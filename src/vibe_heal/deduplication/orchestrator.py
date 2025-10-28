"""Orchestrator for deduplication workflow."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn

from vibe_heal.ai_tools.base import AITool
from vibe_heal.ai_tools.models import FixResult
from vibe_heal.config import VibeHealConfig
from vibe_heal.deduplication.client import DuplicationClient
from vibe_heal.deduplication.models import DuplicationGroup, DuplicationsResponse
from vibe_heal.deduplication.processor import (
    DuplicationProcessor,
)
from vibe_heal.git import GitManager
from vibe_heal.models import FixSummary

if TYPE_CHECKING:
    from vibe_heal.sonarqube.client import SonarQubeClient
    from vibe_heal.sonarqube.project_manager import TempProjectMetadata

logger = logging.getLogger(__name__)


class DeduplicationOrchestrator:
    """Orchestrates the deduplication workflow."""

    def __init__(
        self,
        config: VibeHealConfig,
        ai_tool: AITool,
        console: Console | None = None,
        git_manager: GitManager | None = None,
    ) -> None:
        """Initialize deduplication orchestrator.

        Args:
            config: Application configuration
            ai_tool: AI tool instance
            console: Rich console for output (creates new if None)
            git_manager: Git manager instance (creates new if None)
        """
        self.config = config
        self.ai_tool = ai_tool
        self.console = console or Console()
        self.git_manager = git_manager or GitManager()

    async def dedupe_file(
        self,
        file_path: str,
        dry_run: bool = False,
        max_duplications: int | None = None,
    ) -> FixSummary:
        """Remove code duplications in a file.

        Args:
            file_path: Path to file to deduplicate
            dry_run: If True, don't commit changes
            max_duplications: Maximum number of duplication groups to fix

        Returns:
            Summary of deduplication fixes

        Raises:
            RuntimeError: If not a Git repository or AI tool unavailable
            FileNotFoundError: If the specified file does not exist
        """
        # Step 1: Validate preconditions
        self._validate_preconditions(file_path, dry_run)

        # Step 2: Fetch duplications from SonarQube
        self.console.print(f"\n[yellow]Fetching duplications for {file_path}...[/yellow]")
        async with DuplicationClient(self.config) as dup_client:
            response = await dup_client.get_duplications_for_file(file_path)

        if not response.duplications:
            self.console.print("[green]No duplications found![/green]")
            return FixSummary(total_issues=0)

        # Step 3: Process duplications (filter and sort)
        processor = DuplicationProcessor(max_duplications=max_duplications)
        component_key = f"{self.config.sonarqube_project_key}:{file_path}"
        result = processor.process(response, component_key)

        self.console.print(
            f"[cyan]Found {result.total_groups} total duplication groups, "
            f"{result.processable_groups} in this file, "
            f"processing {len(result.groups_to_fix)}[/cyan]\n"
        )

        if not result.groups_to_fix:
            self.console.print("[yellow]No duplications to process[/yellow]")
            return FixSummary(
                total_issues=result.total_groups,
                skipped=result.skipped_groups,
            )

        # Step 4: Load source file
        source_lines = self._load_source_file(file_path)

        # Step 5: Process each duplication group
        summary = await self._process_duplications(
            result.groups_to_fix,
            response,
            component_key,
            file_path,
            source_lines,
            dry_run,
        )
        summary.total_issues = result.total_groups
        summary.skipped = result.skipped_groups

        # Step 6: Display summary
        self._display_summary(summary, dry_run)

        return summary

    def _validate_preconditions(self, file_path: str, dry_run: bool) -> None:
        """Validate preconditions before deduplicating.

        Args:
            file_path: Path to file
            dry_run: Whether in dry-run mode

        Raises:
            RuntimeError: If not a Git repository or AI tool unavailable
            FileNotFoundError: If the specified file does not exist
        """
        # Check Git repository
        if not self.git_manager.is_repository():
            msg = "Not a Git repository"
            raise RuntimeError(msg)

        # Check file exists
        if not Path(file_path).exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        # Check working directory is clean unless dry-run
        if not dry_run:
            self.git_manager.require_clean_working_directory()

        # Check AI tool is available
        if not self.ai_tool.is_available():
            msg = f"{self.ai_tool.tool_type.display_name} is not available"
            raise RuntimeError(msg)

    def _load_source_file(self, file_path: str) -> list[str]:
        """Load source file contents.

        Args:
            file_path: Path to file

        Returns:
            List of source lines (0-indexed)
        """
        with open(file_path, encoding="utf-8") as f:
            return f.readlines()

    def _create_duplication_prompt(
        self,
        group: DuplicationGroup,
        target_ref: str,
        response: DuplicationsResponse,
        source_lines: list[str],
    ) -> str:
        """Create AI prompt for fixing a duplication.

        Args:
            group: Duplication group to fix
            target_ref: Reference ID of target file
            response: Full duplications response
            source_lines: Source code lines (0-indexed)

        Returns:
            Formatted prompt for AI tool
        """
        target_block = group.get_target_block(target_ref)
        if not target_block:
            return "Error: Could not find target block"

        # Get first 3 and last 3 lines of duplication
        first_lines, last_lines = target_block.get_snippet_lines(source_lines)

        # Build prompt
        prompt_parts = [
            f"Duplicate code detected at lines {target_block.from_line}-{target_block.to_line} ({target_block.size} lines total)\n",
        ]

        # Add code snippet
        if target_block.size <= 6:
            prompt_parts.append("Code block:")
            for i, line in enumerate(first_lines + last_lines, start=target_block.from_line):
                prompt_parts.append(f"{i}: {line.rstrip()}")
        else:
            prompt_parts.append("First 3 lines:")
            for i, line in enumerate(first_lines, start=target_block.from_line):
                prompt_parts.append(f"{i}: {line.rstrip()}")

            omitted = target_block.size - 6
            prompt_parts.append(f"\n... ({omitted} lines omitted) ...\n")

            prompt_parts.append("Last 3 lines:")
            start_line = target_block.to_line - len(last_lines) + 1
            for i, line in enumerate(last_lines, start=start_line):
                prompt_parts.append(f"{i}: {line.rstrip()}")

        # Add information about other duplication locations
        other_blocks = group.get_other_blocks(target_ref)
        if other_blocks:
            prompt_parts.append(f"\n\nThis code is duplicated in {len(other_blocks)} other location(s):")
            for block in other_blocks:
                file_info = response.get_file_info(block.ref)
                if file_info:
                    prompt_parts.append(f"  - {file_info.key} (lines {block.from_line}-{block.to_line})")

        # Add concise refactoring guidance
        prompt_parts.append(
            "\n\nRefactor to eliminate this duplication. Choose the best approach:\n"
            "- Extract function/method (simple cases)\n"
            "- Find suitable parent class (inheritance hierarchies)\n"
            "- Extract reusable component (UI frameworks)\n"
            "- Create utility/helper module (cross-file)\n"
            "- Use composition/dependency injection\n\n"
            "Important: Update ALL duplicate locations consistently."
        )

        return "\n".join(prompt_parts)

    def _handle_fix_result(
        self,
        fix_result: FixResult,
        group: DuplicationGroup,
        target_ref: str,
        response: DuplicationsResponse,
        file_path: str,
        dry_run: bool,
        summary: FixSummary,
        progress: Progress,
        task: TaskID,
    ) -> None:
        """Handle the result of a deduplication fix attempt.

        Args:
            fix_result: Result from AI tool
            group: Duplication group that was fixed
            target_ref: Reference ID of target file
            response: Full duplications response (for file info lookup)
            file_path: Path to file
            dry_run: Whether in dry-run mode
            summary: Summary to update
            progress: Progress bar
            task: Progress task
        """
        target_block = group.get_target_block(target_ref)
        if not target_block:
            summary.failed += 1
            progress.update(task, description="[red]✗ Failed: target block not found[/red]")
            return

        if fix_result.success:
            # Commit if not dry-run
            if not dry_run:
                try:
                    # Create a simplified "issue" representation for commit message
                    # Build list of all duplicate locations
                    duplicate_locations = []
                    for block in group.blocks:
                        file_info = response.get_file_info(block.ref)
                        if file_info:
                            # Extract file path from component key (format: "project:path/to/file.py")
                            file_path = file_info.key.split(":", 1)[1] if ":" in file_info.key else file_info.key
                            duplicate_locations.append(f"  - {file_path} (lines {block.from_line}-{block.to_line})")

                    locations_text = "\n".join(duplicate_locations)

                    commit_msg = (
                        f"refactor: [duplication] remove duplicate code at line {target_block.from_line}\n\n"
                        f"Refactored duplicate code block spanning lines {target_block.from_line}-{target_block.to_line} "
                        f"({target_block.size} lines).\n\n"
                        f"This code was duplicated in {len(group.blocks)} location(s):\n"
                        f"{locations_text}\n\n"
                        f"AI tool: {self.ai_tool.tool_type.display_name}"
                    )

                    # Auto-detect all modified files since duplications may span multiple files
                    # and AI might create new utility modules. Pass None to auto-detect.
                    sha = self.git_manager.create_commit(commit_msg, None, include_untracked=True)
                    if sha:
                        summary.commits.append(sha)
                        summary.fixed += 1
                        progress.update(
                            task,
                            description=f"[green]✓ Fixed duplication at line {target_block.from_line}[/green]",
                        )
                    else:
                        summary.skipped += 1
                        progress.update(
                            task,
                            description=f"[yellow]⊘ Line {target_block.from_line} already fixed[/yellow]",
                        )
                except Exception as e:
                    logger.exception("Failed to commit")
                    summary.failed += 1
                    progress.update(
                        task,
                        description=f"[red]✗ Commit failed: {e}[/red]",
                    )
            else:
                summary.fixed += 1
                progress.update(
                    task,
                    description=f"[green]✓ Would fix duplication at line {target_block.from_line} (dry-run)[/green]",
                )
        else:
            summary.failed += 1
            error = fix_result.error_message or "Unknown error"
            progress.update(
                task,
                description=f"[red]✗ Failed: {error[:50]}[/red]",
            )
            logger.error(f"Failed to fix duplication: {fix_result.error_message}")

    async def _process_duplications(
        self,
        groups: list[DuplicationGroup],
        response: DuplicationsResponse,
        component_key: str,
        file_path: str,
        source_lines: list[str],
        dry_run: bool,
    ) -> FixSummary:
        """Process each duplication group.

        Args:
            groups: List of duplication groups to process
            response: Full duplications response
            component_key: Component key of target file
            file_path: Path to file
            source_lines: Source code lines
            dry_run: Whether in dry-run mode

        Returns:
            Fix summary
        """
        summary = FixSummary(total_issues=0)
        target_ref = response.get_target_file_ref(component_key)

        if not target_ref:
            logger.error(f"Could not find target file ref for {component_key}")
            return summary

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            for idx, group in enumerate(groups, 1):
                target_block = group.get_target_block(target_ref)
                if not target_block:
                    continue

                task = progress.add_task(
                    f"[cyan]Fixing duplication {idx}/{len(groups)} "
                    f"(lines {target_block.from_line}-{target_block.to_line})...",
                    total=None,
                )

                # Create prompt for AI
                prompt = self._create_duplication_prompt(group, target_ref, response, source_lines)

                # Use AI tool to fix (pass prompt as "message" field)
                fix_result = await self.ai_tool.fix_duplication(prompt, file_path)

                self._handle_fix_result(
                    fix_result,
                    group,
                    target_ref,
                    response,
                    file_path,
                    dry_run,
                    summary,
                    progress,
                    task,
                )

        return summary

    def _display_summary(self, summary: FixSummary, dry_run: bool) -> None:
        """Display deduplication summary.

        Args:
            summary: Fix summary
            dry_run: Whether in dry-run mode
        """
        self.console.print("\n[bold]Summary:[/bold]")
        self.console.print(f"  Total duplication groups: {summary.total_issues}")
        self.console.print(f"  [green]Fixed: {summary.fixed}[/green]")
        self.console.print(f"  [red]Failed: {summary.failed}[/red]")
        self.console.print(f"  [yellow]Skipped: {summary.skipped}[/yellow]")

        if summary.fixed > 0:
            self.console.print(f"  Success rate: {summary.success_rate:.1f}%")

        if not dry_run and summary.commits:
            self.console.print(f"\n[bold]Created {len(summary.commits)} commit(s)[/bold]")

        if dry_run:
            self.console.print("\n[yellow]Dry-run mode: no changes committed[/yellow]")


class FileDedupResult(BaseModel):
    """Result of deduplicating a single file."""

    file_path: Path
    duplications_fixed: int
    success: bool
    error_message: str | None = None


class DedupeBranchResult(BaseModel):
    """Result of branch-wide deduplication operation."""

    success: bool
    files_processed: list[FileDedupResult]
    temp_project: Any = None  # TempProjectMetadata
    analysis_result: Any = None  # AnalysisResult
    total_duplications_fixed: int = 0
    error_message: str | None = None


class DedupeBranchOrchestrator:
    """Orchestrates branch-wide deduplication workflow.

    Similar to CleanupOrchestrator but focuses on code duplications.
    Coordinates:
    - Branch analysis (modified files)
    - Temporary project creation
    - SonarQube analysis
    - Duplication fixing via AI tool
    - Project cleanup
    """

    def __init__(
        self,
        config: VibeHealConfig,
        client: "SonarQubeClient",
        ai_tool: AITool,
    ) -> None:
        """Initialize the dedupe-branch orchestrator.

        Args:
            config: Application configuration
            client: SonarQube API client
            ai_tool: AI tool for fixing duplications
        """
        from vibe_heal.git.branch_analyzer import BranchAnalyzer
        from vibe_heal.sonarqube.analysis_runner import AnalysisRunner
        from vibe_heal.sonarqube.project_manager import ProjectManager

        self.config = config
        self.client = client
        self.ai_tool = ai_tool
        self.project_manager = ProjectManager(client)
        self.analysis_runner = AnalysisRunner(config, client)
        self.branch_analyzer = BranchAnalyzer(Path.cwd())
        self.git_manager = GitManager(Path.cwd())
        self.console = Console()

    async def dedupe_branch(
        self,
        base_branch: str = "origin/main",
        max_iterations: int = 10,
        file_patterns: list[str] | None = None,
        verbose: bool = False,
    ) -> DedupeBranchResult:
        """Remove duplications from all modified files in current branch.

        Workflow:
        1. Analyze branch to get modified files
        2. Create temporary SonarQube project
        3. Run SonarQube analysis
        4. For each file with duplications, iteratively dedupe until clean
        5. Delete temporary project

        Args:
            base_branch: Base branch to compare against (default: origin/main)
            max_iterations: Maximum dedup iterations per file (default: 10)
            file_patterns: Optional list of glob patterns to filter files
            verbose: Enable verbose output

        Returns:
            DedupeBranchResult with success status and details
        """
        from vibe_heal.sonarqube.project_manager import TempProjectMetadata

        temp_project: TempProjectMetadata | None = None
        files_processed: list[FileDedupResult] = []

        try:
            # Step 1: Validate and filter modified files
            modified_files = self._validate_and_filter_files(base_branch, file_patterns)

            if not modified_files:
                return DedupeBranchResult(
                    success=True,
                    files_processed=[],
                    total_duplications_fixed=0,
                )

            # Step 2: Create temporary SonarQube project
            temp_project = await self._create_temp_project()

            # Step 3: Run SonarQube analysis
            self.console.print("\n[dim]Running SonarQube analysis...[/dim]")
            analysis_result = await self.analysis_runner.run_analysis(
                project_key=temp_project.project_key,
                project_name=temp_project.project_name,
                project_dir=Path.cwd(),
            )

            if not analysis_result.success:
                self.console.print(f"[red]Analysis failed: {analysis_result.error_message}[/red]")
                return DedupeBranchResult(
                    success=False,
                    files_processed=[],
                    temp_project=temp_project,
                    analysis_result=analysis_result,
                    error_message=f"Analysis failed: {analysis_result.error_message}",
                )

            self.console.print(f"[dim]Analysis completed. Dashboard: {analysis_result.dashboard_url}[/dim]")

            # Step 4: Process each file
            total_duplications_fixed = 0
            for file_path in modified_files:
                file_result = await self._dedupe_file(
                    file_path=file_path,
                    project_key=temp_project.project_key,
                    max_iterations=max_iterations,
                    verbose=verbose,
                )
                files_processed.append(file_result)
                total_duplications_fixed += file_result.duplications_fixed

            return DedupeBranchResult(
                success=True,
                files_processed=files_processed,
                temp_project=temp_project,
                analysis_result=analysis_result,
                total_duplications_fixed=total_duplications_fixed,
            )

        except Exception as e:
            logger.exception("Branch deduplication failed")
            return DedupeBranchResult(
                success=False,
                files_processed=files_processed,
                temp_project=temp_project,
                error_message=str(e),
            )

        finally:
            # Step 5: Always cleanup temporary project
            if temp_project:
                await self._cleanup_temp_project(temp_project)

    def _validate_and_filter_files(
        self,
        base_branch: str,
        file_patterns: list[str] | None,
    ) -> list[Path]:
        """Validate branch and filter modified files.

        Args:
            base_branch: Base branch to compare against
            file_patterns: Optional file patterns to filter

        Returns:
            List of modified file paths to process
        """
        # Validate branch exists
        self.branch_analyzer.validate_branch_exists(base_branch)

        # Get modified files
        modified_files = self.branch_analyzer.get_modified_files(base_branch)

        if not modified_files:
            self.console.print("[yellow]No modified files in branch[/yellow]")
            return []

        # Filter by patterns if provided
        if file_patterns:
            modified_files = self._filter_files(modified_files, file_patterns)

        if not modified_files:
            self.console.print("[yellow]No files match the specified patterns[/yellow]")
            return []

        self.console.print(f"\n[cyan]Found {len(modified_files)} modified file(s) to process[/cyan]")
        for f in modified_files:
            self.console.print(f"  - {f}")

        return modified_files

    def _filter_files(self, files: list[Path], patterns: list[str]) -> list[Path]:
        """Filter files by glob patterns.

        Args:
            files: List of file paths
            patterns: List of glob patterns

        Returns:
            Filtered list of file paths
        """
        from fnmatch import fnmatch

        filtered = []
        for file_path in files:
            for pattern in patterns:
                if fnmatch(str(file_path), pattern):
                    filtered.append(file_path)
                    break
        return filtered

    async def _create_temp_project(self) -> "TempProjectMetadata":
        """Create temporary SonarQube project.

        Returns:
            Temporary project metadata
        """
        from vibe_heal.sonarqube.project_manager import TempProjectMetadata

        branch_name = self.branch_analyzer.get_current_branch()
        user_email = self.branch_analyzer.get_user_email()

        self.console.print("\n[dim]Creating temporary SonarQube project...[/dim]")
        temp_project: TempProjectMetadata = await self.project_manager.create_temp_project(
            base_key=self.config.sonarqube_project_key,
            branch_name=branch_name,
            user_email=user_email,
        )

        self.console.print(f"[dim]Created project: {temp_project.project_key}[/dim]")
        return temp_project

    async def _cleanup_temp_project(self, temp_project: "TempProjectMetadata") -> None:
        """Clean up temporary SonarQube project.

        Args:
            temp_project: Project metadata to cleanup
        """
        try:
            self.console.print("\n[dim]Cleaning up temporary project...[/dim]")
            await self.project_manager.delete_project(temp_project.project_key)
            self.console.print("[dim]Temporary project deleted[/dim]")
        except Exception as e:
            logger.warning(f"Failed to delete temporary project: {e}")
            self.console.print(f"[yellow]Warning: Failed to delete temporary project: {e}[/yellow]")

    async def _dedupe_file(
        self,
        file_path: Path,
        project_key: str,
        max_iterations: int,
        verbose: bool,
    ) -> FileDedupResult:
        """Deduplicate a single file iteratively.

        Args:
            file_path: Path to file to deduplicate
            project_key: SonarQube project key
            max_iterations: Maximum iterations

        Returns:
            File deduplication result
        """
        self.console.print(f"\n[bold cyan]Processing {file_path}[/bold cyan]")

        total_fixed = 0

        try:
            # Create a modified config with the temp project key
            temp_config = VibeHealConfig(env_file=None)
            temp_config.sonarqube_url = self.config.sonarqube_url
            temp_config.sonarqube_token = self.config.sonarqube_token
            temp_config.sonarqube_username = self.config.sonarqube_username
            temp_config.sonarqube_password = self.config.sonarqube_password
            temp_config.sonarqube_project_key = project_key
            temp_config.ai_tool = self.config.ai_tool
            temp_config.code_context_lines = self.config.code_context_lines
            temp_config.include_rule_description = self.config.include_rule_description

            # Create dedupe orchestrator with temp config
            dedupe_orch = DeduplicationOrchestrator(
                config=temp_config,
                ai_tool=self.ai_tool,
                console=self.console,
                git_manager=self.git_manager,
            )

            # Iteratively dedupe until no duplications or max iterations reached
            for iteration in range(max_iterations):
                if verbose:
                    self.console.print(f"[dim]  Iteration {iteration + 1}/{max_iterations}[/dim]")

                # Run deduplication
                summary = await dedupe_orch.dedupe_file(
                    file_path=str(file_path),
                    dry_run=False,
                    max_duplications=None,
                )

                total_fixed += summary.fixed

                # If no duplications were fixed, we're done
                if summary.fixed == 0:
                    if verbose:
                        self.console.print("[dim]  No more duplications to fix[/dim]")
                    break

            return FileDedupResult(
                file_path=file_path,
                duplications_fixed=total_fixed,
                success=True,
            )

        except Exception as e:
            logger.exception(f"Failed to dedupe {file_path}")
            return FileDedupResult(
                file_path=file_path,
                duplications_fixed=total_fixed,
                success=False,
                error_message=str(e),
            )
