"""Tests for CleanupOrchestrator class."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibe_heal.ai_tools.base import AITool
from vibe_heal.cleanup.orchestrator import (
    CleanupOrchestrator,
    FileCleanupResult,
)
from vibe_heal.config import VibeHealConfig
from vibe_heal.git.branch_analyzer import BranchAnalyzer
from vibe_heal.git.manager import GitManager
from vibe_heal.models import FixSummary
from vibe_heal.orchestrator import VibeHealOrchestrator
from vibe_heal.sonarqube.analysis_runner import AnalysisResult, AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.models import SonarQubeIssue
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
    async def test_initial_analysis_fails(self, orchestrator: CleanupOrchestrator) -> None:
        """Test when initial SonarQube analysis fails."""
        temp_project = TempProjectMetadata(
            project_key="test-project-user_example_com-feature",
            project_name="Test Project (user@example.com - feature)",
            created_at="2024-01-01T00:00:00Z",
            base_project_key="test-project",
            branch_name="feature",
            user_email="user@example.com",
        )

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
        assert "Initial analysis failed" in result.error_message
        assert result.temp_project == temp_project
        mock_delete.assert_called_once_with(temp_project.project_key)

    @pytest.mark.asyncio
    async def test_successful_cleanup_single_file(
        self,
        orchestrator: CleanupOrchestrator,
    ) -> None:
        """Test successful cleanup of a single file."""
        temp_project = TempProjectMetadata(
            project_key="test-project-user_example_com-feature",
            project_name="Test Project (user@example.com - feature)",
            created_at="2024-01-01T00:00:00Z",
            base_project_key="test-project",
            branch_name="feature",
            user_email="user@example.com",
        )

        file_path = Path("src/file1.py")

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[file_path],
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
                    success=True,
                    task_id="AY123",
                    dashboard_url="https://sonar.test.com/dashboard?id=test",
                ),
            ),
            patch.object(
                orchestrator,
                "_cleanup_file",
                return_value=FileCleanupResult(
                    file_path=file_path,
                    issues_fixed=5,
                    success=True,
                ),
            ) as mock_cleanup_file,
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.cleanup_branch()

        assert result.success is True
        assert len(result.files_processed) == 1
        assert result.files_processed[0].file_path == file_path
        assert result.files_processed[0].issues_fixed == 5
        assert result.total_issues_fixed == 5
        mock_cleanup_file.assert_called_once()
        mock_delete.assert_called_once_with(temp_project.project_key)

    @pytest.mark.asyncio
    async def test_successful_cleanup_multiple_files(
        self,
        orchestrator: CleanupOrchestrator,
    ) -> None:
        """Test successful cleanup of multiple files."""
        temp_project = TempProjectMetadata(
            project_key="test-project-user_example_com-feature",
            project_name="Test Project (user@example.com - feature)",
            created_at="2024-01-01T00:00:00Z",
            base_project_key="test-project",
            branch_name="feature",
            user_email="user@example.com",
        )

        files = [Path("src/file1.py"), Path("src/file2.py"), Path("src/file3.py")]

        cleanup_results = [
            FileCleanupResult(file_path=files[0], issues_fixed=3, success=True),
            FileCleanupResult(file_path=files[1], issues_fixed=0, success=True),
            FileCleanupResult(file_path=files[2], issues_fixed=7, success=True),
        ]

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=files,
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
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
            patch.object(
                orchestrator,
                "_cleanup_file",
                side_effect=cleanup_results,
            ) as mock_cleanup_file,
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ),
        ):
            result = await orchestrator.cleanup_branch()

        assert result.success is True
        assert len(result.files_processed) == 3
        assert result.total_issues_fixed == 10  # 3 + 0 + 7
        assert mock_cleanup_file.call_count == 3

    @pytest.mark.asyncio
    async def test_cleanup_with_file_patterns(
        self,
        orchestrator: CleanupOrchestrator,
    ) -> None:
        """Test cleanup with file pattern filtering."""
        temp_project = TempProjectMetadata(
            project_key="test-project-user_example_com-feature",
            project_name="Test Project (user@example.com - feature)",
            created_at="2024-01-01T00:00:00Z",
            base_project_key="test-project",
            branch_name="feature",
            user_email="user@example.com",
        )

        all_files = [Path("src/file1.py"), Path("src/file2.ts"), Path("test.py")]

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=all_files,
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
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
            patch.object(
                orchestrator,
                "_cleanup_file",
                return_value=FileCleanupResult(
                    file_path=Path("dummy"),
                    issues_fixed=1,
                    success=True,
                ),
            ) as mock_cleanup_file,
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ),
        ):
            result = await orchestrator.cleanup_branch(file_patterns=["*.py"])

        assert result.success is True
        # Should only process Python files
        assert mock_cleanup_file.call_count == 2

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
    ) -> None:
        """Test that temporary project is deleted even on exception."""
        temp_project = TempProjectMetadata(
            project_key="test-project-user_example_com-feature",
            project_name="Test Project (user@example.com - feature)",
            created_at="2024-01-01T00:00:00Z",
            base_project_key="test-project",
            branch_name="feature",
            user_email="user@example.com",
        )

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


class TestCleanupFile:
    """Tests for _cleanup_file method."""

    @pytest.mark.asyncio
    async def test_no_issues_found(
        self,
        orchestrator: CleanupOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """Test when file has no issues."""
        file_path = Path("src/file1.py")

        with (
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
        ):
            mock_client.get_issues_for_file.return_value = []

            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=10,
            )

        assert result.success is True
        assert result.file_path == file_path
        assert result.issues_fixed == 0
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_analysis_fails(
        self,
        orchestrator: CleanupOrchestrator,
    ) -> None:
        """Test when analysis fails."""
        file_path = Path("src/file1.py")

        with patch.object(
            orchestrator.analysis_runner,
            "run_analysis",
            return_value=AnalysisResult(
                success=False,
                error_message="Analysis failed",
            ),
        ):
            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=10,
            )

        assert result.success is False
        assert "Analysis failed at iteration 1" in result.error_message

    @pytest.mark.asyncio
    async def test_single_iteration_fixes_all(
        self,
        orchestrator: CleanupOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """Test when all issues are fixed in one iteration."""
        file_path = Path("src/file1.py")

        # Create mock issues
        issues = [
            SonarQubeIssue(
                key="issue1",
                rule="python:S1234",
                message="Test issue",
                component="my-project:src/file1.py",
                line=10,
                status="OPEN",
            ),
        ]

        with (
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
            patch(
                "vibe_heal.cleanup.orchestrator.VibeHealOrchestrator",
            ) as mock_orchestrator_class,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # First call returns issues, second call returns empty (all fixed)
            mock_client.get_issues_for_file.side_effect = [issues, []]

            mock_orchestrator = AsyncMock(spec=VibeHealOrchestrator)
            mock_orchestrator.fix_file.return_value = FixSummary(
                total_issues=1,
                fixed=1,
            )
            mock_orchestrator_class.return_value = mock_orchestrator

            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=10,
            )

        assert result.success is True
        assert result.file_path == file_path
        assert result.issues_fixed == 1
        mock_orchestrator.fix_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_iterations(
        self,
        orchestrator: CleanupOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """Test multiple iterations to fix all issues."""
        file_path = Path("src/file1.py")

        issue1 = SonarQubeIssue(
            key="issue1",
            rule="python:S1234",
            message="Issue 1",
            component="my-project:src/file1.py",
            line=10,
            status="OPEN",
        )
        issue2 = SonarQubeIssue(
            key="issue2",
            rule="python:S5678",
            message="Issue 2",
            component="my-project:src/file1.py",
            line=20,
            status="OPEN",
        )

        with (
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
            patch(
                "vibe_heal.cleanup.orchestrator.VibeHealOrchestrator",
            ) as mock_orchestrator_class,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # Iteration 1: 2 issues, Iteration 2: 1 issue, Iteration 3: 0 issues
            mock_client.get_issues_for_file.side_effect = [
                [issue1, issue2],
                [issue2],
                [],
            ]

            mock_orchestrator = AsyncMock(spec=VibeHealOrchestrator)
            mock_orchestrator.fix_file.side_effect = [
                FixSummary(total_issues=1, fixed=1),
                FixSummary(total_issues=1, fixed=1),
            ]
            mock_orchestrator_class.return_value = mock_orchestrator

            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=10,
            )

        assert result.success is True
        assert result.issues_fixed == 2
        assert mock_orchestrator.fix_file.call_count == 2

    @pytest.mark.asyncio
    async def test_max_iterations_reached(
        self,
        orchestrator: CleanupOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """Test when max iterations is reached."""
        file_path = Path("src/file1.py")

        issue = SonarQubeIssue(
            key="issue1",
            rule="python:S1234",
            message="Persistent issue",
            component="my-project:src/file1.py",
            line=10,
            status="OPEN",
        )

        with (
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
            patch(
                "vibe_heal.cleanup.orchestrator.VibeHealOrchestrator",
            ) as mock_orchestrator_class,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # Always return the same issue (can't be fixed)
            mock_client.get_issues_for_file.return_value = [issue]

            mock_orchestrator = AsyncMock(spec=VibeHealOrchestrator)
            mock_orchestrator.fix_file.return_value = FixSummary(
                total_issues=1,
                fixed=0,  # No issues actually fixed
            )
            mock_orchestrator_class.return_value = mock_orchestrator

            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=3,
            )

        # Should succeed but with 0 issues fixed after hitting max iterations
        assert result.success is True
        assert result.issues_fixed == 0
        assert mock_orchestrator.fix_file.call_count == 3

    @pytest.mark.asyncio
    async def test_fix_fails(
        self,
        orchestrator: CleanupOrchestrator,
        mock_client: AsyncMock,
    ) -> None:
        """Test when fix operation fails."""
        file_path = Path("src/file1.py")

        issue = SonarQubeIssue(
            key="issue1",
            rule="python:S1234",
            message="Test issue",
            component="my-project:src/file1.py",
            line=10,
            status="OPEN",
        )

        with (
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="AY123"),
            ),
            patch(
                "vibe_heal.cleanup.orchestrator.VibeHealOrchestrator",
            ) as mock_orchestrator_class,
        ):
            mock_client.get_issues_for_file.return_value = [issue]

            mock_orchestrator = AsyncMock(spec=VibeHealOrchestrator)
            # When fix fails, VibeHealOrchestrator still returns FixSummary
            # with failed count > 0
            mock_orchestrator.fix_file.return_value = FixSummary(
                total_issues=1,
                failed=1,
            )
            mock_orchestrator_class.return_value = mock_orchestrator

            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=10,
            )

        assert result.success is False
        assert "Fix failed at iteration 1" in result.error_message
        assert "1 fixes failed" in result.error_message

    @pytest.mark.asyncio
    async def test_exception_handling(
        self,
        orchestrator: CleanupOrchestrator,
    ) -> None:
        """Test exception handling in _cleanup_file."""
        file_path = Path("src/file1.py")

        with patch.object(
            orchestrator.analysis_runner,
            "run_analysis",
            side_effect=Exception("Unexpected error"),
        ):
            result = await orchestrator._cleanup_file(
                file_path=file_path,
                project_key="test-key",
                project_name="Test Project",
                max_iterations=10,
            )

        assert result.success is False
        assert "Cleanup failed: Unexpected error" in result.error_message
        assert result.issues_fixed == 0


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
