"""Branch PR cleanup orchestration (cleanup-pr command).

Skeleton for the ``cleanup-pr`` workflow. This module owns the strict
preconditions (FR-2 step 1 + 11.A-12), file selection (step 2), the temporary
SonarQube project lifecycle (step 4 + step 7), and the top-level failure policy
(11.A-8 / 11.A-14, same as ``cleanup``). The analysis + per-file fix loop
(FR-2 steps 5-6) is a clearly-marked stub that WO-2b-ii / Phase 05 fills in.
"""

import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel

from vibe_heal.ai_tools.base import AITool
from vibe_heal.config import VibeHealConfig
from vibe_heal.git.branch_analyzer import BranchAnalyzer, BranchNotFoundError
from vibe_heal.git.exceptions import GitOperationError, NotAGitRepositoryError
from vibe_heal.git.manager import GitManager
from vibe_heal.output import dim, error, success, warn
from vibe_heal.sonarqube.analysis_runner import AnalysisResult, AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.project_manager import ProjectManager, TempProjectMetadata


class FileCleanupPrResult(BaseModel):
    """Result of cleaning up a single file (PR-scoped)."""

    file_path: Path
    issues_fixed: int = 0
    issues_out_of_scope: int = 0
    duplications_fixed: int = 0
    duplications_out_of_scope: int = 0
    main_duplications_fixed: int = 0
    success: bool
    error_message: str | None = None


class CleanupPrResult(BaseModel):
    """Result of the branch PR cleanup operation."""

    success: bool
    files_processed: list[FileCleanupPrResult]
    temp_project: TempProjectMetadata | None = None
    analysis_result: AnalysisResult | None = None
    total_issues_fixed: int = 0
    total_duplications_fixed: int = 0
    total_main_duplications_fixed: int = 0
    external_files_touched: list[Path] = []
    error_message: str | None = None


