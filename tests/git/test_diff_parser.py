"""Tests for DiffParser class."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import GitCommandError, Repo

from vibe_heal.git.diff_parser import DiffParser, DiffParserError

DIFF_SIMPLE_ADD = """\
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -5 +5,3 @@
+new line one
+new line two
+new line three
"""

DIFF_PURE_DELETION = """\
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -3,2 +3 @@
-deleted line one
-deleted line two
"""

DIFF_MODIFICATION = """\
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -3 +3 @@
-old line
+new line
"""

DIFF_MULTIPLE_HUNKS = """\
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -3 +3 @@
-old
+new
@@ -10,0 +11 @@
+inserted line
"""

DIFF_MULTIPLE_FILES = """\
diff --git a/src/file1.py b/src/file1.py
index 1234567..abcdefg 100644
--- a/src/file1.py
+++ b/src/file1.py
@@ -5,0 +5 @@
+added in file1
diff --git a/src/file2.py b/src/file2.py
index 1111111..2222222 100644
--- a/src/file2.py
+++ b/src/file2.py
@@ -10 +10 @@
-old in file2
+new in file2
"""

DIFF_EMPTY = ""

DIFF_BINARY = """\
diff --git a/image.png b/image.png
new file mode 100644
Binary files /dev/null and b/image.png differ
"""

DIFF_RENAMED_FILE = """\
diff --git a/src/old_name.py b/src/new_name.py
similarity index 90%
rename from src/old_name.py
rename to src/new_name.py
index 1234567..abcdefg 100644
--- a/src/old_name.py
+++ b/src/new_name.py
@@ -5 +5 @@
-old content
+new content
"""

DIFF_MIXED_HUNKS = """\
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -3,0 +3 @@
+added at 3
@@ -7 +6 @@
-deleted at 7
@@ -12 +10,0 @@
+added at 10
"""


@pytest.fixture
def mock_repo(tmp_path: Path) -> MagicMock:
    """Create a mock Git repository."""
    repo = MagicMock(spec=Repo)
    repo.working_dir = str(tmp_path)
    return repo


@pytest.fixture
def parser(tmp_path: Path, mock_repo: MagicMock) -> DiffParser:
    """Create a DiffParser instance with mocked repo."""
    with patch("vibe_heal.git.diff_parser.Repo", return_value=mock_repo):
        p = DiffParser(tmp_path)
    return p


class TestDiffParserInit:
    """Tests for DiffParser initialization."""

    def test_init_valid_repo(self, tmp_path: Path, mock_repo: MagicMock) -> None:
        """Test initialization with valid repository."""
        with patch("vibe_heal.git.diff_parser.Repo", return_value=mock_repo):
            p = DiffParser(tmp_path)

        assert p.repo == mock_repo

    def test_init_invalid_repo(self, tmp_path: Path) -> None:
        """Test initialization with invalid repository raises error."""
        from git.exc import InvalidGitRepositoryError

        with (
            patch(
                "vibe_heal.git.diff_parser.Repo",
                side_effect=InvalidGitRepositoryError("Not a git repo"),
            ),
            pytest.raises(DiffParserError, match="Not a valid git repository"),
        ):
            DiffParser(tmp_path)


class TestParseChangedLines:
    """Tests for get_changed_lines method."""

    def test_simple_addition(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing a simple addition hunk."""
        mock_repo.git.diff.return_value = DIFF_SIMPLE_ADD

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/example.py": {5, 6, 7}}

    def test_pure_deletion(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing a pure deletion produces empty set."""
        mock_repo.git.diff.return_value = DIFF_PURE_DELETION

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/example.py": set()}

    def test_modification(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing a modification (del+add) hunk."""
        mock_repo.git.diff.return_value = DIFF_MODIFICATION

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/example.py": {3}}

    def test_multiple_hunks(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing multiple hunks in the same file."""
        mock_repo.git.diff.return_value = DIFF_MULTIPLE_HUNKS

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/example.py": {3, 11}}

    def test_multiple_files(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing changes across multiple files."""
        mock_repo.git.diff.return_value = DIFF_MULTIPLE_FILES

        result = parser.get_changed_lines("origin/main")

        assert result == {
            "src/file1.py": {5},
            "src/file2.py": {10},
        }

    def test_empty_diff(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing an empty diff returns empty dict."""
        mock_repo.git.diff.return_value = DIFF_EMPTY

        result = parser.get_changed_lines("origin/main")

        assert result == {}

    def test_binary_file_ignored(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test that binary file diffs are ignored."""
        mock_repo.git.diff.return_value = DIFF_BINARY

        result = parser.get_changed_lines("origin/main")

        assert result == {}

    def test_renamed_file(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test parsing a renamed file uses the new name."""
        mock_repo.git.diff.return_value = DIFF_RENAMED_FILE

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/new_name.py": {5}}

    def test_mixed_hunks(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test file with addition, deletion-only, and another addition hunk."""
        mock_repo.git.diff.return_value = DIFF_MIXED_HUNKS

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/example.py": {3, 10}}

    def test_uses_three_dot_diff(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test that three-dot diff syntax is used."""
        mock_repo.git.diff.return_value = ""

        parser.get_changed_lines("origin/main")

        mock_repo.git.diff.assert_called_once_with("--unified=0", "origin/main...HEAD")

    def test_custom_base_branch(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test with custom base branch."""
        mock_repo.git.diff.return_value = ""

        parser.get_changed_lines("develop")

        mock_repo.git.diff.assert_called_once_with("--unified=0", "develop...HEAD")

    def test_git_command_error(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test error handling when git diff fails."""
        mock_repo.git.diff.side_effect = GitCommandError("git diff", 1)

        with pytest.raises(DiffParserError, match="Git diff command failed"):
            parser.get_changed_lines("origin/main")

    def test_context_lines_increment_counter(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test that context lines (space-prefixed) increment the new_line counter."""
        diff_with_context = """\
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -5 +5 @@
 context line
+new line
"""
        mock_repo.git.diff.return_value = diff_with_context

        result = parser.get_changed_lines("origin/main")

        assert result == {"src/example.py": {6}}

    def test_no_hunks_in_diff(self, parser: DiffParser, mock_repo: MagicMock) -> None:
        """Test diff with file header but no @@ hunk headers."""
        diff_no_hunks = """\
diff --git a/src/example.py b/src/example.py
new file mode 100644
"""
        mock_repo.git.diff.return_value = diff_no_hunks

        result = parser.get_changed_lines("origin/main")

        assert result == {}
