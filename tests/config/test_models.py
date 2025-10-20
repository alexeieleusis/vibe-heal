"""Tests for configuration models."""

import pytest
from pydantic import ValidationError

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.config import InvalidConfigurationError, VibeHealConfig


class TestVibeHealConfig:
    """Tests for VibeHealConfig model."""

    def test_valid_config_with_token(self) -> None:
        """Test creating config with token authentication."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="test-token",
            sonarqube_project_key="my-project",
        )

        assert config.sonarqube_url == "https://sonar.example.com"
        assert config.sonarqube_token == "test-token"
        assert config.sonarqube_project_key == "my-project"
        assert config.use_token_auth is True

    def test_valid_config_with_basic_auth(self) -> None:
        """Test creating config with basic authentication."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_username="user",
            sonarqube_password="pass",
            sonarqube_project_key="my-project",
        )

        assert config.sonarqube_username == "user"
        assert config.sonarqube_password == "pass"
        assert config.use_token_auth is False

    def test_invalid_missing_auth(self) -> None:
        """Test that missing authentication raises error."""
        with pytest.raises(InvalidConfigurationError, match="Must provide either"):
            VibeHealConfig(
                sonarqube_url="https://sonar.example.com",
                sonarqube_project_key="my-project",
            )

    def test_invalid_only_username(self) -> None:
        """Test that only username (without password) raises error."""
        with pytest.raises(InvalidConfigurationError, match="Must provide either"):
            VibeHealConfig(
                sonarqube_url="https://sonar.example.com",
                sonarqube_username="user",
                sonarqube_project_key="my-project",
            )

    def test_invalid_only_password(self) -> None:
        """Test that only password (without username) raises error."""
        with pytest.raises(InvalidConfigurationError, match="Must provide either"):
            VibeHealConfig(
                sonarqube_url="https://sonar.example.com",
                sonarqube_password="pass",
                sonarqube_project_key="my-project",
            )

    def test_url_normalization_trailing_slash(self) -> None:
        """Test that trailing slash is removed from URL."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com/",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
        )

        assert config.sonarqube_url == "https://sonar.example.com"

    def test_url_normalization_multiple_slashes(self) -> None:
        """Test that multiple trailing slashes are removed."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com///",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
        )

        assert config.sonarqube_url == "https://sonar.example.com"

    def test_ai_tool_from_string_lowercase(self) -> None:
        """Test parsing AI tool from lowercase string."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
            ai_tool="claude-code",
        )

        assert config.ai_tool == AIToolType.CLAUDE_CODE

    def test_ai_tool_from_string_uppercase(self) -> None:
        """Test parsing AI tool from uppercase string (case insensitive)."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
            ai_tool="CLAUDE-CODE",
        )

        assert config.ai_tool == AIToolType.CLAUDE_CODE

    def test_ai_tool_aider_from_string(self) -> None:
        """Test parsing Aider from lowercase string."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
            ai_tool="aider",
        )

        assert config.ai_tool == AIToolType.AIDER

    def test_ai_tool_from_enum(self) -> None:
        """Test that enum value is accepted directly."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
            ai_tool=AIToolType.AIDER,
        )

        assert config.ai_tool == AIToolType.AIDER

    def test_ai_tool_none(self) -> None:
        """Test that None is accepted for ai_tool (auto-detect)."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="token",
            sonarqube_project_key="my-project",
        )

        assert config.ai_tool is None

    def test_ai_tool_invalid_string(self) -> None:
        """Test that invalid AI tool string raises error."""
        with pytest.raises(InvalidConfigurationError, match="Invalid AI tool"):
            VibeHealConfig(
                sonarqube_url="https://sonar.example.com",
                sonarqube_token="token",
                sonarqube_project_key="my-project",
                ai_tool="invalid-tool",
            )

    def test_missing_required_url(self) -> None:
        """Test that missing URL raises ValidationError."""
        with pytest.raises(ValidationError, match="sonarqube_url"):
            VibeHealConfig(
                sonarqube_token="token",
                sonarqube_project_key="my-project",
            )

    def test_missing_required_project_key(self) -> None:
        """Test that missing project key raises ValidationError."""
        with pytest.raises(ValidationError, match="sonarqube_project_key"):
            VibeHealConfig(
                sonarqube_url="https://sonar.example.com",
                sonarqube_token="token",
            )

    def test_token_auth_takes_precedence(self) -> None:
        """Test that token auth is preferred when both methods provided."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.example.com",
            sonarqube_token="token",
            sonarqube_username="user",
            sonarqube_password="pass",
            sonarqube_project_key="my-project",
        )

        # Token auth should be used when both are present
        assert config.use_token_auth is True
