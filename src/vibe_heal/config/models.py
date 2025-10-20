"""Configuration models."""

from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.config.exceptions import InvalidConfigurationError


class VibeHealConfig(BaseSettings):
    """Configuration for vibe-heal application."""

    # SonarQube settings
    sonarqube_url: str = Field(description="SonarQube server URL")
    sonarqube_token: str | None = Field(
        default=None,
        description="SonarQube authentication token (preferred)",
    )
    sonarqube_username: str | None = Field(
        default=None,
        description="SonarQube username (alternative to token)",
    )
    sonarqube_password: str | None = Field(
        default=None,
        description="SonarQube password (alternative to token)",
    )
    sonarqube_project_key: str = Field(description="SonarQube project key")

    # AI Tool settings
    ai_tool: AIToolType | None = Field(
        default=None,
        description="AI tool to use (auto-detect if not specified)",
    )

    # Aider-specific settings (only used when ai_tool=AIDER)
    aider_model: str | None = Field(
        default=None,
        description="Aider model to use (e.g., 'ollama_chat/gemma3:27b')",
    )
    aider_api_key: str | None = Field(
        default=None,
        description="API key for Aider's model provider (e.g., OLLAMA_API_KEY)",
    )
    aider_api_base: str | None = Field(
        default=None,
        description="API base URL for Aider's model provider (e.g., 'http://127.0.0.1:11434')",
    )

    # Context enrichment settings
    code_context_lines: int = Field(
        default=5,
        description="Number of lines to show before/after the issue line for context",
    )
    include_rule_description: bool = Field(
        default=True,
        description="Include full rule description in AI prompts",
    )

    model_config = SettingsConfigDict(
        env_file=[".env.vibeheal", ".env"],
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("ai_tool", mode="before")
    @classmethod
    def parse_ai_tool(cls, v: str | AIToolType | None) -> AIToolType | None:
        """Parse AI tool from string or enum.

        Args:
            v: AI tool value (string, enum, or None)

        Returns:
            Parsed AIToolType or None

        Raises:
            InvalidConfigurationError: If AI tool value is invalid
        """
        if v is None:
            return None
        if isinstance(v, AIToolType):
            return v
        if isinstance(v, str):
            try:
                return AIToolType(v.lower())
            except ValueError as e:
                valid_tools = [t.value for t in AIToolType]
                raise InvalidConfigurationError(f"Invalid AI tool: {v}. Valid options: {valid_tools}") from e
        raise InvalidConfigurationError(f"Invalid AI tool type: {type(v)}")

    @field_validator("sonarqube_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL doesn't have trailing slash.

        Args:
            v: URL value

        Returns:
            Normalized URL without trailing slash
        """
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        """Ensure either token or username/password is provided.

        Returns:
            Self

        Raises:
            InvalidConfigurationError: If neither auth method is provided
        """
        has_token = self.sonarqube_token is not None
        has_basic = self.sonarqube_username is not None and self.sonarqube_password is not None

        if not has_token and not has_basic:
            raise InvalidConfigurationError(
                "Must provide either SONARQUBE_TOKEN or both SONARQUBE_USERNAME and SONARQUBE_PASSWORD"
            )

        return self

    @property
    def use_token_auth(self) -> bool:
        """Check if token authentication should be used.

        Returns:
            True if token auth is configured
        """
        return self.sonarqube_token is not None

    @staticmethod
    def find_env_file() -> Path | None:
        """Find the environment file being used.

        Checks for .env.vibeheal and .env in current directory in that order.

        Returns:
            Path to the env file if found, None otherwise
        """
        for env_file in [".env.vibeheal", ".env"]:
            path = Path(env_file)
            if path.exists():
                return path.absolute()
        return None
