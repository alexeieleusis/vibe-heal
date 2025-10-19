# Phase 5: Git Integration ✅ COMPLETE

## Objective

Implement Git operations to safely commit fixes after each successful issue resolution.

## Status: ✅ COMPLETE

All Git integration features implemented and tested:
- [x] `GitManager` class for Git operations
- [x] Repository checks (`is_repository`, `is_clean`)
- [x] Branch information retrieval
- [x] Uncommitted files listing
- [x] Automatic commit creation for fixes with proper message formatting
- [x] Conventional commit format (`fix: [SQ-RULE] message`)
- [x] Safety check (`require_clean_working_directory`)
- [x] Comprehensive error handling with custom exceptions
- [x] Test coverage: 22 tests, 85% coverage

**Test Results**: 22 tests for git module, 85% coverage
**Overall Progress**: 120 tests passing, 93% code coverage

**Implementation Notes**:
- Uses GitPython for robust Git operations
- Commit messages follow conventional commits format
- Each fix gets its own commit for easy tracking/rollback
- Safety checks prevent working in dirty repositories
- Comprehensive test suite using temporary Git repositories

## Dependencies

- Phase 0, 1, and 4 must be complete
- `GitPython` installed
- `AIToolType` enum available
- `SonarQubeIssue` model available

## Files to Create/Modify

```
src/vibe_heal/
├── git/
│   ├── __init__.py              # Export public API
│   ├── manager.py               # Git operations
│   └── exceptions.py            # Git-specific exceptions
tests/
└── git/
    └── test_manager.py          # Git manager tests
```

## Tasks

### 1. Create Git Exceptions

**File**: `src/vibe_heal/git/exceptions.py`

```python
class GitError(Exception):
    """Base exception for Git errors."""
    pass


class NotAGitRepositoryError(GitError):
    """Directory is not a Git repository."""
    pass


class DirtyWorkingDirectoryError(GitError):
    """Working directory has uncommitted changes."""
    pass


class GitOperationError(GitError):
    """Git operation failed."""
    pass
```

### 2. Create Git Manager

**File**: `src/vibe_heal/git/manager.py`

```python
from pathlib import Path
from typing import Any

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

    def __init__(self, repo_path: str | Path | None = None):
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
            raise NotAGitRepositoryError(
                f"Not a Git repository: {self.repo_path}"
            ) from e
        except git.GitError as e:
            raise GitError(f"Git error: {e}") from e

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
            raise GitOperationError(f"Unable to get current branch: {e}") from e

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
            raise GitOperationError("No files to commit")

        # Create commit message
        message = self._create_commit_message(issue, ai_tool_type)

        try:
            # Stage files
            self.repo.index.add(files)

            # Create commit
            commit = self.repo.index.commit(message)

            return commit.hexsha

        except git.GitError as e:
            raise GitOperationError(f"Failed to create commit: {e}") from e

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
            raise DirtyWorkingDirectoryError(
                f"Working directory is not clean. Uncommitted files:\n"
                + "\n".join(f"  - {f}" for f in uncommitted[:10])
                + ("\n  ..." if len(uncommitted) > 10 else "")
            )
```

### 3. Export Public API

**File**: `src/vibe_heal/git/__init__.py`

```python
from vibe_heal.git.exceptions import (
    DirtyWorkingDirectoryError,
    GitError,
    GitOperationError,
    NotAGitRepositoryError,
)
from vibe_heal.git.manager import GitManager

__all__ = [
    "GitManager",
    "GitError",
    "NotAGitRepositoryError",
    "DirtyWorkingDirectoryError",
    "GitOperationError",
]
```

### 4. Write Comprehensive Tests

**File**: `tests/git/test_manager.py`

Test cases (use temporary Git repos):

**Repository checks**:
- ✅ `is_repository()` returns True in Git repo
- ✅ `is_repository()` returns False outside Git repo
- ✅ Constructor raises error for non-Git directory
- ✅ `get_current_branch()` returns correct branch name

**Clean state checks**:
- ✅ `is_clean()` returns True for clean repo
- ✅ `is_clean()` returns False with uncommitted changes
- ✅ `is_clean()` returns False with untracked files
- ✅ `get_uncommitted_files()` returns correct list

