"""DEPRECATED: Use vibe_heal.vcs.git.branch_analyzer instead.

Git branch analysis - now imported from vcs.git.branch_analyzer for backwards compatibility.
"""

import warnings

from vibe_heal.vcs.exceptions import (
    BranchAnalyzerError,
    BranchNotFoundError,
    InvalidRepositoryError,
)
from vibe_heal.vcs.git.branch_analyzer import GitBranchAnalyzer

warnings.warn(
    "vibe_heal.git.branch_analyzer is deprecated. Use vibe_heal.vcs.git.branch_analyzer or vibe_heal.vcs.factory.VCSFactory instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export for backwards compatibility (with old name)
BranchAnalyzer = GitBranchAnalyzer

__all__ = [
    "BranchAnalyzer",
    "BranchAnalyzerError",
    "BranchNotFoundError",
    "InvalidRepositoryError",
]
