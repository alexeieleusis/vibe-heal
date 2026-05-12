"""Review orchestration for analyzing SonarQube issues on changed lines."""

from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from vibe_heal.config import VibeHealConfig
from vibe_heal.git.branch_analyzer import BranchAnalyzer
from vibe_heal.git.diff_parser import DiffParser
from vibe_heal.review.github import GitHubReviewClient
from vibe_heal.review.line_filter import IssueLineFilter
from vibe_heal.review.models import FileReview, ReviewIssue, ReviewResult
from vibe_heal.review.reporter import default_report_dir, load_report, write_reports
from vibe_heal.sonarqube.analysis_runner import AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import ComponentNotFoundError
from vibe_heal.sonarqube.project_manager import ProjectManager, TempProjectMetadata

console = Console()


class ReviewAnalysisResult(BaseModel):
    """Result of a review analysis operation."""

    success: bool = True
    project_key: str = ""
    branch: str = ""
    base_branch: str = ""
    files: list[FileReview] = []
    error_message: str | None = None
    report_file: Path | None = None

    @property
    def total_issues(self) -> int:
        """Return the total number of issues across all files."""
        return sum(len(f.issues) for f in self.files)


class ReviewOrchestrator:
    """Orchestrates the review workflow: analyze changed lines for SonarQube issues.

    Coordinates:
    - Branch analysis (modified files)
    - Diff parsing (changed lines)
    - Temporary project creation
    - SonarQube analysis
    - Issue filtering to changed lines
    - Report generation
    - GitHub review posting
    """

    def __init__(
        self,
        config: VibeHealConfig,
        client: SonarQubeClient,
        branch_analyzer: BranchAnalyzer | None = None,
        diff_parser: DiffParser | None = None,
    ) -> None:
        """Initialize the review orchestrator.

        Args:
            config: Application configuration.
            client: SonarQube API client.
            branch_analyzer: Optional BranchAnalyzer instance (for testing).
            diff_parser: Optional DiffParser instance (for testing).
        """
        self.config = config
        self.client = client
        self.branch_analyzer = branch_analyzer if branch_analyzer is not None else BranchAnalyzer(Path.cwd())
        self.diff_parser = diff_parser if diff_parser is not None else DiffParser(Path.cwd())
        self.project_manager = ProjectManager(client)
        self.analysis_runner = AnalysisRunner(config, client)
        self.github_client = GitHubReviewClient()

    async def run_analysis(
        self,
        base_branch: str = "origin/main",
        file_patterns: list[str] | None = None,
        report_file: Path | None = None,
        verbose: bool = False,
    ) -> ReviewAnalysisResult:
        """Analyze SonarQube issues on changed lines.

        Workflow:
        1. Get modified files from BranchAnalyzer
        2. Filter by patterns if specified
        3. Get changed lines from DiffParser
        4. Create temp project, copy exclusion settings
        5. Run analysis (sonar-scanner)
        6. For each modified file: fetch issues, filter to changed lines
        7. Build ReviewResult, write reports
        8. Delete temp project in finally block

        Args:
            base_branch: Base branch to compare against.
            file_patterns: Optional list of glob patterns to filter files.
            report_file: Optional path to write the report JSON to.
                If provided, the parent directory is used for report output.
            verbose: Enable verbose output.

        Returns:
            ReviewAnalysisResult with success status and review data.
        """
        temp_project: TempProjectMetadata | None = None
        branch = self.branch_analyzer.get_current_branch()
        if report_file is None:
            report_file = default_report_dir(self.config.sonarqube_project_key, branch) / "review.json"
        result = ReviewAnalysisResult(
            project_key=self.config.sonarqube_project_key,
            branch=branch,
            base_branch=base_branch,
            report_file=report_file,
        )

        try:
            # Step 1: Get modified files
            console.print(f"[dim]Analyzing branch against {base_branch}...[/dim]")
            modified_files = self.branch_analyzer.get_modified_files(base_branch)
            console.print(f"[dim]Found {len(modified_files)} modified files[/dim]")

            if not modified_files:
                console.print("[green]No modified files to review.[/green]")
                self._write_report(result, report_file)
                return result

            # Step 2: Filter by patterns if specified
            if file_patterns:
                console.print(f"[dim]Filtering files with patterns: {file_patterns}[/dim]")
                modified_files = self._filter_files(modified_files, file_patterns)
                console.print(f"[dim]After filtering: {len(modified_files)} files remain[/dim]")

            if not modified_files:
                console.print("[green]No files match the specified patterns.[/green]")
                self._write_report(result, report_file)
                return result

            # Step 3: Get changed lines
            changed_lines_map = self.diff_parser.get_changed_lines(base_branch)

            # Step 4: Create temp project
            temp_project = await self._create_temp_project()

            # Step 5: Run analysis
            console.print("[dim]Running SonarQube analysis...[/dim]")
            analysis_result = await self.analysis_runner.run_analysis(
                project_key=temp_project.project_key,
                project_name=temp_project.project_name,
                project_dir=Path.cwd(),
            )

            if not analysis_result.success:
                error_msg = analysis_result.error_message or "Analysis failed"
                console.print(f"[red]Analysis failed: {error_msg}[/red]")
                return ReviewAnalysisResult(
                    project_key=self.config.sonarqube_project_key,
                    branch=result.branch,
                    base_branch=base_branch,
                    success=False,
                    error_message=error_msg,
                )

            console.print("[dim]Analysis completed successfully.[/dim]")

            # Step 6: Fetch issues for each file, filter to changed lines
            original_project_key = self.config.sonarqube_project_key
            self.config.sonarqube_project_key = temp_project.project_key
            self.client.config.sonarqube_project_key = temp_project.project_key

            try:
                for file_path in modified_files:
                    file_issues = await self._get_filtered_issues(file_path, changed_lines_map, verbose)
                    if file_issues:
                        result.files.append(
                            FileReview(
                                file_path=str(file_path),
                                issues=file_issues,
                            )
                        )
                    elif verbose:
                        console.print(f"[dim]  {file_path}: no issues on changed lines[/dim]")
            finally:
                self.config.sonarqube_project_key = original_project_key
                self.client.config.sonarqube_project_key = original_project_key

            # Step 7: Write reports
            self._write_report(result, report_file)

            console.print(
                f"[green]Review complete: {result.total_issues} issue(s) "
                f"found across {len(result.files)} file(s).[/green]"
            )
            return result

        except Exception as e:
            return ReviewAnalysisResult(
                project_key=self.config.sonarqube_project_key,
                branch=result.branch,
                base_branch=base_branch,
                success=False,
                error_message=f"Review failed: {e}",
            )

        finally:
            await self._cleanup_temp_project(temp_project)

    async def run_post(
        self,
        report_file: Path,
        pr_number: int | None = None,
        verbose: bool = False,
    ) -> None:
        """Post review comments to a GitHub PR.

        Workflow:
        1. Load report from JSON
        2. Detect or use explicit PR number
        3. Post review comments via GitHubReviewClient

        Args:
            report_file: Path to the saved review.json file.
            pr_number: Optional explicit PR number. If None, auto-detect.
            verbose: Enable verbose output.
        """
        # Step 1: Load report
        report_dir = report_file.parent
        console.print(f"[dim]Loading report from {report_dir}...[/dim]")
        report = load_report(report_dir)

        # Step 2: Detect PR number
        pr = pr_number if pr_number is not None else await self.github_client.detect_pr()
        console.print(f"[dim]Posting review to PR #{pr}...[/dim]")

        # Step 3: Post review
        await self.github_client.post_review(pr, report)
        console.print(f"[green]Posted {report.total_issues} issue(s) as review comments on PR #{pr}.[/green]")

    async def _create_temp_project(self) -> TempProjectMetadata:
        """Create temporary SonarQube project for analysis.

        Returns:
            TempProjectMetadata for the created project.
        """
        console.print("[dim]Creating temporary SonarQube project...[/dim]")
        current_branch = self.branch_analyzer.get_current_branch()
        user_email = self.branch_analyzer.get_user_email()

        temp_project = await self.project_manager.create_temp_project(
            base_key=self.config.sonarqube_project_key,
            branch_name=current_branch,
            user_email=user_email,
        )
        console.print(f"[dim]Created project: {temp_project.project_key}[/dim]")

        try:
            copied, inherited_count = await self.project_manager.copy_exclusion_settings(
                source_key=self.config.sonarqube_project_key,
                target_key=temp_project.project_key,
            )
            if copied:
                console.print(f"[dim]Copied {len(copied)} exclusion setting(s): {', '.join(copied)}[/dim]")
            if inherited_count:
                console.print(f"[dim]Skipped {inherited_count} inherited setting(s)[/dim]")
            if not copied and not inherited_count:
                console.print("[dim]No exclusion settings configured on source project[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not copy exclusion settings: {e}[/yellow]")

        return temp_project

    async def _get_filtered_issues(
        self,
        file_path: Path,
        changed_lines_map: dict[str, set[int]],
        verbose: bool,
    ) -> list[ReviewIssue]:
        """Fetch issues for a file and filter to changed lines.

        Args:
            file_path: Path to the file.
            changed_lines_map: Mapping of file paths to changed line sets.
            verbose: Enable verbose output.

        Returns:
            List of ReviewIssue for issues on changed lines.
        """
        try:
            issues = await self.client.get_issues_for_file(str(file_path), resolved=False)
        except ComponentNotFoundError:
            if verbose:
                console.print(f"[dim]  {file_path}: skipped (not in SonarQube analysis)[/dim]")
            return []

        changed_lines = changed_lines_map.get(str(file_path), set())

        if not changed_lines:
            if verbose:
                console.print(f"[dim]  {file_path}: no changed lines in diff[/dim]")
            return []

        filtered = IssueLineFilter.filter_issues(issues, changed_lines)

        if verbose and filtered:
            console.print(f"[dim]  {file_path}: {len(filtered)} issue(s) on changed lines[/dim]")
        return filtered

    async def _cleanup_temp_project(self, temp_project: TempProjectMetadata | None) -> None:
        """Clean up temporary SonarQube project.

        Args:
            temp_project: Temporary project metadata (None if not created).
        """
        if temp_project:
            try:
                console.print(f"[dim]Deleting temporary project: {temp_project.project_key}[/dim]")
                await self.project_manager.delete_project(temp_project.project_key)
                console.print("[green]Temporary project deleted.[/green]")
            except Exception as e:
                console.print(f"[yellow]Warning: Failed to delete temporary project: {e}[/yellow]")

    def _filter_files(
        self,
        files: list[Path],
        patterns: list[str],
    ) -> list[Path]:
        """Filter files by glob patterns.

        Args:
            files: List of file paths.
            patterns: List of glob patterns.

        Returns:
            Filtered list of files matching at least one pattern.
        """
        filtered: list[Path] = []
        for file_path in files:
            for pattern in patterns:
                if file_path.match(pattern):
                    filtered.append(file_path)
                    break
        return filtered

    def _write_report(self, result: ReviewAnalysisResult, report_file: Path | None) -> None:
        """Write report files if a report path is specified.

        Args:
            result: Review result to write.
            report_file: Optional path to the report JSON file.
        """
        if report_file is None:
            return

        report_dir = report_file.parent
        review_result = ReviewResult(
            project_key=result.project_key,
            branch=result.branch,
            base_branch=result.base_branch,
            files=result.files,
        )
        write_reports(review_result, report_dir)
        console.print(f"[dim]Reports written to {report_dir}[/dim]")
