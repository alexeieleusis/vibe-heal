"""Common VCS exceptions for vibe-heal.

This module provides VCS-agnostic exception classes that can be used
by any version control system implementation (Git, Mercurial, etc.).
"""


class VCSError(Exception):
    """Base exception for all VCS-related errors."""


class NotARepositoryError(VCSError):
    """Raised when a directory is not a valid repository."""


class DirtyWorkingDirectoryError(VCSError):
    """Raised when the working directory has uncommitted changes."""


class VCSOperationError(VCSError):
    """Raised when a VCS operation fails."""


class BranchAnalyzerError(VCSError):
    """Base exception for BranchAnalyzer errors."""


class BranchNotFoundError(BranchAnalyzerError):
    """Raised when a specified branch does not exist."""


class InvalidRepositoryError(BranchAnalyzerError):
    """Raised when the repository is invalid or not found."""
