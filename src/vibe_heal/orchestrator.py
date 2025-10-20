"""Main workflow orchestration for vibe-heal."""

import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from vibe_heal.ai_tools import AIToolFactory
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.config import VibeHealConfig
from vibe_heal.git import GitManager
from vibe_heal.models import FixSummary
from vibe_heal.processor import IssueProcessor
from vibe_heal.sonarqube import SonarQubeClient
from vibe_heal.sonarqube.models import SonarQubeIssue

logger = logging.getLogger(__name__)


class VibeHealOrchestrator:
    """Orchestrates the fix workflow."""

    def __init__(self, config: VibeHealConfig) -> None:
        """Initialize orchestrator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.console = Console()
        self.git_manager = GitManager()
        self.ai_tool = self._initialize_ai_tool()

    def _initialize_ai_tool(self) -> AITool:
        """Initialize AI tool based on config or auto-detect.

        Returns:
            Initialized AI tool

        Raises:
            RuntimeError: If no AI tool is available
        """
        if self.config.ai_tool:
            tool_type: AIToolType = self.config.ai_tool
            self.console.print(f"[blue]Using configured AI tool: {tool_type.display_name}[/blue]")
        else:
            detected_tool = AIToolFactory.detect_available()
            if not detected_tool:
                msg = "No AI tool found. Please install Claude Code or Aider."
                raise RuntimeError(msg)
            tool_type = detected_tool
            self.console.print(f"[blue]Auto-detected AI tool: {tool_type.display_name}[/blue]")

        return AIToolFactory.create(tool_type, self.config)

    async def fix_file(
        self,
        file_path: str,
        dry_run: bool = False,
        max_issues: int | None = None,
        min_severity: str | None = None,
    ) -> FixSummary:
        """Fix SonarQube issues in a file.

        Args:
            file_path: Path to file to fix
            dry_run: If True, don't commit changes
            max_issues: Maximum number of issues to fix
            min_severity: Minimum severity to process

        Returns:
            Summary of fixes

        Raises:
            RuntimeError: If not a Git repository, file has uncommitted changes, or AI tool unavailable
            FileNotFoundError: If the specified file does not exist
        """
        # Step 1: Validate preconditions
        self._validate_preconditions(file_path, dry_run)

        # Step 2: Fetch issues from SonarQube
        self.console.print(f"\n[yellow]Fetching issues for {file_path}...[/yellow]")
        async with SonarQubeClient(self.config) as sonar_client:
            issues = await sonar_client.get_issues_for_file(file_path)

        if not issues:
            self.console.print("[green]No issues found![/green]")
            return FixSummary(total_issues=0)

        # Step 3: Process issues (filter and sort)
        processor = IssueProcessor(
            min_severity=min_severity,
            max_issues=max_issues,
        )
        result = processor.process(issues)

        self.console.print(
            f"[cyan]Found {result.total_issues} total issues, "
            f"{result.fixable_issues} fixable, "
            f"processing {len(result.issues_to_fix)}[/cyan]\n"
        )

        if not result.has_issues:
            self.console.print("[yellow]No fixable issues to process[/yellow]")
            return FixSummary(
                total_issues=result.total_issues,
                skipped=result.skipped_issues,
            )

        # Step 4: Confirm with user
        if not dry_run and not self._confirm_processing(len(result.issues_to_fix)):
            self.console.print("[yellow]Cancelled by user[/yellow]")
            return FixSummary(
                total_issues=result.total_issues,
                skipped=len(result.issues_to_fix),
            )

        # Step 5: Process each issue
        summary = await self._process_issues(
            result.issues_to_fix,
            file_path,
            dry_run,
        )
        summary.total_issues = result.total_issues
        summary.skipped = result.skipped_issues

        # Step 6: Display summary
        self._display_summary(summary, dry_run)

        return summary

    def _validate_preconditions(self, file_path: str, dry_run: bool) -> None:
        """Validate preconditions before fixing.

        Args:
            file_path: Path to file
            dry_run: Whether in dry-run mode

        Raises:
            RuntimeError: If not a Git repository, file has uncommitted changes, or AI tool unavailable
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

        # Check file doesn't have uncommitted changes (unless dry-run)
        if not dry_run and self.git_manager.has_uncommitted_changes(file_path):
            msg = f"File '{file_path}' has uncommitted changes. Please commit or stash changes before fixing."
            raise RuntimeError(msg)

        # Check AI tool is available
        if not self.ai_tool.is_available():
            msg = f"{self.ai_tool.tool_type.display_name} is not available"
            raise RuntimeError(msg)

    def _confirm_processing(self, issue_count: int) -> bool:
        """Ask user to confirm processing.

        Args:
            issue_count: Number of issues to process

        Returns:
            True if user confirms
        """
        self.console.print(f"\n[bold yellow]About to process {issue_count} issue(s).[/bold yellow]")
        self.console.print("[yellow]Each fix will be committed separately.[/yellow]")

        response = input("Continue? [y/N]: ").strip().lower()
        return response in ["y", "yes"]

    async def _process_issues(
        self,
        issues: list[SonarQubeIssue],
        file_path: str,
        dry_run: bool,
    ) -> FixSummary:
        """Process each issue.

        Args:
            issues: List of issues to process
            file_path: Path to file
            dry_run: Whether in dry-run mode

        Returns:
            Fix summary
        """
        summary = FixSummary(total_issues=0)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            for idx, issue in enumerate(issues, 1):
                task = progress.add_task(
                    f"[cyan]Fixing issue {idx}/{len(issues)} (line {issue.line}): {issue.message[:50]}...",
                    total=None,
                )

                # Attempt to fix
                fix_result = await self.ai_tool.fix_issue(issue, file_path)

                if fix_result.success:
                    # Commit if not dry-run
                    if not dry_run:
                        try:
                            sha = self.git_manager.commit_fix(
                                issue,
                                fix_result.files_modified,
                                self.ai_tool.tool_type,
                            )
                            summary.commits.append(sha)
                            summary.fixed += 1
                            progress.update(
                                task,
                                description=f"[green]✓ Fixed line {issue.line}[/green]",
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
                            description=f"[green]✓ Would fix line {issue.line} (dry-run)[/green]",
                        )
                else:
                    summary.failed += 1
                    error = fix_result.error_message or "Unknown error"
                    progress.update(
                        task,
                        description=f"[red]✗ Failed: {error[:50]}[/red]",
                    )
                    logger.error(f"Failed to fix issue {issue.key}: {fix_result.error_message}")

        return summary

    def _display_summary(self, summary: FixSummary, dry_run: bool) -> None:
        """Display fix summary.

        Args:
            summary: Fix summary
            dry_run: Whether in dry-run mode
        """
        self.console.print("\n[bold]Summary:[/bold]")
        self.console.print(f"  Total issues: {summary.total_issues}")
        self.console.print(f"  [green]Fixed: {summary.fixed}[/green]")
        self.console.print(f"  [red]Failed: {summary.failed}[/red]")
        self.console.print(f"  [yellow]Skipped: {summary.skipped}[/yellow]")

        if summary.fixed > 0:
            self.console.print(f"  Success rate: {summary.success_rate:.1f}%")

        if not dry_run and summary.commits:
            self.console.print(f"\n[bold]Created {len(summary.commits)} commit(s)[/bold]")

        if dry_run:
            self.console.print("\n[yellow]Dry-run mode: no changes committed[/yellow]")
