"""DEPRECATED: Use vibe_heal.vcs.exceptions instead.

Git-specific exceptions - now imported from vcs.exceptions for backwards compatibility.
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

warnings.warn(
    "vibe_heal.git.exceptions is deprecated. Use vibe_heal.vcs.exceptions instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DirtyWorkingDirectoryError",
    "GitError",
    "GitOperationError",
    "NotAGitRepositoryError",
]
