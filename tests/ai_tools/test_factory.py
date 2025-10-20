"""Tests for AI tool factory."""

import pytest
from pytest_mock import MockerFixture

from vibe_heal.ai_tools import AIToolFactory, AIToolType, ClaudeCodeTool


class TestAIToolFactory:
    """Tests for AIToolFactory."""

    def test_create_claude_code_tool(self) -> None:
        """Test creating Claude Code tool."""
        tool = AIToolFactory.create(AIToolType.CLAUDE_CODE)

        assert isinstance(tool, ClaudeCodeTool)
        assert tool.tool_type == AIToolType.CLAUDE_CODE

    def test_create_invalid_tool_type(self) -> None:
        """Test creating tool with unsupported type raises error."""
        # AIDER is not implemented yet (Phase 8)
        with pytest.raises(ValueError, match="Unsupported AI tool type"):
            AIToolFactory.create(AIToolType.AIDER)

    def test_detect_available_when_claude_exists(self, mocker: MockerFixture) -> None:
        """Test auto-detection when Claude is available."""
        # Mock shutil.which to return Claude path
        mocker.patch("shutil.which", return_value="/usr/local/bin/claude")

        detected = AIToolFactory.detect_available()

        assert detected == AIToolType.CLAUDE_CODE

    def test_detect_available_when_no_tools(self, mocker: MockerFixture) -> None:
        """Test auto-detection when no tools available."""
        # Mock shutil.which to return None (tool not found)
        mocker.patch("shutil.which", return_value=None)

        detected = AIToolFactory.detect_available()

        assert detected is None

    def test_factory_returns_new_instances(self) -> None:
        """Test that factory creates new instances each time."""
        tool1 = AIToolFactory.create(AIToolType.CLAUDE_CODE)
        tool2 = AIToolFactory.create(AIToolType.CLAUDE_CODE)

        assert tool1 is not tool2
        assert isinstance(tool1, ClaudeCodeTool)
        assert isinstance(tool2, ClaudeCodeTool)
