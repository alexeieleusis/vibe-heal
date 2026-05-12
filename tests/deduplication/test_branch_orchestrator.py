"""Tests for DedupeBranchOrchestrator class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vibe_heal.ai_tools.base import AITool
from vibe_heal.config import VibeHealConfig
from vibe_heal.deduplication.orchestrator import DedupeBranchOrchestrator
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import SonarQubeAPIError
from vibe_heal.sonarqube.project_manager import TempProjectMetadata


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
) -> DedupeBranchOrchestrator:
    """Create DedupeBranchOrchestrator with mocked dependencies."""
    return DedupeBranchOrchestrator(config, mock_client, mock_ai_tool)


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


class TestCreateTempProject:
    """Tests for _create_temp_project method."""

    @pytest.mark.asyncio
    async def test_create_temp_project_warns_on_settings_copy_failure(
        self,
        orchestrator: DedupeBranchOrchestrator,
        temp_project: TempProjectMetadata,
    ) -> None:
        """Test that the orchestrator warns but does not re-raise when copying settings fails."""
        with (
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
                orchestrator.project_manager,
                "copy_exclusion_settings",
                side_effect=SonarQubeAPIError("Permission denied", status_code=403),
            ),
        ):
            result = await orchestrator._create_temp_project()

        assert result == temp_project

    @pytest.mark.asyncio
    async def test_create_temp_project_copies_settings_successfully(
        self,
        orchestrator: DedupeBranchOrchestrator,
        temp_project: TempProjectMetadata,
    ) -> None:
        """Test that settings are copied successfully after project creation."""
        with (
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
                orchestrator.project_manager,
                "copy_exclusion_settings",
                return_value=(["sonar.cpd.exclusions"], 0, 0),
            ) as mock_copy,
        ):
            result = await orchestrator._create_temp_project()

        assert result == temp_project
        mock_copy.assert_called_once_with(
            source_key=orchestrator.config.sonarqube_project_key,
            target_key=temp_project.project_key,
        )
