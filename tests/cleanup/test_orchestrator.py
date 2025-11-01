"""Tests for CleanupOrchestrator class."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibe_heal.ai_tools.base import AITool
from vibe_heal.cleanup.orchestrator import (
    CleanupOrchestrator,
)
from vibe_heal.config import VibeHealConfig
from vibe_heal.git.branch_analyzer import BranchAnalyzer
from vibe_heal.git.manager import GitManager
from vibe_heal.sonarqube.analysis_runner import AnalysisResult, AnalysisRunner
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
    """Create a mock SonarQubeClient."""
    return AsyncMock(spec=SonarQubeClient)


@pytest.fixture
def mock_ai_tool() -> MagicMock:
    """Create a mock AITool."""
    return MagicMock(spec=AITool)


@pytest.fixture
def orchestrator(
    config: VibeHealConfig,
    mock_client: AsyncMock,
    mock_ai_tool: MagicMock,
) -> CleanupOrchestrator:
    """Create CleanupOrchestrator with mocked dependencies."""
    return CleanupOrchestrator(config, mock_client, mock_ai_tool)


@pytest.fixture
def temp_project() -> TempProjectMetadata:
    """Create a test temporary project metadata."""
    return TempProjectMetadata(
        project_key="test-project-user_example_com-feature",
        project_name="Test Project (user@example.com - feature)",
        created_at="2024-01-01T00:00:00Z",
        base_project_key="test-project",
        branch_name="feature",
        user_email="user@example.com",
    )


class TestCleanupOrchestratorInit:
    """Tests for CleanupOrchestrator initialization."""

    def test_init(
        self,
        config: VibeHealConfig,
        mock_client: AsyncMock,
        mock_ai_tool: MagicMock,
    ) -> None:
        """Test CleanupOrchestrator initialization."""
        orchestrator = CleanupOrchestrator(config, mock_client, mock_ai_tool)

        assert orchestrator.config == config
        assert orchestrator.client == mock_client
        assert orchestrator.ai_tool == mock_ai_tool
        assert isinstance(orchestrator.project_manager, ProjectManager)
        assert isinstance(orchestrator.analysis_runner, AnalysisRunner)
        assert isinstance(orchestrator.branch_analyzer, BranchAnalyzer)
        assert isinstance(orchestrator.git_manager, GitManager)


class TestCleanupBranch:
    """Tests for cleanup_branch method."""

    @pytest.mark.asyncio
    async def test_no_modified_files(self, orchestrator: CleanupOrchestrator) -> None:
        """Test when branch has no modified files."""
        with patch.object(
            orchestrator.branch_analyzer,
            "get_modified_files",
            return_value=[],
        ):
            result = await orchestrator.cleanup_branch()

        assert result.success is True
        assert result.files_processed == []
        assert result.total_issues_fixed == 0
        assert result.temp_project is None

    @pytest.mark.asyncio
    async def test_no_files_after_filtering(self, orchestrator: CleanupOrchestrator) -> None:
        """Test when file patterns filter out all files."""
        with patch.object(
            orchestrator.branch_analyzer,
            "get_modified_files",
            return_value=[Path("test.txt"), Path("data.json")],
        ):
            result = await orchestrator.cleanup_branch(file_patterns=["*.py"])

        assert result.success is True
        assert result.files_processed == []
        assert result.total_issues_fixed == 0
        assert result.temp_project is None

    @pytest.mark.asyncio
    async def test_initial_analysis_fails(
        self,
        orchestrator: CleanupOrchestrator,
        temp_project: TempProjectMetadata,
    ) -> None:
        """Test when initial SonarQube analysis fails."""
        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file1.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature-branch",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(
                    success=False,
                    error_message="Analysis failed",
                ),
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.cleanup_branch()

        assert result.success is False
        assert "Analysis failed at iteration 1" in result.error_message
        assert result.temp_project == temp_project
        mock_delete.assert_called_once_with(temp_project.project_key)

    @pytest.mark.asyncio
    async def test_cleanup_exception_handling(
        self,
        orchestrator: CleanupOrchestrator,
    ) -> None:
        """Test that exceptions are handled gracefully."""
        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                side_effect=Exception("Git error"),
            ),
        ):
            result = await orchestrator.cleanup_branch()

        assert result.success is False
        assert "Cleanup failed: Git error" in result.error_message

    @pytest.mark.asyncio
    async def test_project_cleanup_on_exception(
        self,
        orchestrator: CleanupOrchestrator,
        temp_project: TempProjectMetadata,
    ) -> None:
        """Test that temporary project is deleted even on exception."""
        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file1.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature-branch",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                side_effect=Exception("Analysis error"),
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.cleanup_branch()

        assert result.success is False
        # Project should still be deleted
        mock_delete.assert_called_once_with(temp_project.project_key)


# Note: _cleanup_file method was removed in favor of integrated loop in cleanup_branch
# Tests for the new integrated workflow are in TestCleanupBranch


class TestFilterFiles:
    """Tests for _filter_files method."""

    def test_filter_single_pattern(self, orchestrator: CleanupOrchestrator) -> None:
        """Test filtering with a single pattern."""
        files = [
            Path("src/file1.py"),
            Path("src/file2.ts"),
            Path("test/test1.py"),
        ]

        result = orchestrator._filter_files(files, ["*.py"])

        assert len(result) == 2
        assert Path("src/file1.py") in result
        assert Path("test/test1.py") in result

    def test_filter_multiple_patterns(self, orchestrator: CleanupOrchestrator) -> None:
        """Test filtering with multiple patterns."""
        files = [
            Path("src/file1.py"),
            Path("src/file2.ts"),
            Path("src/file3.js"),
            Path("test.txt"),
        ]

        result = orchestrator._filter_files(files, ["*.py", "*.ts"])

        assert len(result) == 2
        assert Path("src/file1.py") in result
        assert Path("src/file2.ts") in result

    def test_filter_glob_pattern(self, orchestrator: CleanupOrchestrator) -> None:
        """Test filtering with glob patterns."""
        files = [
            Path("src/module/file1.py"),
            Path("src/file2.py"),
            Path("test/test1.py"),
        ]

        result = orchestrator._filter_files(files, ["src/**/*.py"])

        # Path.match only matches the nested module file
        assert len(result) == 1
        assert Path("src/module/file1.py") in result

    def test_filter_no_matches(self, orchestrator: CleanupOrchestrator) -> None:
        """Test filtering when no files match."""
        files = [
            Path("src/file1.py"),
            Path("src/file2.py"),
        ]

        result = orchestrator._filter_files(files, ["*.ts"])

        assert len(result) == 0

    def test_filter_all_match(self, orchestrator: CleanupOrchestrator) -> None:
        """Test filtering when all files match."""
        files = [
            Path("file1.py"),
            Path("file2.py"),
            Path("file3.py"),
        ]

        result = orchestrator._filter_files(files, ["*.py"])

        assert len(result) == 3
