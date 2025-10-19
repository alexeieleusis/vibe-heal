"""Git operations manager."""

from pathlib import Path

import git

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.git.exceptions import (
    DirtyWorkingDirectoryError,
    GitError,
    GitOperationError,
    NotAGitRepositoryError,
)
from vibe_heal.sonarqube.models import SonarQubeIssue


class GitManager:
    """Manages Git operations for vibe-heal."""

    def __init__(self, repo_path: str | Path | None = None) -> None:
        """Initialize Git manager.

        Args:
            repo_path: Path to Git repository (default: current directory)

        Raises:
            NotAGitRepositoryError: If path is not a Git repository
        """
        self.repo_path = Path(repo_path or Path.cwd())

        try:
            self.repo = git.Repo(self.repo_path, search_parent_directories=True)
        except git.InvalidGitRepositoryError as e:
            msg = f"Not a Git repository: {self.repo_path}"
            raise NotAGitRepositoryError(msg) from e
        except git.GitError as e:
            msg = f"Git error: {e}"
            raise GitError(msg) from e

    def is_repository(self) -> bool:
        """Check if current directory is a Git repository.

        Returns:
            True if in a Git repository
        """
        try:
            return self.repo.git_dir is not None
        except Exception:
            return False

    def is_clean(self) -> bool:
        """Check if working directory is clean (no uncommitted changes).

        Returns:
            True if working directory is clean
        """
        return not self.repo.is_dirty(untracked_files=True)

    def get_current_branch(self) -> str:
        """Get the name of the current branch.

        Returns:
            Current branch name

        Raises:
            GitOperationError: If unable to determine branch
        """
        try:
            return self.repo.active_branch.name
        except Exception as e:
            msg = f"Unable to get current branch: {e}"
            raise GitOperationError(msg) from e

    def get_uncommitted_files(self) -> list[str]:
        """Get list of uncommitted files.

        Returns:
            List of file paths with uncommitted changes
        """
        changed = [item.a_path for item in self.repo.index.diff(None)]
        staged = [item.a_path for item in self.repo.index.diff("HEAD")]
        untracked = self.repo.untracked_files

        return list(set(changed + staged + untracked))

    def commit_fix(
        self,
        issue: SonarQubeIssue,
        files: list[str],
        ai_tool_type: AIToolType,
    ) -> str:
        """Create a commit for a fixed issue.

        Args:
            issue: The SonarQube issue that was fixed
            files: List of files to commit
            ai_tool_type: The AI tool used for the fix

        Returns:
            Commit SHA

        Raises:
            GitOperationError: If commit fails
        """
        if not files:
            msg = "No files to commit"
            raise GitOperationError(msg)

        # Create commit message
        message = self._create_commit_message(issue, ai_tool_type)

        try:
            # Stage files
            self.repo.index.add(files)

            # Create commit
            commit = self.repo.index.commit(message)

            return commit.hexsha

        except git.GitError as e:
            msg = f"Failed to create commit: {e}"
            raise GitOperationError(msg) from e

    def _create_commit_message(
        self,
        issue: SonarQubeIssue,
        ai_tool_type: AIToolType,
    ) -> str:
        """Create a formatted commit message for a fix.

        Args:
            issue: The SonarQube issue that was fixed
            ai_tool_type: The AI tool used for the fix

        Returns:
            Formatted commit message
        """
        # Extract rule name (e.g., "python:S1481" -> "S1481")
        rule_short = issue.rule.split(":")[-1] if ":" in issue.rule else issue.rule

        # Create subject line
        subject = f"fix: [SQ-{rule_short}] {issue.message[:50]}"
        if len(issue.message) > 50:
            subject = subject.rstrip() + "..."

        # Create body
        body_parts = [
            f"Fixes SonarQube issue on line {issue.line}",
            f"Rule: {issue.rule}",
            f"Severity: {issue.severity}",
            f"Type: {issue.type}",
            f"Message: {issue.message}",
            "",
            f"Fixed by vibe-heal using {ai_tool_type.display_name}",
        ]

        body = "\n".join(body_parts)

        # Combine subject and body
        return f"{subject}\n\n{body}"

    def require_clean_working_directory(self) -> None:
        """Ensure working directory is clean.

        Raises:
            DirtyWorkingDirectoryError: If working directory is dirty
        """
        if not self.is_clean():
            uncommitted = self.get_uncommitted_files()
            msg = (
                "Working directory is not clean. Uncommitted files:\n"
                + "\n".join(f"  - {f}" for f in uncommitted[:10])
                + ("\n  ..." if len(uncommitted) > 10 else "")
            )
            raise DirtyWorkingDirectoryError(msg)
