"""Mercurial branch analysis for identifying modified files."""

from pathlib import Path
from types import TracebackType

import hglib  # type: ignore[import-untyped]

from vibe_heal.vcs.base import BranchAnalyzer
from vibe_heal.vcs.exceptions import (
    BranchAnalyzerError,
    BranchNotFoundError,
    InvalidRepositoryError,
)


class MercurialBranchAnalyzer(BranchAnalyzer):
    """Analyzes differences between Mercurial branches to identify modified files.

    This class provides functionality to compare the current branch with a base
    branch and identify which files have been modified, added, or changed.
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize the MercurialBranchAnalyzer.

        Args:
            repo_path: Path to the Mercurial repository root

        Raises:
            InvalidRepositoryError: If repo_path is not a valid Mercurial repository
        """
        super().__init__(repo_path)
        try:
            self.client = hglib.open(str(repo_path))
        except hglib.error.ServerError as e:
            raise InvalidRepositoryError(f"Not a valid Mercurial repository: {repo_path}") from e

        self.repo_path = Path(repo_path)

    def close(self) -> None:
        """Close the underlying Mercurial client."""
        if hasattr(self, "client"):
            try:  # noqa: SIM105
                self.client.close()
            except Exception:  # noqa: S110
                # Intentionally ignore errors on close to avoid masking earlier exceptions
                pass

    def __enter__(self) -> "MercurialBranchAnalyzer":
        """Enter context manager, returning the analyzer instance itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Ensure the Mercurial client is closed when leaving a context manager block."""
        self.close()

    def get_modified_files(self, base_branch: str = "default") -> list[Path]:
        """Get list of files modified in current branch vs. base branch.

        Uses Mercurial's ancestor() revset function to find files that differ
        between the base branch and the current working directory.
        Only returns files that currently exist in the working tree (excludes deletions).

        Args:
            base_branch: Name of the base branch to compare against. Defaults to 'default'
                        (Mercurial's equivalent to Git's 'main').

        Returns:
            List of Path objects for modified files, relative to repository root.
            Returns empty list if no files are modified.

        Raises:
            BranchNotFoundError: If base_branch does not exist in the repository
            BranchAnalyzerError: If Mercurial command fails for other reasons
        """
        # Validate base branch exists
        if not self.validate_branch_exists(base_branch):
            raise BranchNotFoundError(f"Branch '{base_branch}' does not exist in repository")

        try:
            # Use ancestor() revset to get merge base, then compare to current working directory
            # This is the Mercurial equivalent of Git's three-dot diff syntax
            # Format: ancestor(base_branch, .) gives the common ancestor
            # Then status from that ancestor to current (.)
            ancestor_revset = f"ancestor({base_branch},.)"

            # Get status between merge base and current working directory
            # Returns list of (status_char, filename) tuples
            status_output = self.client.status(rev=[ancestor_revset.encode("utf-8"), b"."])

            if not status_output:
                return []

            # Filter to only existing files (exclude deletions)
            existing_files: list[Path] = []
            for status_char, filename_bytes in status_output:
                if status_char != b"R":  # Not removed
                    filename = filename_bytes.decode("utf-8")
                    full_path = self.repo_path / filename
                    if full_path.exists() and full_path.is_file():
                        # Return path relative to repo root
                        existing_files.append(Path(filename))

            return existing_files

        except hglib.error.CommandError as e:
            raise BranchAnalyzerError(f"Mercurial status command failed: {e}") from e
        except Exception as e:
            raise BranchAnalyzerError(f"Failed to get modified files: {e}") from e

    def get_current_branch(self) -> str:
        """Get name of the current active branch.

        Returns:
            Name of current branch (e.g., 'default', 'feature-branch')

        Raises:
            BranchAnalyzerError: If unable to determine current branch
        """
        try:
            branch_bytes: bytes = self.client.branch()
            return branch_bytes.decode("utf-8")
        except Exception as e:
            raise BranchAnalyzerError(f"Failed to get current branch: {e}") from e

    def validate_branch_exists(self, branch: str) -> bool:
        """Check if a branch exists in the repository.

        Checks both active and closed branches.

        Args:
            branch: Name of the branch to check

        Returns:
            True if branch exists, False otherwise
        """
        try:
            # Get list of branches (returns list of (name, rev, tip) tuples)
            branches = self.client.branches()

            # Check if branch name matches any existing branch
            for branch_info in branches:
                branch_name = branch_info[0].decode("utf-8")
                if branch_name == branch:
                    return True

            # Also check closed branches
            try:
                closed_branches = self.client.branches(closed=True)
                for branch_info in closed_branches:
                    branch_name = branch_info[0].decode("utf-8")
                    if branch_name == branch:
                        return True
            except Exception:  # noqa: S110
                # If we can't check closed branches, that's okay
                pass

            return False

        except Exception:
            # If we can't list branches, assume it doesn't exist
            return False

    def get_user_email(self) -> str:
        """Get configured Mercurial user email for project naming.

        Returns:
            User email from repository or global config

        Raises:
            BranchAnalyzerError: If user email is not configured
        """
        try:
            # Mercurial stores username in ui.username config
            # Format is typically "Name <email>" or just "email"
            username_bytes: bytes | None = self.client.config(b"ui", b"username")

            if not username_bytes:
                raise BranchAnalyzerError(  # noqa: TRY301
                    "Mercurial ui.username not configured. "
                    "Run: hg config --global ui.username 'Your Name <your@email.com>'"
                )

            username_str = username_bytes.decode("utf-8")

            # Extract email from "Name <email>" format
            email: str
            if "<" in username_str and ">" in username_str:
                email = username_str.split("<")[1].split(">")[0].strip()
            else:
                # Assume entire string is email
                email = username_str.strip()

            if not email:
                raise BranchAnalyzerError(  # noqa: TRY301
                    "Mercurial ui.username not configured. "
                    "Run: hg config --global ui.username 'Your Name <your@email.com>'"
                )

            return email

        except BranchAnalyzerError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            raise BranchAnalyzerError(f"Failed to get user email: {e}") from e
