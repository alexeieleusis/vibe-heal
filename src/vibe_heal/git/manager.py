"""DEPRECATED: Use vibe_heal.vcs.git.manager instead.

Git operations manager - now imported from vcs.git.manager for backwards compatibility.
"""

import warnings
        body_parts.extend([
            f"Fixed by: vibe-heal using {ai_tool_type.display_name}",
            "",
            "[vibe-heal](https://github.com/alexeieleusis/vibe-heal)",
        ])

from vibe_heal.vcs.git.manager import GitManager as _GitManager

warnings.warn(
    "vibe_heal.git.manager is deprecated. Use vibe_heal.vcs.git.manager or vibe_heal.vcs.factory.VCSFactory instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export for backwards compatibility
GitManager = _GitManager

__all__ = ["GitManager"]