class CleanupPrOrchestrator:
    """Orchestrates the branch PR cleanup workflow.

    Coordinates:
    - Strict preconditions (repo, base branch, AI tool, clean tree, fetch, up-to-date)
    - File selection (modified vs. base)
    - Temporary project creation
    - SonarQube analysis + per-file fix loop (stub, Phase 05)
    - Project cleanup
    """

    def __init__(
        self,
        config: VibeHealConfig,
        client: SonarQubeClient,
        ai_tool: AITool,
    ) -> None:
        """Initialize the cleanup-pr orchestrator.

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
        self.git_manager = GitManager(Path.cwd(), pre_commit_command=config.pre_commit_command)

    async def cleanup_pr(
        self,
        base_branch: str = "origin/main",
        max_iterations: int = 10,
        file_patterns: list[str] | None = None,
        min_severity: str | None = None,
        include_main_duplications: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> CleanupPrResult:
        """Clean up SonarQube issues and duplications scoped to branch changes.

        The strict preconditions (FR-2 step 1 + 11.A-12) run up front, before any
        SonarQube work: the tree must be a clean git repository sitting on top of
        a freshly fetched base branch, with an available AI tool unless this is a
        dry run. ``include_main_duplications`` is accepted for forward
        compatibility but is not acted on in this phase (behaves as False).

        Args:
            base_branch: Base branch to fetch and compare against (default: origin/main)
            max_iterations: Maximum analysis iterations for the whole branch (default: 10)
            file_patterns: Optional list of glob patterns to filter files
            min_severity: Minimum issue severity to fix (passed through to the loop)
            include_main_duplications: Accepted but unused in this phase (WO-3)
            dry_run: Preview without committing (skips the AI-tool availability check)
            verbose: Enable verbose output

        Returns:
            CleanupPrResult with success status and details
        """
        # FR-2 step 1 + 11.A-12: strict preconditions, all before any SonarQube work.
        self._validate_preconditions(base_branch, dry_run)
        self._fetch_base_branch(base_branch)
        self._check_up_to_date_with_base(base_branch)

        temp_project: TempProjectMetadata | None = None
        original_project_key: str | None = None
        files_processed: list[FileCleanupPrResult] = []

        try:
            # Step 2: select and filter the modified files.
            modified_files = self._select_files(base_branch, file_patterns)

            if not modified_files:
                return CleanupPrResult(success=True, files_processed=[])

            # Step 4: create the temporary SonarQube project.
            temp_project = await self._create_temp_project()

            # Project-key override: route the whole run to the temp project. Both keys
            # are restored in the finally block on every path (same pattern as cleanup).
            original_project_key = self.config.sonarqube_project_key
            self.config.sonarqube_project_key = temp_project.project_key
            self.client.config.sonarqube_project_key = temp_project.project_key

            # Steps 5-6: iteration/fix loop (analysis + per-file duplications-then-issues).
            (
                files_processed,
                analysis_result,
                external_files_touched,
            ) = await self._run_iteration_loop(
                modified_files=modified_files,
                temp_project=temp_project,
                max_iterations=max_iterations,
                min_severity=min_severity,
                dry_run=dry_run,
                verbose=verbose,
            )

            return CleanupPrResult(
                success=True,
                files_processed=files_processed,
                temp_project=temp_project,
                analysis_result=analysis_result,
                total_issues_fixed=sum(f.issues_fixed for f in files_processed),
                total_duplications_fixed=sum(f.duplications_fixed for f in files_processed),
                total_main_duplications_fixed=sum(f.main_duplications_fixed for f in files_processed),
                external_files_touched=external_files_touched,
            )

        except Exception as e:
            return CleanupPrResult(
                success=False,
                files_processed=files_processed,
                temp_project=temp_project,
                error_message=f"Cleanup failed: {e}",
            )

        finally:
            # Restore the original project key on every path.
            if original_project_key is not None:
                self.config.sonarqube_project_key = original_project_key
                self.client.config.sonarqube_project_key = original_project_key
            # Step 7: always clean up the temp project.
            await self._cleanup_temp_project(temp_project)

    # ------------------------------------------------------------------
    # Preconditions (FR-2 step 1 + 11.A-12)
    # ------------------------------------------------------------------

    def _validate_preconditions(self, base_branch: str, dry_run: bool) -> None:
        """Validate the strict preconditions before any SonarQube work.

        Args:
            base_branch: Base branch to compare against.
            dry_run: Whether this is a dry run (skips the AI-tool availability check).

        Raises:
            NotAGitRepositoryError: If not in a git repository.
            BranchNotFoundError: If the base branch does not exist.
            RuntimeError: If the AI tool is unavailable and this is not a dry run.
            DirtyWorkingDirectoryError: If the working tree has modified or staged files.
        """
        if not self.git_manager.is_repository():
            msg = "Not a Git repository"
            raise NotAGitRepositoryError(msg)

        if not self.branch_analyzer.validate_branch_exists(base_branch):
            msg = f"Branch '{base_branch}' does not exist in repository"
            raise BranchNotFoundError(msg)

        if not dry_run and not self.ai_tool.is_available():
            msg = f"{self.ai_tool.tool_type.display_name} is not available"
            raise RuntimeError(msg)

        # Strict clean working tree (untracked files are fine), checked once up front.
        self.git_manager.require_clean_working_directory()

    @staticmethod
    def _split_remote_ref(base_branch: str) -> tuple[str, str]:
        """Split a base ref into ``(remote, branch)``.

        ``origin/main`` -> ``("origin", "main")``. A bare name (no slash) assumes
        the default remote ``origin``.
        """
        if "/" in base_branch:
            remote, branch = base_branch.split("/", 1)
            return remote, branch
        return "origin", base_branch

    def _fetch_base_branch(self, base_branch: str) -> None:
        """Fetch the base ref's remote ref; refuse to run on any fetch failure.

        Runs even in dry-run. On any failure (offline, auth, missing remote) the
        run is refused with a domain error before any SonarQube work — no fallback
        to the local ref.

        Args:
            base_branch: Base branch to fetch (e.g. 'origin/main').

        Raises:
            GitOperationError: If the git binary is unavailable or the fetch fails.
        """
        remote, branch = self._split_remote_ref(base_branch)
        cmd = shlex.split(f"git fetch {remote} {branch}")
        dim(f"Fetching {base_branch} ...")
        try:
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # noqa: S603
        except OSError as e:
            msg = f"Failed to run 'git fetch {remote} {branch}': {e}"
            error(msg)
            raise GitOperationError(msg) from e
        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace").strip() if result.stderr else ""
            detail = stderr_text or f"'git fetch {remote} {branch}' exited with code {result.returncode}"
            msg = f"Refusing to run: unable to fetch {base_branch}. {detail}"
            error(msg)
            raise GitOperationError(msg)

    def _check_up_to_date_with_base(self, base_branch: str) -> None:
        """Ensure HEAD sits on top of the base branch (base is an ancestor of HEAD).

        A merged-in base counts; linear history is not required. Refuses to run
        otherwise, before any SonarQube work.

        Args:
            base_branch: Base branch to check against.

        Raises:
            GitOperationError: If HEAD is not up to date with the base branch.
        """
        cmd = shlex.split(f"git merge-base --is-ancestor {base_branch} HEAD")
        dim(f"Checking that HEAD is up to date with {base_branch} ...")
        try:
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        except OSError as e:
            msg = f"Failed to check ancestry with {base_branch}: {e}"
            error(msg)
            raise GitOperationError(msg) from e
        if result.returncode != 0:
            msg = f"Branch is not up to date with {base_branch}; rebase or merge {base_branch} first"
            error(msg)
            raise GitOperationError(msg)

    # ------------------------------------------------------------------
    # File selection (FR-2 step 2)
    # ------------------------------------------------------------------

    def _select_files(self, base_branch: str, file_patterns: list[str] | None) -> list[Path]:
        """Select the modified files vs. the base branch, optionally pattern-filtered.

        Uses ``Path.match`` (the cleanup/review behavior), not ``fnmatch``.

        Args:
            base_branch: Base branch to compare against.
            file_patterns: Optional glob patterns to filter files.

        Returns:
            The selected modified files (empty when nothing is in scope).
        """
        dim(f"Analyzing branch against {base_branch}...")
        modified_files = self.branch_analyzer.get_modified_files(base_branch)
        dim(f"Found {len(modified_files)} modified files")

        if not modified_files:
            return []

        if file_patterns:
            dim(f"Filtering files with patterns: {file_patterns}")
            modified_files = self._filter_files(modified_files, file_patterns)
            dim(f"After filtering: {len(modified_files)} files remain")

        if modified_files:
            dim("Files to process:")
            for f in modified_files:
                dim(f"  - {f}")

        return modified_files

    def _filter_files(self, files: list[Path], patterns: list[str]) -> list[Path]:
        """Filter files by glob patterns using ``Path.match``.

        Args:
            files: List of file paths.
            patterns: List of glob patterns (e.g. ["*.py", "src/**/*.ts"]).

        Returns:
            Files matching at least one pattern.
        """
        filtered = []
        for file_path in files:
            for pattern in patterns:
                if file_path.match(pattern):
                    filtered.append(file_path)
                    break
        return filtered

    # ------------------------------------------------------------------
    # Temp project lifecycle (FR-2 step 4 + step 7)
    # ------------------------------------------------------------------

    async def _create_temp_project(self) -> TempProjectMetadata:
        """Create a temporary SonarQube project for analysis.

        Returns:
            Metadata for the created temp project.
        """
        current_branch = self.branch_analyzer.get_current_branch()
        user_email = self.branch_analyzer.get_user_email()

        return await self.project_manager.create_temp_project_with_settings(
            base_key=self.config.sonarqube_project_key,
            branch_name=current_branch,
            user_email=user_email,
            command_name="cleanup-pr",
        )

    async def _cleanup_temp_project(self, temp_project: TempProjectMetadata | None) -> None:
        """Delete the temp project; a deletion failure is a warning, not an error.

        Args:
            temp_project: Temp project metadata (None if not created).
        """
        if temp_project:
            try:
                dim(f"Deleting temporary project: {temp_project.project_key}")
                await self.project_manager.delete_project(temp_project.project_key)
                success("✓ Temporary project deleted")
            except Exception as e:
                warn(f"Warning: Failed to delete temporary project: {e}")

    # ------------------------------------------------------------------
    # Iteration/fix loop (FR-2 steps 5-6) — STUB
    # ------------------------------------------------------------------

    async def _run_iteration_loop(
        self,
        modified_files: list[Path],
        temp_project: TempProjectMetadata,
        max_iterations: int,
        min_severity: str | None,
        dry_run: bool,
        verbose: bool,
    ) -> tuple[list[FileCleanupPrResult], AnalysisResult | None, list[Path]]:
        """Run the analysis + per-file duplications-then-issues fix loop (FR-2 steps 5-6).

        Args:
            modified_files: Selected files to process.
            temp_project: Active temp project (keys are already overridden by the caller).
            max_iterations: Maximum analysis iterations for the whole branch.
            min_severity: Minimum issue severity to fix.
            dry_run: Preview without committing.
            verbose: Enable verbose output.

        Returns:
            Tuple of (per-file results, analysis result, external files touched).
        """
        # WO-2b-ii / Phase 05: implement the iteration loop here.
        files = [FileCleanupPrResult(file_path=f, success=True) for f in modified_files]
        return files, None, []