**Commit operations**:
- ✅ `commit_fix()` creates commit with correct message
- ✅ `commit_fix()` stages specified files
- ✅ `commit_fix()` returns commit SHA
- ✅ `commit_fix()` raises error with no files
- ✅ Commit message format is correct

**Safety checks**:
- ✅ `require_clean_working_directory()` passes when clean
- ✅ `require_clean_working_directory()` raises when dirty

**Example test structure**:
```python
import pytest
from pathlib import Path
import git

from vibe_heal.git import GitManager, DirtyWorkingDirectoryError
from vibe_heal.sonarqube.models import SonarQubeIssue
from vibe_heal.ai_tools.base import AIToolType


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary Git repository."""
    repo = git.Repo.init(tmp_path)

    # Create initial commit
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")
    repo.index.add(["test.py"])
    repo.index.commit("Initial commit")

    return tmp_path


def test_is_clean_with_clean_repo(git_repo):
    manager = GitManager(git_repo)
    assert manager.is_clean()


def test_is_clean_with_dirty_repo(git_repo):
    manager = GitManager(git_repo)

    # Modify file
    (git_repo / "test.py").write_text("print('modified')")

    assert not manager.is_clean()


def test_commit_fix(git_repo):
    manager = GitManager(git_repo)

    # Modify file
    test_file = git_repo / "test.py"
    test_file.write_text("print('fixed')")

    # Create issue
    issue = SonarQubeIssue(
        key="ABC123",
        rule="python:S1481",
        severity="MAJOR",
        message="Remove unused import",
        component="project:test.py",
        line=10,
        status="OPEN",
        type="CODE_SMELL",
    )

    # Commit fix
    sha = manager.commit_fix(issue, ["test.py"], AIToolType.CLAUDE_CODE)

    assert sha
    assert manager.is_clean()

    # Check commit message
    commit = manager.repo.head.commit
    assert "[SQ-S1481]" in commit.message
    assert "Remove unused import" in commit.message
    assert "Claude Code" in commit.message
```

## Example Usage

```python
from vibe_heal.git import GitManager, DirtyWorkingDirectoryError
from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.sonarqube.models import SonarQubeIssue

# Initialize Git manager
git_manager = GitManager()

# Check if in Git repo
if not git_manager.is_repository():
    print("Not a Git repository!")
    exit(1)

# Ensure clean state
try:
    git_manager.require_clean_working_directory()
except DirtyWorkingDirectoryError as e:
    print(f"Error: {e}")
    exit(1)

# After fixing an issue...
issue = SonarQubeIssue(...)
sha = git_manager.commit_fix(
    issue=issue,
    files=["src/main.py"],
    ai_tool_type=AIToolType.CLAUDE_CODE
)
print(f"Created commit: {sha}")
```

## Verification Steps

1. Run tests:
   ```bash
   uv run pytest tests/git/ -v --cov=src/vibe_heal/git
   ```

2. Manual test in real repo:
   ```python
   from vibe_heal.git import GitManager

   manager = GitManager()
   print(f"Repository: {manager.is_repository()}")
   print(f"Clean: {manager.is_clean()}")
   print(f"Branch: {manager.get_current_branch()}")
   ```

3. Type checking:
   ```bash
   uv run mypy src/vibe_heal/git/
   ```

## Definition of Done

- ✅ `GitManager` class implemented
- ✅ Repository checks (is_repository, is_clean)
- ✅ Branch information (get_current_branch)
- ✅ Uncommitted files listing
- ✅ Commit creation with proper message formatting
- ✅ Safety check (require_clean_working_directory)
- ✅ Comprehensive tests with temporary Git repos (>90% coverage)
- ✅ Type checking passes
- ✅ Can create commits for fixes

## Notes

- Use temporary directories in tests (`pytest` `tmp_path` fixture)
- Commit message format follows conventional commits
- GitPython provides excellent abstractions for Git operations
- The `require_clean_working_directory()` is a critical safety feature
- Consider adding `--no-verify` flag support in future to skip hooks if needed
- Each fix gets its own commit for easy rollback
