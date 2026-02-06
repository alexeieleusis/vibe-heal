"""Version Control System abstraction for vibe-heal.

This module provides a unified interface for working with different
version control systems (Git, Mercurial, etc.).
"""

from vibe_heal.vcs.base import BranchAnalyzer, VCSManager
from vibe_heal.vcs.exceptions import (
    BranchAnalyzerError,
    BranchNotFoundError,
    DirtyWorkingDirectoryError,
    InvalidRepositoryError,
    NotARepositoryError,
    VCSError,
    VCSOperationError,
)
from vibe_heal.vcs.factory import VCSFactory, VCSType

__all__ = [
    "BranchAnalyzer",
    "BranchAnalyzerError",
    "BranchNotFoundError",
    "DirtyWorkingDirectoryError",
    "InvalidRepositoryError",
    "NotARepositoryError",
    "VCSError",
    "VCSFactory",
    "VCSManager",
    "VCSOperationError",
    "VCSType",
]
