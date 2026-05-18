"""Tests for the Reporter module."""

from datetime import datetime, timezone
from pathlib import Path

from vibe_heal.review.models import FileReview, ReviewIssue, ReviewResult
from vibe_heal.review.reporter import default_report_dir, load_report, write_reports


def _make_result() -> ReviewResult:
    """Create a sample ReviewResult for testing."""
    return ReviewResult(
        project_key="my-project",
        branch="feature/test",
        base_branch="origin/main",
        generated_at=datetime(2025, 10, 24, 14, 30, 0, tzinfo=timezone.utc),
        files=[
            FileReview(
                file_path="src/example.py",
                issues=[
                    ReviewIssue(rule="python:S1481", message="Remove unused variable", line=10, severity="MAJOR"),
                    ReviewIssue(rule="python:S1192", message="Useless import", line=25, severity="MINOR"),
                ],
            ),
            FileReview(
                file_path="src/utils.py",
                issues=[
                    ReviewIssue(
                        rule="python:S100",
                        message="Syntax error",
                        line=5,
                        severity="CRITICAL",
                        doc_url="https://rules.example.com/S100",
                    ),
                ],
            ),
        ],
    )


def _make_empty_result() -> ReviewResult:
    """Create an empty ReviewResult for testing."""
    return ReviewResult(
        project_key="empty-project",
        branch="main",
        base_branch="origin/main",
        generated_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        files=[],
    )


class TestDefaultReportDir:
    """Tests for default_report_dir."""

    def test_returns_path_with_project_and_branch(self) -> None:
        result = default_report_dir("my-project", "feature/x")
        assert "vibe-heal" in str(result)
        assert "reviews" in str(result)
        assert "my-project" in str(result)
        assert "feature/x" in str(result)

    def test_expands_tilde_home(self) -> None:
        result = default_report_dir("proj", "main")
        assert result.is_absolute()


class TestWriteReports:
    """Tests for write_reports."""

    def test_creates_json_and_markdown_files(self, tmp_path: Path) -> None:
        result = _make_result()
        write_reports(result, tmp_path)
        assert (tmp_path / "review.json").exists()
        assert (tmp_path / "review.md").exists()

    def test_creates_directory_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "dir"
        result = _make_result()
        write_reports(result, nested)
        assert nested.is_dir()
        assert (nested / "review.json").exists()
        assert (nested / "review.md").exists()

    def test_json_round_trip(self, tmp_path: Path) -> None:
        result = _make_result()
        write_reports(result, tmp_path)
        loaded = load_report(tmp_path)
        assert loaded.project_key == result.project_key
        assert loaded.branch == result.branch
        assert loaded.base_branch == result.base_branch
        assert loaded.total_issues == result.total_issues
        assert len(loaded.files) == len(result.files)
        assert loaded.files[0].file_path == "src/example.py"
        assert loaded.files[0].issues[0].rule == "python:S1481"
        assert loaded.files[0].issues[0].line == 10

    def test_empty_result_produces_valid_files(self, tmp_path: Path) -> None:
        result = _make_empty_result()
        write_reports(result, tmp_path)
        assert (tmp_path / "review.json").exists()
        assert (tmp_path / "review.md").exists()
        loaded = load_report(tmp_path)
        assert loaded.total_issues == 0
        assert loaded.files == []

    def test_markdown_contains_summary(self, tmp_path: Path) -> None:
        result = _make_result()
        write_reports(result, tmp_path)
        md = (tmp_path / "review.md").read_text()
        assert "my-project" in md
        assert "feature/test" in md
        assert "3" in md  # total issues count

    def test_markdown_contains_file_tables(self, tmp_path: Path) -> None:
        result = _make_result()
        write_reports(result, tmp_path)
        md = (tmp_path / "review.md").read_text()
        assert "src/example.py" in md
        assert "src/utils.py" in md
        # Table header
        assert "Rule" in md
        assert "Message" in md
        assert "Line" in md
        assert "Severity" in md
        # Table formatting (markdown pipes)
        assert "|---" in md or "|--" in md

    def test_markdown_contains_issue_details(self, tmp_path: Path) -> None:
        result = _make_result()
        write_reports(result, tmp_path)
        md = (tmp_path / "review.md").read_text()
        assert "python:S1481" in md
        assert "Remove unused variable" in md
        assert "MAJOR" in md
        assert "CRITICAL" in md
        assert "https://rules.example.com/S100" in md

    def test_markdown_empty_result_has_no_tables(self, tmp_path: Path) -> None:
        result = _make_empty_result()
        write_reports(result, tmp_path)
        md = (tmp_path / "review.md").read_text()
        # Should not have table rows
        assert "python:" not in md

    def test_custom_path_override(self, tmp_path: Path) -> None:
        custom_dir = tmp_path / "custom" / "reports"
        result = _make_result()
        write_reports(result, custom_dir)
        assert (custom_dir / "review.json").exists()
        assert (custom_dir / "review.md").exists()
        loaded = load_report(custom_dir)
        assert loaded.total_issues == 3
