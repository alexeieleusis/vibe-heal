"""Tests for orchestrator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture

from vibe_heal.ai_tools import AIToolType, ClaudeCodeTool, FixResult
from vibe_heal.config import VibeHealConfig
from vibe_heal.git import GitManager
from vibe_heal.orchestrator import VibeHealOrchestrator
from vibe_heal.sonarqube.models import SonarQubeIssue


@pytest.fixture
def mock_config() -> VibeHealConfig:
    """Create mock configuration.

    Returns:
        Mock configuration
    """
    config = MagicMock(spec=VibeHealConfig)
    config.sonarqube_url = "https://sonar.example.com"
    config.sonarqube_project_key = "test-project"
    config.ai_tool = None  # Test auto-detection
    config.include_rule_description = True  # Default to true
    config.code_context_lines = 5  # Default value
    return config


@pytest.fixture
def sample_issue() -> SonarQubeIssue:
    """Create sample issue for testing.

    Returns:
        Sample SonarQube issue
    """
    return SonarQubeIssue(
        key="ABC123",
        rule="python:S1481",
        severity="MAJOR",
        message="Remove unused variable",
        component="project:src/test.py",
        line=10,
        status="OPEN",
        type="CODE_SMELL",
    )


class TestOrchestratorInit:
    """Tests for orchestrator initialization."""

    def test_init_with_configured_ai_tool(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test initialization with configured AI tool."""
        mock_config.ai_tool = AIToolType.CLAUDE_CODE
        mocker.patch("shutil.which", return_value="/usr/bin/claude")

        orchestrator = VibeHealOrchestrator(mock_config)

        assert orchestrator.config == mock_config
        assert isinstance(orchestrator.ai_tool, ClaudeCodeTool)

    def test_init_with_auto_detect(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test initialization with auto-detected AI tool."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")

        orchestrator = VibeHealOrchestrator(mock_config)

        assert isinstance(orchestrator.ai_tool, ClaudeCodeTool)

    def test_init_raises_when_no_ai_tool(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test initialization fails when no AI tool available."""
        mocker.patch("shutil.which", return_value=None)

        with pytest.raises(RuntimeError, match="No AI tool found"):
            VibeHealOrchestrator(mock_config)


class TestOrchestratorValidation:
    """Tests for precondition validation."""

    def test_validate_preconditions_not_git_repo(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when not a Git repository."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=False)

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        with pytest.raises(RuntimeError, match="Not a Git repository"):
            orchestrator._validate_preconditions(str(test_file), dry_run=False)

    def test_validate_preconditions_working_directory_has_uncommitted_changes(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when working directory has uncommitted changes."""
        from vibe_heal.git.exceptions import DirtyWorkingDirectoryError

        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)
        mocker.patch.object(
            GitManager, "require_clean_working_directory", side_effect=DirtyWorkingDirectoryError("dirty")
        )

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        with pytest.raises(DirtyWorkingDirectoryError):
            orchestrator._validate_preconditions(str(test_file), dry_run=False)

    def test_validate_preconditions_file_not_found(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test validation fails when file doesn't exist."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)

        orchestrator = VibeHealOrchestrator(mock_config)

        with pytest.raises(FileNotFoundError):
            orchestrator._validate_preconditions("/nonexistent/file.py", dry_run=False)

    def test_validate_preconditions_ai_tool_not_available(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test validation fails when AI tool is not available."""
        # Use configured AI tool to bypass auto-detection
        mock_config.ai_tool = AIToolType.CLAUDE_CODE
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)
        mocker.patch.object(GitManager, "require_clean_working_directory")

        orchestrator = VibeHealOrchestrator(mock_config)

        # Now mock the tool as unavailable for validation
        mocker.patch.object(orchestrator.ai_tool, "is_available", return_value=False)

        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        with pytest.raises(RuntimeError, match="not available"):
            orchestrator._validate_preconditions(str(test_file), dry_run=False)

    def test_validate_preconditions_dry_run_skips_clean_check(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test validation skips clean working directory check in dry-run mode."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)
        mock_clean_check = mocker.patch.object(GitManager, "require_clean_working_directory")

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        orchestrator._validate_preconditions(str(test_file), dry_run=True)

        # Should not check for clean working directory in dry-run mode
        mock_clean_check.assert_not_called()


class TestOrchestratorFixFile:
    """Tests for fix_file method."""

    @pytest.mark.asyncio
    async def test_fix_file_no_issues(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        """Test fix_file when no issues found."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)

        # Mock SonarQube client
        mock_client = AsyncMock()
        mock_client.get_issues_for_file.return_value = []
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mocker.patch("vibe_heal.orchestrator.SonarQubeClient", return_value=mock_client)

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        summary = await orchestrator.fix_file(str(test_file), dry_run=True)

        assert summary.total_issues == 0
        assert summary.fixed == 0
        assert summary.failed == 0

    @pytest.mark.asyncio
    async def test_fix_file_no_fixable_issues(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test fix_file when no fixable issues."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)

        # Make issue not fixable
        sample_issue.status = "RESOLVED"

        # Mock SonarQube client
        mock_client = AsyncMock()
        mock_client.get_issues_for_file.return_value = [sample_issue]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mocker.patch("vibe_heal.orchestrator.SonarQubeClient", return_value=mock_client)

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        summary = await orchestrator.fix_file(str(test_file), dry_run=True)

        assert summary.total_issues == 1
        assert summary.fixed == 0
        assert summary.skipped == 1

    @pytest.mark.asyncio
    async def test_fix_file_successful_dry_run(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test successful fix in dry-run mode."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)

        # Mock SonarQube client
        mock_client = AsyncMock()
        mock_client.get_issues_for_file.return_value = [sample_issue]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mocker.patch("vibe_heal.orchestrator.SonarQubeClient", return_value=mock_client)

        # Mock AI tool
        mocker.patch.object(
            ClaudeCodeTool,
            "fix_issue",
            return_value=FixResult(success=True, files_modified=["test.py"]),
        )

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        summary = await orchestrator.fix_file(str(test_file), dry_run=True)

        assert summary.total_issues == 1
        assert summary.fixed == 1
        assert summary.failed == 0
        assert len(summary.commits) == 0  # No commits in dry-run

    @pytest.mark.asyncio
    async def test_fix_file_user_cancels(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
        tmp_path: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test fix_file when user cancels."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch.object(GitManager, "is_repository", return_value=True)
        mocker.patch.object(GitManager, "require_clean_working_directory")

        # Mock SonarQube client
        mock_client = AsyncMock()
        mock_client.get_issues_for_file.return_value = [sample_issue]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mocker.patch("vibe_heal.orchestrator.SonarQubeClient", return_value=mock_client)

        # Mock user cancellation
        mocker.patch("builtins.input", return_value="n")

        orchestrator = VibeHealOrchestrator(mock_config)
        test_file = tmp_path / "test.py"
        test_file.write_text("code")

        summary = await orchestrator.fix_file(str(test_file), dry_run=False)

        assert summary.total_issues == 1
        assert summary.fixed == 0
        assert summary.skipped == 1


class TestConfirmProcessing:
    """Tests for user confirmation."""

    def test_confirm_processing_yes(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test user confirms processing."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch("builtins.input", return_value="y")

        orchestrator = VibeHealOrchestrator(mock_config)

        assert orchestrator._confirm_processing(3) is True

    def test_confirm_processing_no(
        self,
        mock_config: VibeHealConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test user declines processing."""
        mocker.patch("shutil.which", return_value="/usr/bin/claude")
        mocker.patch("builtins.input", return_value="n")

        orchestrator = VibeHealOrchestrator(mock_config)

        assert orchestrator._confirm_processing(3) is False
