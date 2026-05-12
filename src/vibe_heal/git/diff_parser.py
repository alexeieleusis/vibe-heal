"""Unified diff parser for detecting changed lines."""

import re
from pathlib import Path

from git import GitCommandError, Repo
from git.exc import InvalidGitRepositoryError

from vibe_heal.git.exceptions import GitError


class DiffParserError(GitError):
    """Base exception for DiffParser errors."""

    pass


class DiffParser:
    """Parses git unified diffs to detect changed line numbers.

    Uses `git diff --unified=0 <base>...HEAD` to get a minimal diff and
    extracts the line numbers of added/modified lines in HEAD for each file.
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize the DiffParser.

        Args:
            repo_path: Path to the git repository root.

        Raises:
            DiffParserError: If repo_path is not a valid git repository.
        """
        try:
            self.repo = Repo(repo_path, search_parent_directories=True)
        except InvalidGitRepositoryError as e:
            raise DiffParserError(f"Not a valid git repository: {repo_path}") from e

    def get_changed_lines(self, base_branch: str = "origin/main") -> dict[str, set[int]]:
        """Get changed line numbers per file between base branch and HEAD.

        Parses the unified diff output and tracks which lines were added or
        modified in HEAD. Deletions-only hunks produce empty sets.

        Args:
            base_branch: Base branch to compare against. Defaults to 'origin/main'.

        Returns:
            Mapping of file paths to sets of line numbers that were added or
            modified in HEAD. Files with only deletions have empty sets.
            Files with no hunks (e.g., binary, new file mode only) are excluded.

        Raises:
            DiffParserError: If the git diff command fails.
        """
        try:
            diff_output = self.repo.git.diff("--unified=0", f"{base_branch}...HEAD")
        except GitCommandError as e:
            raise DiffParserError(f"Git diff command failed: {e}") from e

        if not diff_output.strip():
            return {}

        return self._parse_diff(diff_output)

    @staticmethod
    def _parse_diff(diff_output: str) -> dict[str, set[int]]:
        """Parse unified diff output into per-file changed line sets.

        Args:
            diff_output: Raw unified diff string.

        Returns:
            Mapping of file paths to sets of changed line numbers.
        """
        result: dict[str, set[int]] = {}
        current_file: str | None = None
        new_line: int = 0

        for line in diff_output.split("\n"):
            new_file, new_counter = _parse_diff_line(line, current_file, new_line, result)
            if new_file is not None:
                current_file = new_file
            if new_counter is not None:
                new_line = new_counter

        return result


_DIFF_HEADER_PREFIXES = (
    "index ",
    "new file ",
    "old mode ",
    "new mode ",
    "similarity ",
    "rename ",
    "copy ",
)


def _parse_diff_line(
    line: str,
    current_file: str | None,
    new_line: int,
    result: dict[str, set[int]],
) -> tuple[str | None, int | None]:
    """Process a single line of unified diff output.

    Returns:
        Tuple of (updated_current_file, updated_new_line). None means no change.
    """
    if line.startswith("diff --git "):
        parts = line.split(" ")
        new_path = parts[3]
        return (new_path[2:] if new_path.startswith("b/") else new_path, None)

    if current_file is None or line.startswith(_DIFF_HEADER_PREFIXES):
        return (None, None)

    if line.startswith("Binary files"):
        result.pop(current_file, None)
        return (None, None)

    if line.startswith(("+++", "---")):
        return (None, None)

    if line.startswith("@@"):
        match = re.match(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)", line)
        if match:
            new_line = int(match.group(1))
            result.setdefault(current_file, set())
        return (None, new_line)

    if current_file not in result:
        return (None, None)

    if line.startswith("+"):
        result[current_file].add(new_line)
        return (None, new_line + 1)
    if line.startswith(" "):
        return (None, new_line + 1)

    return (None, None)
