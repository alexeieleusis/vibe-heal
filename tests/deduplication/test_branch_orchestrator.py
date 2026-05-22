"""Tests for DedupeBranchOrchestrator class."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.shared_orchestrator_tests import BaseTestCreateTempProject
from vibe_heal.ai_tools.base import AITool
from vibe_heal.config import VibeHealConfig
from vibe_heal.deduplication.orchestrator import DedupeBranchOrchestrator
from vibe_heal.sonarqube.client import SonarQubeClient


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


class TestCreateTempProject(BaseTestCreateTempProject):
    """Tests for _create_temp_project method."""

    pass
