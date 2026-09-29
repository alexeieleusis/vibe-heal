"""Tests for cleanup_pr.scope.select_in_scope_issues (FR-4 issue selection)."""

from unittest.mock import patch

from vibe_heal.cleanup_pr.scope import select_in_scope_issues
from vibe_heal.review.models import ReviewIssue
from vibe_heal.sonarqube.models import SonarQubeIssue


def _make_issue(
    key: str,
    line: int | None = 10,
    rule: str = "python:S1481",
    status: str | None = None,
) -> SonarQubeIssue:
    """Build a SonarQubeIssue with sensible defaults."""
    return SonarQubeIssue(
        key=key,
        rule=rule,
        message=f"Issue {key}",
        component="src/main.py",
        line=line,
        status=status,
    )


# Strict changed lines {10, 14} with a 3-line trailing window produce the
# new-line set {10, 11, 12, 13, 14, 15, 16, 17}.
STRICT_LINES = {10, 14}
WINDOW_LINES = {10, 11, 12, 13, 14, 15, 16, 17}


class TestSelectInScopeIssues:
    """Tests for select_in_scope_issues()."""

    def test_keeps_issue_on_changed_line(self) -> None:
        """A fixable issue on a strict changed line is kept."""
        issues = [_make_issue("a", line=10)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == issues
        assert result.out_of_scope_count == 0

    def test_keeps_issue_in_trailing_window(self) -> None:
        """A window-only issue (not on a strict line) is still in scope."""
        issues = [_make_issue("a", line=17)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == issues
        assert result.out_of_scope_count == 0

    def test_drops_issue_outside_scope(self) -> None:
        """An issue outside the trailing window is dropped and counted out of scope."""
        issues = [_make_issue("a", line=5), _make_issue("b", line=10)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == [issues[1]]
        assert result.out_of_scope_count == 1

    def test_keeps_issue_on_first_strict_line(self) -> None:
        """An issue on the first strict changed line is kept."""
        issues = [_make_issue("a", line=10)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == issues

    def test_keeps_issue_on_last_strict_line(self) -> None:
        """An issue on the last strict changed line is kept."""
        issues = [_make_issue("a", line=14)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == issues

    def test_keeps_issue_on_last_window_line(self) -> None:
        """An issue on the last trailing-window line is kept."""
        issues = [_make_issue("a", line=17)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == issues

    def test_drops_issue_on_first_line_beyond_window(self) -> None:
        """An issue on the first line beyond the trailing window is dropped."""
        issues = [_make_issue("a", line=18)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == []
        assert result.out_of_scope_count == 1

    def test_drops_issue_without_line(self) -> None:
        """An issue with line=None is dropped and not counted (not fixable)."""
        issues = [_make_issue("a", line=None)]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == []
        assert result.out_of_scope_count == 0

    def test_drops_non_fixable_issue_on_in_scope_line(self) -> None:
        """A resolved issue on an in-scope line is dropped and not counted out of scope."""
        issues = [_make_issue("a", line=10, status="RESOLVED")]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == []
        assert result.out_of_scope_count == 0

    def test_drops_non_fixable_issue_outside_scope(self) -> None:
        """A resolved issue outside the window is dropped and not counted out of scope."""
        issues = [_make_issue("a", line=5, status="RESOLVED")]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == []
        assert result.out_of_scope_count == 0

    def test_out_of_scope_counts_fixable_but_dropped(self) -> None:
        """Out of scope = fixable issues minus kept issues (non-fixable excluded)."""
        issues = [
            _make_issue("a", line=10),  # fixable, in scope -> kept
            _make_issue("b", line=5),  # fixable, out of scope -> counted
            _make_issue("c", line=14, status="RESOLVED"),  # not fixable -> not counted
            _make_issue("d", line=None),  # not fixable -> not counted
        ]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == [issues[0]]
        assert result.out_of_scope_count == 1

    def test_same_rule_same_line_selects_all(self) -> None:
        """A surviving (rule, line) pair matching several records keeps all of them."""
        issues = [
            _make_issue("a", line=10, rule="python:S1481"),
            _make_issue("b", line=10, rule="python:S1481"),
            _make_issue("c", line=10, rule="python:S1481"),
        ]

        result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == issues
        assert result.out_of_scope_count == 0

    def test_empty_issues(self) -> None:
        """An empty issue list yields an empty result."""
        result = select_in_scope_issues([], WINDOW_LINES, STRICT_LINES)

        assert result.in_scope == []
        assert result.out_of_scope_count == 0

    def test_passes_resolved_line_sets_to_filter_unchanged(self) -> None:
        """The resolved line sets are handed to IssueLineFilter without modification."""
        issues = [_make_issue("a", line=10), _make_issue("b", line=18)]
        surviving = [ReviewIssue(rule="python:S1481", message="Issue a", line=10)]

        with patch("vibe_heal.cleanup_pr.scope.IssueLineFilter") as mock_filter:
            mock_filter.filter_issues.return_value = surviving
            result = select_in_scope_issues(issues, WINDOW_LINES, STRICT_LINES)

        mock_filter.filter_issues.assert_called_once_with(
            issues,
            WINDOW_LINES,
            strict_changed_lines=STRICT_LINES,
        )
        assert result.in_scope == [issues[0]]
        assert result.out_of_scope_count == 1
