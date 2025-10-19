"""Git integration for vibe-heal."""

from vibe_heal.git.exceptions import (
    DirtyWorkingDirectoryError,
    GitError,
    GitOperationError,
    NotAGitRepositoryError,
)
from vibe_heal.git.manager import GitManager

__all__ = [
    "DirtyWorkingDirectoryError",
    "GitError",
    "GitManager",
    "GitOperationError",
    "NotAGitRepositoryError",
]
