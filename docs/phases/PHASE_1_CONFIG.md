# Phase 1: Configuration Management ✅ COMPLETE

## Objective

Implement configuration loading and validation using Pydantic Settings with support for `.env.vibeheal` and `.env` files.

## Status: ✅ COMPLETE

All configuration management features implemented and tested:
- [x] `AIToolType` enum with CLAUDE_CODE and AIDER support
- [x] Configuration exceptions (ConfigurationError, InvalidConfigurationError, MissingConfigurationError)
- [x] `VibeHealConfig` model with full validation
- [x] Token and basic authentication support
- [x] URL normalization
- [x] AI tool parsing from strings
- [x] Comprehensive test coverage (97%)
- [x] All tests passing (28 tests)

**Test Results**: 28 tests, 97% coverage on config module

## Dependencies

- Phase 0 must be complete ✅
- `pydantic`, `pydantic-settings`, `python-dotenv` installed ✅

## Files to Create/Modify

```
src/vibe_heal/
├── ai_tools/
│   └── base.py                    # AIToolType enum
├── config/
│   ├── __init__.py               # Export public API
│   ├── models.py                 # VibeHealConfig
│   └── exceptions.py             # Configuration exceptions
tests/
└── config/
    ├── test_models.py            # Config model tests
    └── test_config_loading.py    # Config loading tests
```

## Tasks

### 1. Create AIToolType Enum

**File**: `src/vibe_heal/ai_tools/base.py`

```python
from enum import Enum


class AIToolType(str, Enum):
    """Supported AI coding tools."""

    CLAUDE_CODE = "claude-code"
    AIDER = "aider"

    @property
    def cli_command(self) -> str:
        """Get the CLI command name for this tool."""
        return self.value

    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        return {
            AIToolType.CLAUDE_CODE: "Claude Code",
            AIToolType.AIDER: "Aider",
        }[self]
```

**Tests**: `tests/ai_tools/test_base.py`
- Test enum values
- Test `cli_command` property
- Test `display_name` property
- Test string conversion

### 2. Create Configuration Exceptions

**File**: `src/vibe_heal/config/exceptions.py`

```python
class ConfigurationError(Exception):
    """Base exception for configuration errors."""
    pass


class MissingConfigurationError(ConfigurationError):
    """Required configuration is missing."""
    pass


class InvalidConfigurationError(ConfigurationError):
    """Configuration value is invalid."""
    pass
```

### 3. Create Configuration Model

**File**: `src/vibe_heal/config/models.py`

```python
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Self

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.config.exceptions import InvalidConfigurationError


class VibeHealConfig(BaseSettings):
    """Configuration for vibe-heal application."""

    # SonarQube settings
    sonarqube_url: str = Field(
        description="SonarQube server URL"
    )
    sonarqube_token: str | None = Field(
        default=None,
        description="SonarQube authentication token (preferred)"
    )
    sonarqube_username: str | None = Field(
        default=None,
        description="SonarQube username (alternative to token)"
    )
    sonarqube_password: str | None = Field(
        default=None,
        description="SonarQube password (alternative to token)"
    )
    sonarqube_project_key: str = Field(
        description="SonarQube project key"
    )

    # AI Tool settings
    ai_tool: AIToolType | None = Field(
        default=None,
        description="AI tool to use (auto-detect if not specified)"
    )

    model_config = SettingsConfigDict(
        env_file=['.env.vibeheal', '.env'],
        env_file_encoding='utf-8',
        env_prefix='',
        case_sensitive=False,
        extra='ignore',
    )

    @field_validator('ai_tool', mode='before')
    @classmethod
    def parse_ai_tool(cls, v: str | AIToolType | None) -> AIToolType | None:
        """Parse AI tool from string or enum."""
        if v is None:
            return None
        if isinstance(v, AIToolType):
            return v
        if isinstance(v, str):
            try:
                return AIToolType(v.lower())
            except ValueError as e:
                valid_tools = [t.value for t in AIToolType]
                raise InvalidConfigurationError(
                    f"Invalid AI tool: {v}. Valid options: {valid_tools}"
                ) from e
        raise InvalidConfigurationError(f"Invalid AI tool type: {type(v)}")

    @field_validator('sonarqube_url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL doesn't have trailing slash."""
        return v.rstrip('/')

    @model_validator(mode='after')
    def validate_auth(self) -> Self:
        """Ensure either token or username/password is provided."""
        has_token = self.sonarqube_token is not None
        has_basic = (
            self.sonarqube_username is not None
            and self.sonarqube_password is not None
        )

        if not has_token and not has_basic:
            raise InvalidConfigurationError(
                "Must provide either SONARQUBE_TOKEN or both "
                "SONARQUBE_USERNAME and SONARQUBE_PASSWORD"
            )

        return self

    @property
    def use_token_auth(self) -> bool:
        """Check if token authentication should be used."""
        return self.sonarqube_token is not None
```

