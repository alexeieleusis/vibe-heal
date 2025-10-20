"""Tests for Git manager."""

from pathlib import Path

import git
import pytest

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.git import (
    DirtyWorkingDirectoryError,
    GitManager,
    GitOperationError,
    NotAGitRepositoryError,
)
from vibe_heal.sonarqube.models import SonarQubeIssue


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary Git repository.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        Path to the temporary Git repository
    """
    repo = git.Repo.init(tmp_path)

    # Create initial commit
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")
    repo.index.add(["test.py"])
    repo.index.commit("Initial commit")

    return tmp_path


@pytest.fixture
def sample_issue() -> SonarQubeIssue:
    """Create a sample issue for testing.

    Returns:
        Sample SonarQube issue
    """
    return SonarQubeIssue(
        key="ABC123",
        rule="python:S1481",
        severity="MAJOR",
        message="Remove unused import",
        component="project:test.py",
        line=10,
        status="OPEN",
        type="CODE_SMELL",
    )


class TestGitManagerInit:
    """Tests for GitManager initialization."""

    def test_init_with_git_repo(self, git_repo: Path) -> None:
        """Test initialization in a Git repository."""
        manager = GitManager(git_repo)

        assert manager.repo_path == git_repo
        assert manager.is_repository()

    def test_init_with_current_directory(self, git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with current directory."""
        monkeypatch.chdir(git_repo)

        manager = GitManager()

        assert manager.is_repository()

    def test_init_with_non_git_directory(self, tmp_path: Path) -> None:
        """Test initialization fails for non-Git directory."""
        non_git_dir = tmp_path / "not_a_repo"
        non_git_dir.mkdir()

        with pytest.raises(NotAGitRepositoryError, match="Not a Git repository"):
            GitManager(non_git_dir)


class TestGitManagerRepository:
    """Tests for repository checks."""

    def test_is_repository_in_git_repo(self, git_repo: Path) -> None:
        """Test is_repository returns True in Git repo."""
        manager = GitManager(git_repo)

        assert manager.is_repository() is True

    def test_get_current_branch(self, git_repo: Path) -> None:
        """Test getting current branch name."""
        manager = GitManager(git_repo)

        # Git repos default to 'master' or 'main'
        branch = manager.get_current_branch()
        assert branch in ["master", "main"]

    def test_get_current_branch_custom_name(self, git_repo: Path) -> None:
        """Test getting current branch with custom name."""
        manager = GitManager(git_repo)

        # Create and checkout a new branch
        manager.repo.create_head("feature-branch")
        manager.repo.heads["feature-branch"].checkout()

        assert manager.get_current_branch() == "feature-branch"


class TestGitManagerCleanState:
    """Tests for clean state checks."""

    def test_is_clean_with_clean_repo(self, git_repo: Path) -> None:
        """Test is_clean returns True for clean repo."""
        manager = GitManager(git_repo)

        assert manager.is_clean() is True

    def test_is_clean_with_modified_file(self, git_repo: Path) -> None:
        """Test is_clean returns False with modified file."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('modified')")

        assert manager.is_clean() is False

    def test_is_clean_with_untracked_file(self, git_repo: Path) -> None:
        """Test is_clean returns False with untracked file."""
        manager = GitManager(git_repo)

        # Create untracked file
        (git_repo / "new_file.py").write_text("print('new')")

        assert manager.is_clean() is False

    def test_is_clean_with_staged_file(self, git_repo: Path) -> None:
        """Test is_clean returns False with staged file."""
        manager = GitManager(git_repo)

        # Modify and stage file
        (git_repo / "test.py").write_text("print('staged')")
        manager.repo.index.add(["test.py"])

        assert manager.is_clean() is False

    def test_get_uncommitted_files_empty(self, git_repo: Path) -> None:
        """Test get_uncommitted_files returns empty list for clean repo."""
        manager = GitManager(git_repo)

        uncommitted = manager.get_uncommitted_files()

        assert uncommitted == []

    def test_get_uncommitted_files_with_changes(self, git_repo: Path) -> None:
        """Test get_uncommitted_files returns list of changed files."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('modified')")

        # Create untracked file
        (git_repo / "new_file.py").write_text("print('new')")

        uncommitted = manager.get_uncommitted_files()

        assert "test.py" in uncommitted
        assert "new_file.py" in uncommitted


