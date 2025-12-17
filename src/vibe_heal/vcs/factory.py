"""VCS detection and factory for creating VCS managers and analyzers.

This module provides automatic detection of the version control system
in use and factory methods for creating appropriate manager/analyzer instances.
"""

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibe_heal.vcs.base import BranchAnalyzer, VCSManager


class VCSType(Enum):
    """Supported version control systems."""

    GIT = "git"
    MERCURIAL = "mercurial"

    @property
    def display_name(self) -> str:
        """Get display name for the VCS type.

        Returns:
            Human-readable name
        """
        return {
            VCSType.GIT: "Git",
            VCSType.MERCURIAL: "Mercurial",
        }[self]


class VCSFactory:
    """Factory for creating VCS managers and analyzers.

    Provides automatic VCS detection and factory methods for creating
    appropriate VCS-specific implementations.
    """

    @staticmethod
    def detect_vcs(repo_path: Path | None = None) -> VCSType:
        """Detect which VCS is in use at the given path.

        Detection order:
        1. Check for .git directory (Git)
        2. Check for .hg directory (Mercurial)
        3. Default to Git if neither found (for backwards compatibility)

        Searches parent directories recursively to find VCS markers.

        Args:
            repo_path: Path to check (default: current directory)

        Returns:
            VCSType enum value indicating detected VCS
        """
        path = Path(repo_path or Path.cwd()).resolve()

        # Search parent directories for VCS markers
        current = path
        while current != current.parent:
            if (current / ".git").exists():
                return VCSType.GIT
            if (current / ".hg").exists():
                return VCSType.MERCURIAL
            current = current.parent

        # Check root directory
        if (current / ".git").exists():
            return VCSType.GIT
        if (current / ".hg").exists():
            return VCSType.MERCURIAL

        # Default to Git for backwards compatibility
        return VCSType.GIT

    @staticmethod
    def create_manager(
        repo_path: str | Path | None = None,
        vcs_type: VCSType | None = None,
    ) -> "VCSManager":
        """Create a VCS manager instance.

        If vcs_type is not specified, automatically detects the VCS type.

        Args:
            repo_path: Path to repository (default: current directory)
            vcs_type: VCS type (default: auto-detect)

        Returns:
            VCS manager instance (GitManager or MercurialManager)

        Raises:
            ValueError: If unsupported VCS type is specified
        """
        if vcs_type is None:
            vcs_type = VCSFactory.detect_vcs(Path(repo_path or Path.cwd()))

        if vcs_type == VCSType.GIT:
            from vibe_heal.vcs.git.manager import GitManager

            return GitManager(repo_path)
        elif vcs_type == VCSType.MERCURIAL:
            from vibe_heal.vcs.mercurial.manager import MercurialManager

            return MercurialManager(repo_path)
        else:
            msg = f"Unsupported VCS type: {vcs_type}"
            raise ValueError(msg)

    @staticmethod
    def create_branch_analyzer(
        repo_path: Path | None = None,
        vcs_type: VCSType | None = None,
    ) -> "BranchAnalyzer":
        """Create a branch analyzer instance.

        If vcs_type is not specified, automatically detects the VCS type.

        Args:
            repo_path: Path to repository (default: current directory)
            vcs_type: VCS type (default: auto-detect)

        Returns:
            Branch analyzer instance (GitBranchAnalyzer or MercurialBranchAnalyzer)

        Raises:
            ValueError: If unsupported VCS type is specified
        """
        path = repo_path or Path.cwd()

        if vcs_type is None:
            vcs_type = VCSFactory.detect_vcs(path)

        if vcs_type == VCSType.GIT:
            from vibe_heal.vcs.git.branch_analyzer import GitBranchAnalyzer

            return GitBranchAnalyzer(path)
        elif vcs_type == VCSType.MERCURIAL:
            from vibe_heal.vcs.mercurial.branch_analyzer import MercurialBranchAnalyzer

            return MercurialBranchAnalyzer(path)
        else:
            msg = f"Unsupported VCS type: {vcs_type}"
            raise ValueError(msg)
