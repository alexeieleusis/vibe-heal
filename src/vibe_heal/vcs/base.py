"""Abstract base classes for version control system operations.

This module defines the common interface that all VCS implementations
(Git, Mercurial, etc.) must implement.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.sonarqube.models import SonarQubeIssue, SonarQubeRule
from vibe_heal.vcs.exceptions import DirtyWorkingDirectoryError


class VCSManager(ABC):
    """Abstract base class for version control system managers.

    Provides common interface for Git, Mercurial, and other VCS operations.
    Each concrete implementation must provide all the methods defined here.
    """

    @abstractmethod
    def __init__(self, repo_path: str | Path | None = None) -> None:
        """Initialize VCS manager.

        Args:
            repo_path: Path to repository (default: current directory)

        Raises:
            NotARepositoryError: If path is not a valid repository
        """

    @abstractmethod
    def is_repository(self) -> bool:
        """Check if current directory is a repository.

        Returns:
            True if in a repository
        """

    @abstractmethod
    def is_clean(self) -> bool:
        """Check if working directory is clean (no uncommitted changes).

        Returns:
            True if working directory is clean
        """

    @abstractmethod
    def get_current_branch(self) -> str:
        """Get the name of the current branch.

        Returns:
            Current branch name

        Raises:
            VCSOperationError: If unable to determine branch
        """

    @abstractmethod
    def get_uncommitted_files(self) -> list[str]:
        """Get list of uncommitted files.

        Returns:
            List of file paths with uncommitted changes
        """

    @abstractmethod
    def get_modified_or_staged_files(self) -> list[str]:
        """Get list of modified or staged files (excluding untracked files).

        Returns:
            List of file paths that are modified or staged (but not untracked)
        """

    @abstractmethod
    def has_modified_or_staged_files(self) -> bool:
        """Check if there are any modified or staged files (excluding untracked).

        Returns:
            True if there are modified or staged files
        """

    @abstractmethod
    def get_all_modified_files(self) -> list[str]:
        """Get all files that have been modified in the working directory.

        This includes both staged and unstaged changes, but excludes untracked files.

        Returns:
            List of file paths with modifications
        """

    @abstractmethod
    def has_uncommitted_changes(self, file_path: str) -> bool:
        """Check if a specific file has uncommitted changes.

        Args:
            file_path: Path to file to check

        Returns:
            True if file has uncommitted changes or is staged
        """

    @abstractmethod
    def commit_fix(
        self,
        issue: SonarQubeIssue,
        files: list[str] | None,
        ai_tool_type: AIToolType,
        rule: SonarQubeRule | None = None,
    ) -> str | None:
        """Create a commit for a fixed issue.

        If files is None, automatically detects and commits all modified files.
        If files is an empty list, raises an error.

        Args:
            issue: The SonarQube issue that was fixed
            files: List of files to commit, or None to auto-detect all modified files
            ai_tool_type: The AI tool used for the fix
            rule: Detailed rule information (optional)

        Returns:
            Commit identifier (SHA/hash), or None if there were no changes to commit

        Raises:
            VCSOperationError: If commit fails or no files to commit
        """

    @abstractmethod
    def create_commit(
        self,
        message: str,
        files: list[str] | None = None,
        include_untracked: bool = False,
    ) -> str | None:
        """Create a commit with a custom message.

        If files is None, automatically detects and commits all modified files.

        Args:
            message: Commit message
            files: List of files to commit, or None to auto-detect all modified files
            include_untracked: If True, include untracked (new) files in auto-detection

        Returns:
            Commit identifier, or None if there were no changes to commit

        Raises:
            VCSOperationError: If commit fails or no files to commit
        """

    def require_clean_working_directory(self) -> None:
        """Ensure working directory has no modified or staged files.

        Untracked files are allowed, but modified or staged files must be committed first.

        Raises:
            DirtyWorkingDirectoryError: If there are modified or staged files
        """
        modified_or_staged = self.get_modified_or_staged_files()
        if modified_or_staged:
            msg = (
                "Working directory has uncommitted changes. Please commit or stash modified files first.\n"
                "Modified or staged files:\n"
                + "\n".join(f"  - {f}" for f in modified_or_staged[:10])
                + ("\n  ..." if len(modified_or_staged) > 10 else "")
                + "\n\nNote: Untracked files are OK and won't block processing."
            )
            raise DirtyWorkingDirectoryError(msg)

    def _create_commit_message(
        self,
        issue: SonarQubeIssue,
        ai_tool_type: AIToolType,
        rule: SonarQubeRule | None = None,
        file_count: int = 1,
    ) -> str:
        """Create a formatted commit message for a fix.

        Args:
            issue: The SonarQube issue that was fixed
            ai_tool_type: The AI tool used for the fix
            rule: Detailed rule information (optional)
            file_count: Number of files modified in this fix (default: 1)

        Returns:
            Formatted commit message
        """
        # Extract rule name (e.g., "python:S1481" -> "S1481")
        rule_short = issue.rule.split(":")[-1] if ":" in issue.rule else issue.rule

        # Create subject line (use rule name if available)
        if rule:
            subject = f"fix: [{issue.rule}] {issue.message[:50]}"
        else:
            subject = f"fix: [SQ-{rule_short}] {issue.message[:50]}"

        if len(issue.message) > 50:
            subject = subject.rstrip() + "..."

        # Create body
        body_parts = [
            f"SonarQube Issue: {issue.key}",
        ]

        if rule:
            body_parts.append(f"Rule: {issue.rule} - {rule.name}")
        else:
            body_parts.append(f"Rule: {issue.rule}")

        body_parts.extend([
            f"Severity: {issue.severity}",
            f"Location: {issue.component}:{issue.line}",
        ])

        # Add file count if multiple files were modified
        if file_count > 1:
            body_parts.append(f"Files modified: {file_count}")

        body_parts.append("")

        # Add public documentation link
        if rule:
            body_parts.extend([
                f"Rationale: {rule.public_doc_url}",
                "",
            ])

        body_parts.extend([
            f"Fixed by: vibe-heal using {ai_tool_type.display_name}",
            "",
            "[vibe-heal](https://github.com/alexeieleusis/vibe-heal)",
        ])

        body = "\n".join(body_parts)

        # Combine subject and body
        return f"{subject}\n\n{body}"


class BranchAnalyzer(ABC):
    """Abstract base class for branch analysis operations.

    Provides common interface for analyzing branch differences across VCS.
    """

    @abstractmethod
    def __init__(self, repo_path: Path) -> None:
        """Initialize the branch analyzer.

        Args:
            repo_path: Path to the repository root

        Raises:
            InvalidRepositoryError: If repo_path is not a valid repository
        """

    @abstractmethod
    def get_modified_files(self, base_branch: str = "origin/main") -> list[Path]:
        """Get list of files modified in current branch vs. base branch.

        Only returns files that currently exist in the working tree (excludes deletions).

        Args:
            base_branch: Name of the base branch to compare against.
                        For Git: 'origin/main' or 'main'
                        For Mercurial: 'default' or 'main'

        Returns:
            List of Path objects for modified files, relative to repository root.
            Returns empty list if no files are modified.

        Raises:
            BranchNotFoundError: If base_branch does not exist in the repository
            BranchAnalyzerError: If comparison fails for other reasons
        """

    @abstractmethod
    def get_current_branch(self) -> str:
        """Get name of the current active branch.

        Returns:
            Name of current branch (e.g., 'feature/new-api', 'main', 'default')

        Raises:
            BranchAnalyzerError: If unable to determine current branch
        """

    @abstractmethod
    def validate_branch_exists(self, branch: str) -> bool:
        """Check if a branch exists in the repository.

        Checks both local and remote branches where applicable.

        Args:
            branch: Name of the branch to check

        Returns:
            True if branch exists (locally or remotely), False otherwise
        """

    @abstractmethod
    def get_user_email(self) -> str:
        """Get configured VCS user email for project naming.

        Returns:
            User email from repository or global config

        Raises:
            BranchAnalyzerError: If user email is not configured
        """
