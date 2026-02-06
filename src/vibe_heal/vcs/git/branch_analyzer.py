"""Git branch analysis for identifying modified files."""

from pathlib import Path

from git import GitCommandError, Repo
from git.exc import InvalidGitRepositoryError as GitInvalidRepoError

from vibe_heal.vcs.base import BranchAnalyzer
from vibe_heal.vcs.exceptions import (
    BranchAnalyzerError,
    BranchNotFoundError,
    InvalidRepositoryError,
)


class GitBranchAnalyzer(BranchAnalyzer):
    """Analyzes differences between git branches to identify modified files.

    This class provides functionality to compare the current branch with a base
    branch and identify which files have been modified, added, or changed.
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize the GitBranchAnalyzer.

        Args:
            repo_path: Path to the git repository root

        Raises:
            InvalidRepositoryError: If repo_path is not a valid git repository
        """
        super().__init__(repo_path)
        try:
            self.repo = Repo(repo_path, search_parent_directories=True)
        except GitInvalidRepoError as e:
            raise InvalidRepositoryError(f"Not a valid git repository: {repo_path}") from e

        self.repo_path = Path(self.repo.working_dir)

    def get_modified_files(self, base_branch: str = "origin/main") -> list[Path]:
        """Get list of files modified in current branch vs. base branch.

        Uses git diff to find files that differ between the base branch and HEAD.
        Only returns files that currently exist in the working tree (excludes deletions).

        Args:
            base_branch: Name of the base branch to compare against. Defaults to 'origin/main'.

        Returns:
            List of Path objects for modified files, relative to repository root.
            Returns empty list if no files are modified.

        Raises:
            BranchNotFoundError: If base_branch does not exist in the repository
            BranchAnalyzerError: If git command fails for other reasons
        """
        # Validate base branch exists
        if not self.validate_branch_exists(base_branch):
            raise BranchNotFoundError(f"Branch '{base_branch}' does not exist in repository")

        try:
            # Use three-dot diff syntax to compare merge base
            # This shows changes on current branch since it diverged from base_branch
            diff_output = self.repo.git.diff("--name-only", f"{base_branch}...HEAD")

            if not diff_output.strip():
                return []

            # Parse file paths from diff output
            file_paths = [line.strip() for line in diff_output.split("\n") if line.strip()]

            # Filter to only existing files (exclude deletions)
            existing_files: list[Path] = []
            for file_path in file_paths:
                full_path = self.repo_path / file_path
                if full_path.exists() and full_path.is_file():
                    # Return path relative to repo root
                    existing_files.append(Path(file_path))

            return existing_files

        except GitCommandError as e:
            raise BranchAnalyzerError(f"Git diff command failed: {e}") from e

    def get_current_branch(self) -> str:
        """Get name of the current active branch.

        Returns:
            Name of current branch (e.g., 'feature/new-api', 'main')

        Raises:
            BranchAnalyzerError: If unable to determine current branch (e.g., detached HEAD)
        """

        def _raise_if_detached() -> None:
            if self.repo.head.is_detached:
                raise BranchAnalyzerError("Repository is in detached HEAD state")

        try:
            _raise_if_detached()
            branch_name = self.repo.active_branch.name
            return branch_name

        except Exception as e:
            raise BranchAnalyzerError(f"Failed to get current branch: {e}") from e

    def validate_branch_exists(self, branch: str) -> bool:
        """Check if a branch exists in the repository.

        Checks both local and remote branches. Supports both simple names (e.g., 'main')
        and remote refs (e.g., 'origin/main').

        Args:
            branch: Name of the branch to check

        Returns:
            True if branch exists (locally or remotely), False otherwise
        """
        try:
            # Check if it's a remote ref (e.g., origin/main)
            if "/" in branch:
                remote_name, branch_name = branch.split("/", 1)
                try:
                    remote = self.repo.remote(remote_name)
                    remote_branches = [ref.name for ref in remote.refs]
                    return f"{remote_name}/{branch_name}" in remote_branches
                except Exception:
                    # Cannot access remote, assume branch doesn't exist
                    return False

            # Check local branches
            local_branches = [ref.name for ref in self.repo.branches]
            if branch in local_branches:
                return True

            # Check default remote branches (origin/branch)
            try:
                remote_branches = [ref.name.split("/", 1)[1] for ref in self.repo.remote().refs]
                if branch in remote_branches:
                    return True
            except GitCommandError:
                # Cannot access default remote, assume branch doesn't exist
                pass

            return False

        except Exception:
            # If we can't list branches, assume it doesn't exist
            return False

    def get_user_email(self) -> str:
        """Get configured git user email for project naming.

        Returns:
            Git user email from repository or global config

        Raises:
            BranchAnalyzerError: If user email is not configured
        """

        def _validate_email_is_string(email: str | int | float | None) -> str:
            """Validate that email is a non-empty string."""
            if not email or not isinstance(email, str):
                raise BranchAnalyzerError("Git user email not configured. Run: git config user.email 'your@email.com'")
            return email

        try:
            # Try repository config first, then global config
            email = self.repo.config_reader().get_value("user", "email", default=None)
            return _validate_email_is_string(email)

        except BranchAnalyzerError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            raise BranchAnalyzerError(f"Failed to get user email: {e}") from e
