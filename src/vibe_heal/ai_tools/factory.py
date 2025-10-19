"""Factory for creating AI tool instances."""

from typing import ClassVar

from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.claude_code import ClaudeCodeTool


class AIToolFactory:
    """Factory for creating AI tool instances."""

    _tool_map: ClassVar[dict[AIToolType, type[AITool]]] = {
        AIToolType.CLAUDE_CODE: ClaudeCodeTool,
        # AIToolType.AIDER will be added in Phase 8
    }

    @staticmethod
    def create(tool_type: AIToolType) -> AITool:
        """Create an AI tool instance based on type.

        Args:
            tool_type: The type of AI tool to create

        Returns:
            AI tool instance

        Raises:
            ValueError: If tool type is not supported
        """
        tool_class = AIToolFactory._tool_map.get(tool_type)
        if not tool_class:
            raise ValueError(f"Unsupported AI tool type: {tool_type}")
        return tool_class()

    @staticmethod
    def detect_available() -> AIToolType | None:
        """Auto-detect first available AI tool.

        Tries tools in order of preference:
        1. Claude Code
        2. Aider (to be added in Phase 8)

        Returns:
            AIToolType of first available tool, or None if none found
        """
        # Try in preference order
        for tool_type in [AIToolType.CLAUDE_CODE]:  # Add AIDER later
            try:
                tool = AIToolFactory.create(tool_type)
                if tool.is_available():
                    return tool_type
            except ValueError:
                continue

        return None
