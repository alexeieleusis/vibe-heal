"""Mercurial operations manager."""

from pathlib import Path

import hglib  # type: ignore[import-untyped]

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.sonarqube.models import SonarQubeIssue, SonarQubeRule
from vibe_heal.vcs.base import VCSManager
from vibe_heal.vcs.exceptions import (
    DirtyWorkingDirectoryError,
    NotARepositoryError,
    VCSOperationError,
)


class MercurialManager(VCSManager):
    """Manages Mercurial operations for vibe-heal."""

    def __init__(self, repo_path: str | Path | None = None) -> None:
        """Initialize Mercurial manager.

        Args:
            repo_path: Path to Mercurial repository (default: current directory)

        Raises:
            NotARepositoryError: If path is not a Mercurial repository
        """
        self.repo_path = Path(repo_path or Path.cwd())

        try:
            # hglib.open searches parent directories automatically
            self.client = hglib.open(str(self.repo_path))
        except hglib.error.ServerError as e:
            msg = f"Not a Mercurial repository: {self.repo_path}"
            raise NotARepositoryError(msg) from e
        except Exception as e:
            msg = f"Mercurial error: {e}"
            raise VCSOperationError(msg) from e

    def __del__(self) -> None:
        """Close the Mercurial client on cleanup."""
        if hasattr(self, "client"):
            try:  # noqa: SIM105
                self.client.close()
            except Exception:  # noqa: S110
                pass

    def is_repository(self) -> bool:
        """Check if current directory is a Mercurial repository.

        Returns:
            True if in a Mercurial repository
        """
        try:
            return (self.repo_path / ".hg").exists()
        except Exception:
            return False

    def is_clean(self) -> bool:
        """Check if working directory is clean (no uncommitted changes).

        Returns:
            True if working directory is clean
        """
        try:
            status = self.client.status()
            # Clean if no files are modified (M), added (A), removed (R), or untracked (?)
            return len(status) == 0
        except Exception:
            return False

    def get_current_branch(self) -> str:
        """Get the name of the current branch.

        Returns:
            Current branch name

        Raises:
            VCSOperationError: If unable to determine branch
        """
        try:
            branch_bytes: bytes = self.client.branch()
            return branch_bytes.decode("utf-8")
        except Exception as e:
            msg = f"Unable to get current branch: {e}"
            raise VCSOperationError(msg) from e

    def get_uncommitted_files(self) -> list[str]:
        """Get list of uncommitted files.

        Returns:
            List of file paths with uncommitted changes
        """
        try:
            status = self.client.status()
            # Include all files: M (modified), A (added), R (removed), ? (untracked)
            return [f[1].decode("utf-8") for f in status if f[0] != b"C"]
        except Exception:
            return []

    def get_modified_or_staged_files(self) -> list[str]:
        """Get list of modified or staged files (excluding untracked files).

        Returns:
            List of file paths that are modified or staged (but not untracked)
        """
        try:
            status = self.client.status()
            # Only modified (M), added (A), or removed (R) - exclude untracked (?)
            return [f[1].decode("utf-8") for f in status if f[0] in b"MAR"]
        except Exception:
            return []

    def has_modified_or_staged_files(self) -> bool:
        """Check if there are any modified or staged files (excluding untracked).

        Returns:
            True if there are modified or staged files
        """
        return len(self.get_modified_or_staged_files()) > 0

    def get_all_modified_files(self) -> list[str]:
        """Get all files that have been modified in the working directory.

        This includes both staged and unstaged changes, but excludes untracked files.

        Returns:
            List of file paths with modifications
        """
        return self.get_modified_or_staged_files()

    def has_uncommitted_changes(self, file_path: str) -> bool:
        """Check if a specific file has uncommitted changes.

        Args:
            file_path: Path to file to check

        Returns:
            True if file has uncommitted changes or is staged
        """
        try:
            # Normalize path to match Mercurial's format
            file_path_normalized = str(Path(file_path))

            # Get status for all files
            status = self.client.status()

            # Check if file appears in status with M, A, or R
            for status_char, filename_bytes in status:
                filename = filename_bytes.decode("utf-8")
                if filename == file_path_normalized and status_char in b"MAR":
                    return True

            return False
        except Exception:
            return False

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
            Commit changeset hash, or None if there were no changes to commit

        Raises:
            VCSOperationError: If commit fails or no files to commit
        """
        # Handle empty list case (explicit request with no files)
        if files is not None and not files:
            msg = "No files to commit"
            raise VCSOperationError(msg)

        # Auto-detect modified files if not provided
        auto_detect = files is None
        if auto_detect:
            files = self.get_all_modified_files()

        # If no modified files in auto-detect mode, check if already committed
        # This handles the case where one fix resolved multiple issues
        if auto_detect and not files:
            # Check if there are any uncommitted changes at all
            status = self.client.status()
            if not status:
                # No changes - issue was already fixed
                return None

        # At this point, files must be a list (either from auto-detect or passed in)
        if files is None:
            msg = "Internal error: files should not be None at this point"
            raise VCSOperationError(msg)

        # Determine correct file count for commit message
        if auto_detect and not files:
            # Count staged files
            status = self.client.status()
            file_count_for_message = len([f for f in status if f[0] in b"MAR"])
        else:
            file_count_for_message = len(files)

        # Create commit message
        message = self._create_commit_message(issue, ai_tool_type, rule, file_count_for_message)

        # Stage and commit using helper method
        return self._stage_and_commit(files, message)

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
            Commit changeset hash, or None if there were no changes to commit

        Raises:
            VCSOperationError: If commit fails or no files to commit
        """
        # Auto-detect modified files if not provided
        if files is None:
            files = self.get_all_modified_files()
            # Add untracked files if requested (e.g., for deduplication when AI creates new files)
            if include_untracked:
                status = self.client.status()
                untracked = [f[1].decode("utf-8") for f in status if f[0] == b"?"]
                files.extend(untracked)

        if not files:
            msg = "No files to commit"
            raise VCSOperationError(msg)

        # Stage and commit using helper method
        return self._stage_and_commit(files, message)

    def _stage_and_commit(self, files: list[str], message: str) -> str | None:
        """Stage files and create a commit if there are changes.

        Args:
            files: List of files to stage
            message: Commit message

        Returns:
            Commit changeset hash, or None if there were no changes to commit

        Raises:
            VCSOperationError: If commit fails
        """
        try:
            # Add files (hglib requires bytes and paths relative to repo root)
            if files:
                # Convert file paths to be relative to repo root
                relative_files = []
                for f in files:
                    file_path = Path(f)
                    # If relative, make it relative to repo root
                    if not file_path.is_absolute():
                        file_path = self.repo_path / file_path
                    # Make absolute path relative to repo root
                    try:  # noqa: SIM105
                        file_path = file_path.relative_to(self.repo_path.resolve())
                    except ValueError:
                        # File is not under repo root - use as-is
                        pass
                    relative_files.append(str(file_path))

                files_bytes = [f.encode("utf-8") for f in relative_files]
                self.client.add(files_bytes)

            # Check if there are any changes to commit after staging
            status = self.client.status()
            modified_or_staged = [f for f in status if f[0] in b"MAR"]
            if not modified_or_staged:
                # No changes staged - return None to indicate no commit was created
                return None

            # Create commit (returns changeset hash as bytes or None)
            commit_hash_bytes: bytes | None = self.client.commit(message.encode("utf-8"))

            if commit_hash_bytes:
                return commit_hash_bytes.decode("utf-8")
            return None

        except hglib.error.CommandError as e:
            msg = f"Failed to create commit: {e}"
            raise VCSOperationError(msg) from e
        except Exception as e:
            msg = f"Failed to create commit: {e}"
            raise VCSOperationError(msg) from e

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

        body_parts.append(f"Fixed by: vibe-heal using {ai_tool_type.display_name}")

        body = "\n".join(body_parts)

        # Combine subject and body
        return f"{subject}\n\n{body}"

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
