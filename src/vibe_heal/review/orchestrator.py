"""Review orchestration for analyzing SonarQube issues on changed lines."""

from pathlib import Path

from pydantic import BaseModel, Field
from rich.console import Console

from vibe_heal.config import VibeHealConfig
from vibe_heal.deduplication.client import DuplicationClient
from vibe_heal.deduplication.models import DuplicationGroup, DuplicationsResponse
from vibe_heal.git.branch_analyzer import BranchAnalyzer
from vibe_heal.git.diff_parser import DiffParser
from vibe_heal.review.github import GitHubReviewClient
from vibe_heal.review.line_filter import IssueLineFilter
from vibe_heal.review.models import (
    DuplicationLocation,
    FileDiagnostics,
    FileReview,
    ResolvedDuplication,
    ReviewDuplication,
    ReviewIssue,
    ReviewResult,
)
from vibe_heal.review.reporter import (
    _write_json,
    _write_markdown,
    default_report_dir,
    load_report_from_path,
)
from vibe_heal.sonarqube.analysis_runner import AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import ComponentNotFoundError, SonarQubeAPIError
from vibe_heal.sonarqube.project_manager import ProjectManager, TempProjectMetadata

console = Console()


class ReviewAnalysisResult(BaseModel):
    """Result of a review analysis operation."""

    success: bool = True
    project_key: str = ""
    branch: str = ""
    base_branch: str = ""
    files: list[FileReview] = Field(default_factory=list)
    diagnostics: list[FileDiagnostics] = Field(default_factory=list)
    diff_files_found: int = 0
    diff_map_keys: list[str] = Field(default_factory=list)
    diff_output_sample: str = ""
    error_message: str | None = None
    report_file: Path | None = None

    @property
    def total_issues(self) -> int:
        """Return the total number of issues across all files."""
        return sum(len(f.issues) for f in self.files)

    @property
    def total_duplications(self) -> int:
        """Return the total number of active and resolved duplication findings."""
        return sum(len(f.duplications) + len(f.resolved_duplications) for f in self.files)


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

            # Step 3: Get changed lines (both new-side and old-side)
            diff_lines = self.diff_parser.get_diff_lines(base_branch)
            changed_lines_map = diff_lines.new_lines
            old_changed_lines_map = diff_lines.old_lines
            result.diff_files_found = len(changed_lines_map)
            result.diff_map_keys = sorted(changed_lines_map.keys())
            raw_diff = self.diff_parser.get_raw_diff(base_branch)
            result.diff_output_sample = raw_diff[:500]

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

            # Step 6: Fetch issues and duplications for each file, filter to changed lines
            original_project_key = self.config.sonarqube_project_key
            self.config.sonarqube_project_key = temp_project.project_key
            self.client.config.sonarqube_project_key = temp_project.project_key

            try:
                for file_path in modified_files:
                    file_issues, diag = await self._get_filtered_issues(file_path, changed_lines_map, verbose)
                    active_dups = await self._get_active_duplications(file_path, changed_lines_map, diag)
                    active_ranges = {(d.from_line, d.to_line) for d in active_dups}
                    resolved_dups = await self._get_resolved_duplications(
                        file_path, changed_lines_map, old_changed_lines_map, active_ranges, original_project_key, diag
                    )
                    result.diagnostics.append(diag)
                    if file_issues or active_dups or resolved_dups:
                        result.files.append(
                            FileReview(
                                file_path=str(file_path),
                                issues=file_issues,
                                duplications=active_dups,
                                resolved_duplications=resolved_dups,
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
                f"[green]Review complete: {result.total_issues} issue(s), "
                f"{result.total_duplications} duplication finding(s) "
                f"across {len(result.files)} file(s).[/green]"
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
        console.print(f"[dim]Loading report from {report_file}...[/dim]")
        report = load_report_from_path(report_file)

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
            copied, inherited_count, failed_count = await self.project_manager.copy_exclusion_settings(
                source_key=self.config.sonarqube_project_key,
                target_key=temp_project.project_key,
            )
            if copied:
                console.print(f"[dim]Copied {len(copied)} exclusion setting(s): {', '.join(copied)}[/dim]")
            if inherited_count:
                console.print(f"[dim]Skipped {inherited_count} inherited setting(s)[/dim]")
            if failed_count:
                console.print(f"[dim]Failed to apply {failed_count} setting(s)[/dim]")
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
    ) -> tuple[list[ReviewIssue], FileDiagnostics]:
        """Fetch issues for a file and filter to changed lines.

        Args:
            file_path: Path to the file.
            changed_lines_map: Mapping of file paths to changed line sets.
            verbose: Enable verbose output.

        Returns:
            Tuple of (filtered ReviewIssues, FileDiagnostics for this file).
        """
        file_path_str = str(file_path)
        repo_relative = self._to_repo_relative(file_path)
        changed_lines = changed_lines_map.get(repo_relative, set())

        diag = FileDiagnostics(
            file_path=file_path_str,
            lookup_key=repo_relative,
            changed_lines=sorted(changed_lines),
        )

        try:
            issues = await self.client.get_issues_for_file(file_path_str, resolved=False)
        except ComponentNotFoundError:
            if verbose:
                console.print(f"[dim]  {file_path}: skipped (not in SonarQube analysis)[/dim]")
            return [], diag

        diag.sonar_issue_count = len(issues)
        diag.sonar_issue_lines = sorted(i.line for i in issues if i.line is not None)

        if not changed_lines:
            if verbose:
                console.print(f"[dim]  {file_path}: no changed lines in diff[/dim]")
            return [], diag

        filtered = IssueLineFilter.filter_issues(issues, changed_lines)

        if verbose and filtered:
            console.print(f"[dim]  {file_path}: {len(filtered)} issue(s) on changed lines[/dim]")
        return filtered, diag

    async def _get_active_duplications(
        self,
        file_path: Path,
        changed_lines_map: dict[str, set[int]],
        diag: FileDiagnostics,
    ) -> list[ReviewDuplication]:
        """Fetch duplication blocks from the temp project that intersect changed lines.

        Args:
            file_path: Path to the file (config already points at temp project).
            changed_lines_map: New-side changed lines per file.
            diag: Per-file diagnostics object to populate with API outcome.

        Returns:
            ReviewDuplication entries for each overlapping block, if any.
        """
        repo_relative = self._to_repo_relative(file_path)
        new_changed_lines = changed_lines_map.get(repo_relative, set())
        if not new_changed_lines:
            diag.active_dup_api_status = "skipped_no_changed_lines"
            return []

        try:
            async with DuplicationClient(self.config) as dup_client:
                response: DuplicationsResponse = await dup_client.get_duplications_for_file(repo_relative)
        except ComponentNotFoundError:
            diag.active_dup_api_status = "component_not_found"
            return []
        except SonarQubeAPIError as e:
            diag.active_dup_api_status = f"api_error:{e}"
            return []
        except Exception as e:
            diag.active_dup_api_status = f"error:{type(e).__name__}:{e}"
            return []

        diag.active_dup_api_status = "ok"
        diag.active_dup_groups_found = len(response.duplications)

        if not response.duplications:
            return []

        component_key = f"{self.config.sonarqube_project_key}:{repo_relative}"
        target_ref = response.get_target_file_ref(component_key)
        if target_ref is None:
            return []

        diag.active_dup_target_ref_found = True

        findings: list[ReviewDuplication] = []
        for group in response.duplications:
            finding = self._build_active_finding(group, target_ref, new_changed_lines, response)
            if finding is not None:
                diag.active_dup_blocks_intersecting += 1
                findings.append(finding)
        return findings

    def _build_active_finding(
        self,
        group: DuplicationGroup,
        target_ref: str,
        new_changed_lines: set[int],
        response: DuplicationsResponse,
    ) -> ReviewDuplication | None:
        target_block = group.get_target_block(target_ref)
        if target_block is None:
            return None
        block_lines = set(range(target_block.from_line, target_block.to_line + 1))
        if not block_lines & new_changed_lines:
            return None
        other_locations = []
        for block in group.get_other_blocks(target_ref):
            file_info = response.get_file_info(block.ref)
            if file_info is None:
                continue
            other_file_path = file_info.key.split(":", 1)[1] if ":" in file_info.key else file_info.key
            other_locations.append(
                DuplicationLocation(
                    file_path=other_file_path,
                    from_line=block.from_line,
                    to_line=block.to_line,
                )
            )
        return ReviewDuplication(
            from_line=target_block.from_line,
            to_line=target_block.to_line,
            other_locations=other_locations,
        )

    async def _get_resolved_duplications(
        self,
        file_path: Path,
        changed_lines_map: dict[str, set[int]],
        old_changed_lines_map: dict[str, set[int]],
        active_dup_ranges: set[tuple[int, int]],
        original_project_key: str,
        diag: FileDiagnostics,
    ) -> list[ResolvedDuplication]:
        """Warn about duplication blocks from main that were modified but not active in temp.

        Queries the main project (not the temp project) for duplications on the
        old-side changed lines. If a block from main intersects those old lines
        and Feature 1 found no corresponding active duplication in the temp project,
        we warn the developer to check the other instances.

        Args:
            file_path: Path to the file.
            changed_lines_map: New-side changed lines per file (for anchor line).
            old_changed_lines_map: Old-side changed lines per file.
            active_dup_ranges: Set of (from_line, to_line) from Feature 1 (skip if covered).
            original_project_key: The main project key (config currently points at temp).
            diag: Per-file diagnostics object to populate with API outcome.

        Returns:
            ResolvedDuplication entries for each uncovered block, if any.
        """
        repo_relative = self._to_repo_relative(file_path)
        old_changed_lines = old_changed_lines_map.get(repo_relative, set())
        if not old_changed_lines:
            diag.resolved_dup_api_status = "skipped_no_changed_lines"
            return []
        new_changed_lines = changed_lines_map.get(repo_relative, set())
        if not new_changed_lines:
            diag.resolved_dup_api_status = "skipped_no_changed_lines"
            return []

        temp_project_key = self.config.sonarqube_project_key
        self.config.sonarqube_project_key = original_project_key
        self.client.config.sonarqube_project_key = original_project_key
        try:
            async with DuplicationClient(self.config) as dup_client:
                response = await dup_client.get_duplications_for_file(repo_relative)
        except ComponentNotFoundError:
            diag.resolved_dup_api_status = "component_not_found"
            return []
        except SonarQubeAPIError as e:
            diag.resolved_dup_api_status = f"api_error:{e}"
            return []
        except Exception as e:
            diag.resolved_dup_api_status = f"error:{type(e).__name__}:{e}"
            return []
        finally:
            self.config.sonarqube_project_key = temp_project_key
            self.client.config.sonarqube_project_key = temp_project_key

        diag.resolved_dup_api_status = "ok"
        diag.resolved_dup_groups_found = len(response.duplications)

        if not response.duplications:
            return []

        component_key = f"{original_project_key}:{repo_relative}"
        target_ref = response.get_target_file_ref(component_key)
        if target_ref is None:
            return []

        anchor_new_line = min(new_changed_lines)
        findings: list[ResolvedDuplication] = []
        for group in response.duplications:
            resolved = self._resolve_group(
                group, target_ref, response, old_changed_lines, active_dup_ranges, anchor_new_line
            )
            if resolved is not None:
                findings.append(resolved)
        return findings

    def _resolve_group(
        self,
        group: DuplicationGroup,
        target_ref: str,
        response: DuplicationsResponse,
        old_changed_lines: set[int],
        active_dup_ranges: set[tuple[int, int]],
        anchor_new_line: int,
    ) -> ResolvedDuplication | None:
        target_block = group.get_target_block(target_ref)
        if target_block is None:
            return None
        block_lines = set(range(target_block.from_line, target_block.to_line + 1))
        if not block_lines & old_changed_lines:
            return None
        if (target_block.from_line, target_block.to_line) in active_dup_ranges:
            return None
        other_locations = []
        for block in group.get_other_blocks(target_ref):
            file_info = response.get_file_info(block.ref)
            if file_info is None:
                continue
            other_file_path = file_info.key.split(":", 1)[1] if ":" in file_info.key else file_info.key
            other_locations.append(
                DuplicationLocation(
                    file_path=other_file_path,
                    from_line=block.from_line,
                    to_line=block.to_line,
                )
            )
        return ResolvedDuplication(
            main_from_line=target_block.from_line,
            main_to_line=target_block.to_line,
            other_locations=other_locations,
            anchor_new_line=anchor_new_line,
        )

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

    def _to_repo_relative(self, file_path: Path) -> str:
        """Convert a file path to repo-root-relative POSIX string.

        Handles paths from BranchAnalyzer which may be CWD-relative when
        running from a subdirectory, or already repo-relative from repo root.

        Args:
            file_path: A Path that may be CWD-relative or repo-root-relative.

        Returns:
            Repo-root-relative path as a POSIX string (for DiffParser map lookup).
        """
        try:
            repo_root = Path(self.branch_analyzer.repo.working_dir)
            if file_path.is_absolute():
                return str(file_path.relative_to(repo_root))
            resolved = (repo_root / file_path).resolve()
            return str(resolved.relative_to(repo_root.resolve()))
        except (ValueError, TypeError):
            return str(file_path)

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

        Writes JSON to the exact report_file path and derives the markdown
        path from it (same stem, .md extension).

        Args:
            result: Review result to write.
            report_file: Optional path to the report JSON file.
        """
        if report_file is None:
            return

        report_dir = report_file.parent
        report_dir.mkdir(parents=True, exist_ok=True)

        review_result = ReviewResult(
            project_key=result.project_key,
            branch=result.branch,
            base_branch=result.base_branch,
            files=result.files,
            diagnostics=result.diagnostics,
            diff_files_found=result.diff_files_found,
            diff_map_keys=result.diff_map_keys,
            diff_output_sample=result.diff_output_sample,
        )

        _write_json(review_result, report_file)
        md_path = report_file.parent / (report_file.stem + ".md")
        _write_markdown(review_result, md_path)
        console.print(f"[dim]Reports written to {report_file} and {md_path}[/dim]")
