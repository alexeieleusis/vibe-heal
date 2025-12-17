"""DEPRECATED: Use vibe_heal.vcs instead.

Git integration for vibe-heal - now provided by vcs module for backwards compatibility.
"""

import warnings

from vibe_heal.vcs.exceptions import (
    DirtyWorkingDirectoryError,
)
from vibe_heal.vcs.exceptions import (
    NotARepositoryError as NotAGitRepositoryError,
)
from vibe_heal.vcs.exceptions import (
    VCSError as GitError,
)
from vibe_heal.vcs.exceptions import (
    VCSOperationError as GitOperationError,
)
from vibe_heal.vcs.git.manager import GitManager

warnings.warn(
    "vibe_heal.git is deprecated. Use vibe_heal.vcs instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DirtyWorkingDirectoryError",
    "GitError",
    "GitManager",
    "GitOperationError",
    "NotAGitRepositoryError",
]
