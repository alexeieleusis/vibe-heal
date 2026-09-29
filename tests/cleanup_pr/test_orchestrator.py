"""Tests for CleanupPrOrchestrator class."""

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.shared_orchestrator_tests import BaseTestCreateTempProject
from vibe_heal.ai_tools.base import AITool
from vibe_heal.cleanup_pr.orchestrator import (
    CleanupPrOrchestrator,
    FileCleanupPrResult,
)
from vibe_heal.config import VibeHealConfig
from vibe_heal.git.branch_analyzer import BranchAnalyzer
from vibe_heal.git.exceptions import DirtyWorkingDirectoryError, GitOperationError
from vibe_heal.git.manager import GitManager
from vibe_heal.sonarqube.analysis_runner import AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.project_manager import ProjectManager, TempProjectMetadata


@pytest.fixture
def config() -> VibeHealConfig:
    """Create test configuration."""
    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_token="test-token",
        sonarqube_project_key="my-project",
    )


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock SonarQubeClient.

    ``config`` is an instance attribute (not a class attribute) so the spec does
    not expose it; it is set up front so the orchestrator's key override/restore
    can read and write ``client.config.sonarqube_project_key``.
    """
    client = AsyncMock(spec=SonarQubeClient)
    client.config = MagicMock()
    return client


@pytest.fixture
def mock_ai_tool() -> MagicMock:
    """Create a mock AITool."""
    return MagicMock(spec=AITool)


@pytest.fixture
def orchestrator(
    config: VibeHealConfig,
    mock_client: AsyncMock,
    mock_ai_tool: MagicMock,
) -> CleanupPrOrchestrator:
    """Create CleanupPrOrchestrator with mocked dependencies."""
    return CleanupPrOrchestrator(config, mock_client, mock_ai_tool)


def _git_result(returncode: int, stderr: bytes = b"") -> subprocess.CompletedProcess:
    """Build a subprocess result with the given exit code and stderr."""
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=None, stderr=stderr)


@contextmanager
def _preconditions_pass(
    orchestrator: CleanupPrOrchestrator,
    fetch_rc: int = 0,
    ancestor_rc: int = 0,
    dirty: bool = False,
) -> Iterator[None]:
    """Make the up-front preconditions pass, with controllable git exit codes.

    ``fetch_rc`` controls the ``git fetch`` exit code, ``ancestor_rc`` the
    ``git merge-base --is-ancestor`` exit code, and ``dirty`` whether the strict
    clean-tree check raises.
    """

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if "fetch" in cmd:
            stderr = b"fatal: unable to access 'https://example.com/'" if fetch_rc else b""
            return _git_result(fetch_rc, stderr=stderr)
        if "merge-base" in cmd:
            return _git_result(ancestor_rc)
        msg = f"Unexpected git command: {cmd}"
        raise AssertionError(msg)

    clean_side_effect = DirtyWorkingDirectoryError("dirty working tree") if dirty else None
    with (
        patch.object(orchestrator.git_manager, "is_repository", return_value=True),
        patch.object(orchestrator.branch_analyzer, "validate_branch_exists", return_value=True),
        patch.object(orchestrator.ai_tool, "is_available", return_value=True),
        patch.object(orchestrator.git_manager, "require_clean_working_directory", side_effect=clean_side_effect),
        patch("vibe_heal.cleanup_pr.orchestrator.subprocess.run", side_effect=fake_run),
    ):
        yield


class TestCleanupPrOrchestratorInit:
    """Tests for CleanupPrOrchestrator initialization."""

    def test_init(
        self,
        config: VibeHealConfig,
        mock_client: AsyncMock,
        mock_ai_tool: MagicMock,
    ) -> None:
        """Test CleanupPrOrchestrator initialization."""
        orchestrator = CleanupPrOrchestrator(config, mock_client, mock_ai_tool)

        assert orchestrator.config == config
        assert orchestrator.client == mock_client
        assert orchestrator.ai_tool == mock_ai_tool
        assert isinstance(orchestrator.project_manager, ProjectManager)
        assert isinstance(orchestrator.analysis_runner, AnalysisRunner)
        assert isinstance(orchestrator.branch_analyzer, BranchAnalyzer)
        assert isinstance(orchestrator.git_manager, GitManager)


class TestCleanupPrPreconditions:
    """Strict preconditions are enforced before any SonarQube work."""

    @pytest.mark.asyncio
    async def test_fetch_failure_refuses_before_sonarqube(
        self,
        orchestrator: CleanupPrOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """A failed fetch refuses the run with a domain error, before SonarQube work."""
        with _preconditions_pass(orchestrator, fetch_rc=1), pytest.raises(GitOperationError, match="fetch"):
            await orchestrator.cleanup_pr()

        # No SonarQube client call happened.
        assert mock_client.method_calls == []

    @pytest.mark.asyncio
    async def test_fetch_failure_uses_parsed_remote_and_branch(
        self,
        orchestrator: CleanupPrOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """The fetch command is built from the parsed remote/branch of the base ref."""
        with _preconditions_pass(orchestrator, fetch_rc=1), pytest.raises(GitOperationError):
            await orchestrator.cleanup_pr(base_branch="upstream/develop")

        assert mock_client.method_calls == []

    @pytest.mark.asyncio
    async def test_not_up_to_date_refuses_before_sonarqube(
        self,
        orchestrator: CleanupPrOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """A non-ancestor (not up to date) base refuses the run, before SonarQube work."""
        with _preconditions_pass(orchestrator, ancestor_rc=1), pytest.raises(GitOperationError, match="not up to date"):
            await orchestrator.cleanup_pr()

        # No SonarQube client call happened.
        assert mock_client.method_calls == []

    @pytest.mark.asyncio
    async def test_dirty_tree_raises_before_sonarqube(
        self,
        orchestrator: CleanupPrOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """A dirty working tree raises DirtyWorkingDirectoryError, before SonarQube work."""
        with _preconditions_pass(orchestrator, dirty=True), pytest.raises(DirtyWorkingDirectoryError):
            await orchestrator.cleanup_pr()

        # No SonarQube client call happened.
        assert mock_client.method_calls == []


class TestCleanupPrFileSelection:
    """File selection (FR-2 step 2)."""

    @pytest.mark.asyncio
    async def test_empty_file_list_returns_success_with_zero_counts(
        self,
        orchestrator: CleanupPrOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """An empty selection returns a successful result with zero counts."""
        with (
            _preconditions_pass(orchestrator),
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[],
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project_with_settings",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await orchestrator.cleanup_pr()

        assert result.success is True
        assert result.files_processed == []
        assert result.total_issues_fixed == 0
        assert result.total_duplications_fixed == 0
        assert result.total_main_duplications_fixed == 0
        assert result.external_files_touched == []
        assert result.temp_project is None
        # No temp project was created and no SonarQube work happened.
        mock_create.assert_not_called()
        assert mock_client.method_calls == []

    @pytest.mark.asyncio
    async def test_empty_file_list_after_pattern_filtering(
        self,
        orchestrator: CleanupPrOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """Files filtered out by patterns also return a successful zero-count result."""
        with (
            _preconditions_pass(orchestrator),
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/a.py"), Path("src/b.py")],
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project_with_settings",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            result = await orchestrator.cleanup_pr(file_patterns=["*.ts"])

        assert result.success is True
        assert result.files_processed == []
        assert result.total_issues_fixed == 0
        mock_create.assert_not_called()
        assert mock_client.method_calls == []

    def test_filter_files_uses_path_match(self, orchestrator: CleanupPrOrchestrator) -> None:
        """_filter_files matches with Path.match (not fnmatch), like cleanup/review."""
        files = [Path("src/module/a.py"), Path("src/b.py"), Path("data/c.json")]
        result = orchestrator._filter_files(files, ["src/**/*.py"])
        assert result == [Path("src/module/a.py")]

    def test_filter_files_multiple_patterns(self, orchestrator: CleanupPrOrchestrator) -> None:
        """A file is kept if it matches any of the patterns."""
        files = [Path("src/a.py"), Path("src/b.ts"), Path("data/c.json")]
        result = orchestrator._filter_files(files, ["*.py", "*.ts"])
        assert result == [Path("src/a.py"), Path("src/b.ts")]


class TestCleanupPrTempProjectLifecycle:
    """Project-key override/restore and temp-project cleanup."""

    @pytest.mark.asyncio
    async def test_project_keys_restored_after_exception(
        self,
        orchestrator: CleanupPrOrchestrator,
        config: VibeHealConfig,
        mock_client: AsyncMock,
        temp_project: TempProjectMetadata,
    ) -> None:
        """Both config and client project keys are restored after an exception."""
        original_key = config.sonarqube_project_key
        with (
            _preconditions_pass(orchestrator),
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/a.py")],
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project_with_settings",
                new_callable=AsyncMock,
                return_value=temp_project,
            ),
            patch.object(
                orchestrator,
                "_run_iteration_loop",
                new_callable=AsyncMock,
                side_effect=Exception("boom"),
            ),
            patch.object(orchestrator.project_manager, "delete_project", new_callable=AsyncMock),
        ):
            result = await orchestrator.cleanup_pr()

        assert result.success is False
        assert "boom" in result.error_message
        # Both keys restored to the original value on every path.
        assert config.sonarqube_project_key == original_key
        assert mock_client.config.sonarqube_project_key == original_key

    @pytest.mark.asyncio
    async def test_temp_project_deleted_after_failed_analysis(
        self,
        orchestrator: CleanupPrOrchestrator,
        temp_project: TempProjectMetadata,
    ) -> None:
        """The temp project is deleted when the loop (analysis) fails."""
        with (
            _preconditions_pass(orchestrator),
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/a.py")],
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project_with_settings",
                new_callable=AsyncMock,
                return_value=temp_project,
            ),
            patch.object(
                orchestrator,
                "_run_iteration_loop",
                new_callable=AsyncMock,
                side_effect=Exception("Analysis failed"),
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.cleanup_pr()

        assert result.success is False
        assert "Analysis failed" in result.error_message
        mock_delete.assert_called_once_with(temp_project.project_key)

    @pytest.mark.asyncio
    async def test_deletion_failure_is_only_a_warning(
        self,
        orchestrator: CleanupPrOrchestrator,
        temp_project: TempProjectMetadata,
    ) -> None:
        """A temp-project deletion failure does not fail the overall run."""
        with (
            _preconditions_pass(orchestrator),
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/a.py")],
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project_with_settings",
                new_callable=AsyncMock,
                return_value=temp_project,
            ),
            patch.object(
                orchestrator,
                "_run_iteration_loop",
                new_callable=AsyncMock,
                return_value=([FileCleanupPrResult(file_path=Path("src/a.py"), success=True)], None, []),
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
                side_effect=Exception("delete failed"),
            ),
        ):
            result = await orchestrator.cleanup_pr()

        # Deletion is a warning, not an error, so the run still succeeds.
        assert result.success is True
        assert result.total_issues_fixed == 0


class TestCreateTempProject(BaseTestCreateTempProject):
    """Tests for _create_temp_project method."""

    pass
