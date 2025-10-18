"""Tests for AI tool base classes and enums."""

import pytest

from vibe_heal.ai_tools.base import AIToolType


class TestAIToolType:
    """Tests for AIToolType enum."""

    def test_enum_values(self) -> None:
        """Test that enum has expected values."""
        assert AIToolType.CLAUDE_CODE.value == "claude-code"
        assert AIToolType.AIDER.value == "aider"

    def test_cli_command_property(self) -> None:
        """Test cli_command property returns correct command."""
        assert AIToolType.CLAUDE_CODE.cli_command == "claude-code"
        assert AIToolType.AIDER.cli_command == "aider"

    def test_display_name_property(self) -> None:
        """Test display_name property returns human-readable names."""
        assert AIToolType.CLAUDE_CODE.display_name == "Claude Code"
        assert AIToolType.AIDER.display_name == "Aider"

    def test_string_conversion(self) -> None:
        """Test that enum value can be accessed as string."""
        assert AIToolType.CLAUDE_CODE.value == "claude-code"
        assert AIToolType.AIDER.value == "aider"
        # Since AIToolType inherits from str, it should work in string contexts
        assert AIToolType.CLAUDE_CODE == "claude-code"
        assert AIToolType.AIDER == "aider"

    def test_enum_comparison(self) -> None:
        """Test enum equality comparison."""
        assert AIToolType.CLAUDE_CODE == AIToolType.CLAUDE_CODE
        assert AIToolType.AIDER == AIToolType.AIDER
        assert AIToolType.CLAUDE_CODE != AIToolType.AIDER

    def test_enum_from_string(self) -> None:
        """Test creating enum from string value."""
        assert AIToolType("claude-code") == AIToolType.CLAUDE_CODE
        assert AIToolType("aider") == AIToolType.AIDER

    def test_invalid_enum_value(self) -> None:
        """Test that invalid value raises ValueError."""
        with pytest.raises(ValueError):
            AIToolType("invalid-tool")