class TestGitManagerCommit:
    """Tests for commit operations."""

    def test_commit_fix_creates_commit(
        self,
        git_repo: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test commit_fix creates a commit."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('fixed')")

        # Commit fix
        sha = manager.commit_fix(sample_issue, ["test.py"], AIToolType.CLAUDE_CODE)

        assert sha
        assert len(sha) == 40  # SHA-1 hex length
        assert manager.is_clean()

    def test_commit_fix_message_format(
        self,
        git_repo: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test commit_fix creates commit with correct message."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('fixed')")

        # Commit fix (without rule details)
        manager.commit_fix(sample_issue, ["test.py"], AIToolType.CLAUDE_CODE, rule=None)

        # Check commit message (should use old format without rule)
        commit = manager.repo.head.commit
        assert "[SQ-S1481]" in commit.message
        assert "Remove unused import" in commit.message
        assert "python:S1481" in commit.message
        assert "MAJOR" in commit.message
        assert "Claude Code" in commit.message

    def test_commit_fix_message_truncation(self, git_repo: Path) -> None:
        """Test commit_fix truncates long messages."""
        manager = GitManager(git_repo)

        # Create issue with long message
        long_message = "A" * 100
        issue = SonarQubeIssue(
            key="ABC123",
            rule="python:S1481",
            severity="MAJOR",
            message=long_message,
            component="project:test.py",
            line=10,
            status="OPEN",
            type="CODE_SMELL",
        )

        # Modify file
        (git_repo / "test.py").write_text("print('fixed')")

        # Commit fix
        manager.commit_fix(issue, ["test.py"], AIToolType.CLAUDE_CODE)

        # Check commit message subject line
        commit = manager.repo.head.commit
        subject_line = commit.message.split("\n")[0]

        # Subject should be truncated with "..."
        assert len(subject_line) < len(long_message) + 20  # +20 for prefix
        assert "..." in subject_line

    def test_commit_fix_stages_files(
        self,
        git_repo: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test commit_fix stages specified files."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('fixed')")

        # Commit fix
        manager.commit_fix(sample_issue, ["test.py"], AIToolType.CLAUDE_CODE)

        # File should be in the commit
        commit = manager.repo.head.commit
        assert "test.py" in commit.stats.files

    def test_commit_fix_multiple_files(
        self,
        git_repo: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test commit_fix handles multiple files."""
        manager = GitManager(git_repo)

        # Create and modify multiple files
        (git_repo / "test.py").write_text("print('fixed 1')")
        file2 = git_repo / "test2.py"
        file2.write_text("print('fixed 2')")

        # Commit fix with multiple files
        manager.commit_fix(sample_issue, ["test.py", "test2.py"], AIToolType.CLAUDE_CODE)

        # Both files should be in the commit
        commit = manager.repo.head.commit
        assert "test.py" in commit.stats.files
        assert "test2.py" in commit.stats.files

    def test_commit_fix_raises_with_no_files(
        self,
        git_repo: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test commit_fix raises error with no files."""
        manager = GitManager(git_repo)

        with pytest.raises(GitOperationError, match="No files to commit"):
            manager.commit_fix(sample_issue, [], AIToolType.CLAUDE_CODE)

    def test_commit_fix_returns_sha(
        self,
        git_repo: Path,
        sample_issue: SonarQubeIssue,
    ) -> None:
        """Test commit_fix returns commit SHA."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('fixed')")

        # Commit fix
        sha = manager.commit_fix(sample_issue, ["test.py"], AIToolType.CLAUDE_CODE)

        # Verify SHA matches actual commit
        assert sha == manager.repo.head.commit.hexsha


class TestGitManagerSafety:
    """Tests for safety checks."""

    def test_require_clean_working_directory_passes_when_clean(
        self,
        git_repo: Path,
    ) -> None:
        """Test require_clean_working_directory passes when clean."""
        manager = GitManager(git_repo)

        # Should not raise
        manager.require_clean_working_directory()

    def test_require_clean_working_directory_raises_when_dirty(
        self,
        git_repo: Path,
    ) -> None:
        """Test require_clean_working_directory raises when dirty."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('modified')")

        with pytest.raises(DirtyWorkingDirectoryError, match="not clean"):
            manager.require_clean_working_directory()

    def test_require_clean_working_directory_lists_files(
        self,
        git_repo: Path,
    ) -> None:
        """Test require_clean_working_directory lists uncommitted files."""
        manager = GitManager(git_repo)

        # Modify file
        (git_repo / "test.py").write_text("print('modified')")

        with pytest.raises(DirtyWorkingDirectoryError, match="test.py"):
            manager.require_clean_working_directory()