### 4. Export Public API

**File**: `src/vibe_heal/config/__init__.py`

```python
from vibe_heal.config.exceptions import (
    ConfigurationError,
    InvalidConfigurationError,
    MissingConfigurationError,
)
from vibe_heal.config.models import VibeHealConfig

__all__ = [
    "VibeHealConfig",
    "ConfigurationError",
    "InvalidConfigurationError",
    "MissingConfigurationError",
]
```

### 5. Write Comprehensive Tests

**File**: `tests/config/test_models.py`

Test cases:
- ✅ Valid configuration with token auth
- ✅ Valid configuration with basic auth
- ✅ Invalid: missing auth (no token, no username/password)
- ✅ Invalid: only username provided (missing password)
- ✅ Invalid: only password provided (missing username)
- ✅ URL normalization (removes trailing slash)
- ✅ AI tool parsing from string
- ✅ AI tool invalid value raises error
- ✅ Case insensitivity for AI tool
- ✅ Missing required fields (url, project_key)

**File**: `tests/config/test_config_loading.py`

Test cases:
- ✅ Load from `.env.vibeheal` file
- ✅ Load from `.env` file
- ✅ Prefer `.env.vibeheal` over `.env`
- ✅ Load from environment variables
- ✅ Environment variables override .env files

Use `pytest-mock` and temporary files for testing.

## Example Usage

After this phase, configuration can be loaded like:

```python
from vibe_heal.config import VibeHealConfig

# Load from .env.vibeheal or .env
config = VibeHealConfig()

# Access configuration
print(config.sonarqube_url)
print(config.use_token_auth)
if config.ai_tool:
    print(config.ai_tool.display_name)
```

## Verification Steps

1. Run tests:
   ```bash
   uv run pytest tests/config/ -v
   ```

2. Test with actual .env file:
   ```bash
   # Create test .env.vibeheal
   cat > .env.vibeheal <<EOF
   SONARQUBE_URL=https://sonar.example.com
   SONARQUBE_TOKEN=test-token
   SONARQUBE_PROJECT_KEY=my-project
   AI_TOOL=claude-code
   EOF

   # Test loading
   uv run python -c "from vibe_heal.config import VibeHealConfig; c = VibeHealConfig(); print(c)"
   ```

3. Type checking:
   ```bash
   uv run mypy src/vibe_heal/config/
   ```

## Definition of Done

- ✅ `AIToolType` enum implemented with tests
- ✅ `VibeHealConfig` model with all validations
- ✅ Authentication validation (token or basic auth required)
- ✅ URL normalization
- ✅ AI tool parsing from string
- ✅ Comprehensive test coverage (>90%)
- ✅ Type checking passes
- ✅ Can load config from `.env.vibeheal` and `.env`
- ✅ All tests pass

## Notes

- Focus on comprehensive validation - fail fast with clear errors
- Use Pydantic's built-in validators as much as possible
- Test both happy path and error cases
- Consider adding a `config show` CLI command later to verify configuration
