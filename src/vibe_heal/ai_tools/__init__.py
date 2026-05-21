"""AI tool integration for vibe-heal."""

from vibe_heal.ai_tools.aider import AiderTool
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.claude_code import ClaudeCodeTool
from vibe_heal.ai_tools.factory import AIToolFactory
from vibe_heal.ai_tools.gemini import GeminiCliTool
from vibe_heal.ai_tools.models import FixResult
from vibe_heal.ai_tools.opencode import OpenCodeTool

__all__ = [
    "AITool",
    "AIToolFactory",
    "AIToolType",
    "AiderTool",
    "ClaudeCodeTool",
    "FixResult",
    "GeminiCliTool",
    "OpenCodeTool",
    "create_fix_prompt",
]


def __getattr__(name: str):
    """Lazy import of create_fix_prompt to avoid circular imports."""
    if name == "create_fix_prompt":
        from vibe_heal.ai_tools.prompts import create_fix_prompt as _create_fix_prompt

        return _create_fix_prompt
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
