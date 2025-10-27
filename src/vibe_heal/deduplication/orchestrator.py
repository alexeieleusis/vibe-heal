"""Orchestrator for deduplication workflow."""

import logging
from pathlib import Path

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

        # Add general refactoring guidance
        prompt_parts.append("\n\nPlease refactor this duplicate code. Consider appropriate strategies such as:")
        prompt_parts.append("- Extracting a function or method")
        prompt_parts.append("- Finding a suitable class in the inheritance hierarchy")
        prompt_parts.append("- Extracting a reusable component")
        prompt_parts.append("- Using composition or dependency injection patterns")
        prompt_parts.append("\nAnalyze the context and choose the most appropriate refactoring approach.")

        return "\n".join(prompt_parts)

    def _handle_fix_result(
        self,
        fix_result: FixResult,
        group: DuplicationGroup,
        target_ref: str,
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
                    commit_msg = (
                        f"refactor: [duplication] remove duplicate code at line {target_block.from_line}\n\n"
                        f"Refactored duplicate code block spanning lines {target_block.from_line}-{target_block.to_line} "
                        f"({target_block.size} lines).\n\n"
                        f"This code was duplicated in {len(group.blocks)} location(s).\n\n"
                        f"AI tool: {self.ai_tool.tool_type.display_name}"
                    )

                    sha = self.git_manager.create_commit(commit_msg, [file_path])
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
