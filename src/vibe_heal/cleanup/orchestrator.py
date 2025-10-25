"""Branch cleanup orchestration."""

import asyncio
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from vibe_heal.ai_tools.base import AITool
from vibe_heal.config import VibeHealConfig
from vibe_heal.git.branch_analyzer import BranchAnalyzer
from vibe_heal.git.manager import GitManager
from vibe_heal.orchestrator import VibeHealOrchestrator
from vibe_heal.sonarqube.analysis_runner import AnalysisResult, AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.project_manager import ProjectManager, TempProjectMetadata

console = Console()


class FileCleanupResult(BaseModel):
    """Result of cleaning up a single file."""

    file_path: Path
    issues_fixed: int
    success: bool
    error_message: str | None = None


class CleanupResult(BaseModel):
    """Result of branch cleanup operation."""

    success: bool
    files_processed: list[FileCleanupResult]
    temp_project: TempProjectMetadata | None = None
    analysis_result: AnalysisResult | None = None
    total_issues_fixed: int = 0
    error_message: str | None = None


class CleanupOrchestrator:
    """Orchestrates branch cleanup workflow.

    Coordinates:
    - Branch analysis (modified files)
    - Temporary project creation
    - SonarQube analysis
    - Issue fixing via AI tool
    - Project cleanup
    """

    def __init__(
        self,
        config: VibeHealConfig,
        client: SonarQubeClient,
        ai_tool: AITool,
    ) -> None:
        """Initialize the cleanup orchestrator.

        Args:
            config: Application configuration
            client: SonarQube API client
            ai_tool: AI tool for fixing issues
        """
        self.config = config
        self.client = client
        self.ai_tool = ai_tool
        self.project_manager = ProjectManager(client)
        self.analysis_runner = AnalysisRunner(config, client)
        self.branch_analyzer = BranchAnalyzer(Path.cwd())
        self.git_manager = GitManager(Path.cwd())

    async def cleanup_branch(
        self,
        base_branch: str = "origin/main",
        max_iterations: int = 10,
        file_patterns: list[str] | None = None,
    ) -> CleanupResult:
        """Clean up all modified files in current branch.

        Workflow:
        1. Analyze branch to get modified files
        2. Create temporary SonarQube project
        3. Run analysis on project
        4. Fix issues for each file iteratively
        5. Delete temporary project

        Args:
            base_branch: Base branch to compare against (default: origin/main)
            max_iterations: Maximum analysis iterations per file (default: 10)
            file_patterns: Optional list of glob patterns to filter files

        Returns:
            CleanupResult with success status and details
        """
        temp_project: TempProjectMetadata | None = None
        files_processed: list[FileCleanupResult] = []

        try:
            # Step 1: Analyze branch to get modified files
            console.print(f"[dim]Analyzing branch against {base_branch}...[/dim]")
            modified_files = self.branch_analyzer.get_modified_files(base_branch)
            console.print(f"[dim]Found {len(modified_files)} modified files[/dim]")

            if not modified_files:
                return CleanupResult(
                    success=True,
                    files_processed=[],
                    total_issues_fixed=0,
                )

            # Filter files if patterns provided
            if file_patterns:
                console.print(f"[dim]Filtering files with patterns: {file_patterns}[/dim]")
                modified_files = self._filter_files(modified_files, file_patterns)
                console.print(f"[dim]After filtering: {len(modified_files)} files remain[/dim]")

            if not modified_files:
                return CleanupResult(
                    success=True,
                    files_processed=[],
                    total_issues_fixed=0,
                )

            # List files that will be processed
            console.print("[dim]Files to process:[/dim]")
            for f in modified_files:
                console.print(f"[dim]  - {f}[/dim]")

            # Step 2: Create temporary SonarQube project
            console.print("\n[dim]Creating temporary SonarQube project...[/dim]")
            current_branch = self.branch_analyzer.get_current_branch()
            user_email = self.branch_analyzer.get_user_email()

            temp_project = await self.project_manager.create_temp_project(
                base_key=self.config.sonarqube_project_key,
                branch_name=current_branch,
                user_email=user_email,
            )
            console.print(f"[dim]Created project: {temp_project.project_key}[/dim]")

            # Step 3: Run initial analysis on entire project
            console.print("\n[dim]Running SonarQube analysis...[/dim]")
            analysis_result = await self.analysis_runner.run_analysis(
                project_key=temp_project.project_key,
                project_name=temp_project.project_name,
                project_dir=Path.cwd(),
            )

            if not analysis_result.success:
                console.print(f"[red]Analysis failed: {analysis_result.error_message}[/red]")
                return CleanupResult(
                    success=False,
                    files_processed=[],
                    temp_project=temp_project,
                    analysis_result=analysis_result,
                    error_message=f"Initial analysis failed: {analysis_result.error_message}",
                )

            console.print(f"[dim]Analysis completed successfully. Dashboard: {analysis_result.dashboard_url}[/dim]")

            # Step 4: Fix issues for each modified file
            for file_path in modified_files:
                file_result = await self._cleanup_file(
                    file_path=file_path,
                    project_key=temp_project.project_key,
                    project_name=temp_project.project_name,
                    max_iterations=max_iterations,
                )
                files_processed.append(file_result)

            # Calculate total issues fixed
            total_issues_fixed = sum(f.issues_fixed for f in files_processed)

            # Step 5: Cleanup happens in finally block
            return CleanupResult(
                success=True,
                files_processed=files_processed,
                temp_project=temp_project,
                analysis_result=analysis_result,
                total_issues_fixed=total_issues_fixed,
            )

        except Exception as e:
            return CleanupResult(
                success=False,
                files_processed=files_processed,
                temp_project=temp_project,
                error_message=f"Cleanup failed: {e}",
            )

        finally:
            # Always cleanup temporary project
            if temp_project:
                try:
                    await self.project_manager.delete_project(temp_project.project_key)
                except Exception as e:
                    # Log but don't fail the operation if cleanup fails
                    # The main operation result should still be returned
                    _ = e  # Suppress unused variable warning

    async def _cleanup_file(
        self,
        file_path: Path,
        project_key: str,
        project_name: str,
        max_iterations: int,
    ) -> FileCleanupResult:
        """Clean up issues in a single file iteratively.

        Runs analysis and fixes issues until no more issues remain or max iterations reached.

        Args:
            file_path: Path to file to clean up
            project_key: Temporary project key
            project_name: Temporary project name
            max_iterations: Maximum number of iterations

        Returns:
            FileCleanupResult with fix details
        """
        total_fixed = 0

        try:
            console.print(f"\n[dim]Processing {file_path}...[/dim]")

            for iteration in range(max_iterations):
                console.print(f"[dim]  Iteration {iteration + 1}/{max_iterations}[/dim]")

                # Run analysis for this specific file
                analysis_result = await self.analysis_runner.run_analysis(
                    project_key=project_key,
                    project_name=project_name,
                    project_dir=Path.cwd(),
                    sources=[file_path],  # Optimize: analyze only this file
                )

                if not analysis_result.success:
                    console.print(f"[red]  Analysis failed at iteration {iteration + 1}[/red]")
                    return FileCleanupResult(
                        file_path=file_path,
                        issues_fixed=total_fixed,
                        success=False,
                        error_message=f"Analysis failed at iteration {iteration + 1}: {analysis_result.error_message}",
                    )

                # Get issues for this file from SonarQube
                console.print("[dim]  Fetching issues from SonarQube...[/dim]")
                issues = await self.client.get_issues_for_file(str(file_path), resolved=False)
                console.print(f"[dim]  Found {len(issues)} total issues[/dim]")

                # Filter fixable issues
                fixable_issues = [issue for issue in issues if issue.is_fixable]
                console.print(f"[dim]  {len(fixable_issues)} fixable issues[/dim]")

                if not fixable_issues:
                    # No more issues to fix
                    console.print(f"[green]  ✓ No more fixable issues (fixed {total_fixed} total)[/green]")
                    return FileCleanupResult(
                        file_path=file_path,
                        issues_fixed=total_fixed,
                        success=True,
                    )

                # Use existing orchestrator to fix file
                # This reuses all the existing logic from the fix command
                console.print(f"[dim]  Invoking AI tool to fix {len(fixable_issues)} issues...[/dim]")
                orchestrator = VibeHealOrchestrator(config=self.config)

                # Fix the file (will handle all issues in reverse line order)
                fix_summary = await orchestrator.fix_file(
                    file_path=str(file_path),
                    max_issues=len(fixable_issues),
                    min_severity=None,  # Fix all severities
                    dry_run=False,
                )

                console.print(
                    f"[dim]  Fixed: {fix_summary.fixed}, Failed: {fix_summary.failed}, Skipped: {fix_summary.skipped}[/dim]"
                )

                # Check if any fixes failed
                if fix_summary.has_failures:
                    console.print(f"[red]  Fix failed at iteration {iteration + 1}[/red]")
                    return FileCleanupResult(
                        file_path=file_path,
                        issues_fixed=total_fixed,
                        success=False,
                        error_message=f"Fix failed at iteration {iteration + 1}: {fix_summary.failed} fixes failed",
                    )

                # Track how many issues were fixed this iteration
                total_fixed += fix_summary.fixed
                console.print(f"[dim]  Total fixed so far: {total_fixed}[/dim]")

                # Wait a bit before next analysis to let SonarQube process
                await asyncio.sleep(2)

            # Reached max iterations
            return FileCleanupResult(
                file_path=file_path,
                issues_fixed=total_fixed,
                success=True,
            )

        except Exception as e:
            return FileCleanupResult(
                file_path=file_path,
                issues_fixed=total_fixed,
                success=False,
                error_message=f"Cleanup failed: {e}",
            )

    def _filter_files(
        self,
        files: list[Path],
        patterns: list[str],
    ) -> list[Path]:
        """Filter files by glob patterns.

        Args:
            files: List of file paths
            patterns: List of glob patterns (e.g., ["*.py", "src/**/*.ts"])

        Returns:
            Filtered list of files matching at least one pattern
        """
        filtered = []
        for file_path in files:
            for pattern in patterns:
                if file_path.match(pattern):
                    filtered.append(file_path)
                    break
        return filtered
