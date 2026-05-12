"""Tests for review command models."""

from datetime import datetime, timezone

from vibe_heal.review.models import FileReview, ReviewIssue, ReviewResult


class TestReviewIssue:
    """Tests for ReviewIssue model."""

    def test_create_issue_with_all_fields(self) -> None:
        """Test creating a review issue with all fields."""
        issue = ReviewIssue(
            rule="python:S1481",
            message="Remove this unused import",
            line=42,
            severity="MAJOR",
            doc_url="https://next.sonarqube.com/sonarqube/coding_rules?open=python%3AS1481",
            is_new_in_sonar=True,
        )

        assert issue.rule == "python:S1481"
        assert issue.message == "Remove this unused import"
        assert issue.line == 42
        assert issue.severity == "MAJOR"
        assert issue.doc_url == "https://next.sonarqube.com/sonarqube/coding_rules?open=python%3AS1481"
        assert issue.is_new_in_sonar is True

    def test_create_issue_with_defaults(self) -> None:
        """Test creating a review issue with default values."""
        issue = ReviewIssue(
            rule="python:S1192",
            message="Unused variable",
            line=10,
        )

        assert issue.rule == "python:S1192"
        assert issue.severity == "INFO"
        assert issue.doc_url is None
        assert issue.is_new_in_sonar is False

    def test_serialization_round_trip(self) -> None:
        """Test that a ReviewIssue serializes and deserializes correctly."""
        original = ReviewIssue(
            rule="typescript:S3801",
            message="Refactor this function",
            line=100,
            severity="CRITICAL",
            doc_url="https://example.com/rule",
            is_new_in_sonar=True,
        )

        data = original.model_dump()
        restored = ReviewIssue(**data)

        assert restored.rule == original.rule
        assert restored.message == original.message
        assert restored.line == original.line
        assert restored.severity == original.severity
        assert restored.doc_url == original.doc_url
        assert restored.is_new_in_sonar == original.is_new_in_sonar

    def test_json_serialization_round_trip(self) -> None:
        """Test JSON serialization and deserialization."""
        original = ReviewIssue(
            rule="python:S1067",
            message="Uppercase in underscore",
            line=5,
            severity="MINOR",
            is_new_in_sonar=False,
        )

        json_str = original.model_dump_json()
        restored = ReviewIssue.model_validate_json(json_str)

        assert restored.rule == original.rule
        assert restored.message == original.message
        assert restored.line == original.line
        assert restored.severity == original.severity
        assert restored.doc_url == original.doc_url
        assert restored.is_new_in_sonar == original.is_new_in_sonar

    def test_extra_fields_ignored(self) -> None:
        """Test that extra fields from API are ignored."""
        issue = ReviewIssue(
            rule="python:S1481",
            message="Test",
            line=1,
            extra_field="should be ignored",
            another_field=123,
        )

        assert issue.rule == "python:S1481"


class TestFileReview:
    """Tests for FileReview model."""

    def test_create_file_review_with_issues(self) -> None:
        """Test creating a file review with multiple issues."""
        issues = [
            ReviewIssue(rule="python:S1481", message="Issue 1", line=10, severity="MAJOR"),
            ReviewIssue(rule="python:S1192", message="Issue 2", line=20, severity="MINOR"),
        ]

        review = FileReview(file_path="src/main.py", issues=issues)

        assert review.file_path == "src/main.py"
        assert len(review.issues) == 2
        assert review.issues[0].rule == "python:S1481"
        assert review.issues[1].line == 20

    def test_create_file_review_empty(self) -> None:
        """Test creating a file review with no issues."""
        review = FileReview(file_path="src/clean.py", issues=[])

        assert review.file_path == "src/clean.py"
        assert review.issues == []

    def test_serialization_round_trip(self) -> None:
        """Test that a FileReview serializes and deserializes correctly."""
        original = FileReview(
            file_path="src/utils.py",
            issues=[
                ReviewIssue(
                    rule="python:S1481",
                    message="Remove unused",
                    line=5,
                    severity="MAJOR",
                    is_new_in_sonar=True,
                ),
            ],
        )

        data = original.model_dump()
        restored = FileReview(**data)

        assert restored.file_path == original.file_path
        assert len(restored.issues) == 1
        assert restored.issues[0].rule == original.issues[0].rule
        assert restored.issues[0].is_new_in_sonar == original.issues[0].is_new_in_sonar

    def test_json_serialization_round_trip(self) -> None:
        """Test JSON serialization and deserialization."""
        original = FileReview(
            file_path="src/app.ts",
            issues=[
                ReviewIssue(rule="typescript:S3801", message="Refactor", line=50),
                ReviewIssue(rule="typescript:S100", message="Too long", line=80),
            ],
        )

        json_str = original.model_dump_json()
        restored = FileReview.model_validate_json(json_str)

        assert restored.file_path == original.file_path
        assert len(restored.issues) == 2
        assert restored.issues[0].rule == "typescript:S3801"
        assert restored.issues[1].line == 80


class TestReviewResult:
    """Tests for ReviewResult model."""

    def test_create_review_result(self) -> None:
        """Test creating a review result with all fields."""
        files = [
            FileReview(
                file_path="src/a.py",
                issues=[ReviewIssue(rule="python:S1481", message="Issue", line=1)],
            ),
            FileReview(
                file_path="src/b.py",
                issues=[
                    ReviewIssue(rule="python:S1192", message="Issue A", line=10),
                    ReviewIssue(rule="python:S1067", message="Issue B", line=20),
                ],
            ),
        ]

        result = ReviewResult(
            project_key="my-project",
            branch="feature/test",
            base_branch="origin/main",
            generated_at=datetime(2025, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
            files=files,
        )

        assert result.project_key == "my-project"
        assert result.branch == "feature/test"
        assert result.base_branch == "origin/main"
        assert len(result.files) == 2
        assert result.total_issues == 3

    def test_total_issues_empty(self) -> None:
        """Test total_issues returns 0 when no files."""
        result = ReviewResult(
            project_key="my-project",
            branch="main",
            base_branch="origin/main",
            files=[],
        )

        assert result.total_issues == 0

    def test_total_issues_files_with_no_issues(self) -> None:
        """Test total_issues returns 0 when files exist but have no issues."""
        result = ReviewResult(
            project_key="my-project",
            branch="main",
            base_branch="origin/main",
            files=[
                FileReview(file_path="src/clean.py", issues=[]),
                FileReview(file_path="src/also_clean.py", issues=[]),
            ],
        )

        assert result.total_issues == 0

    def test_generated_at_defaults_to_now(self) -> None:
        """Test that generated_at defaults to current UTC time."""
        before = datetime.now(timezone.utc)
        result = ReviewResult(
            project_key="my-project",
            branch="main",
            base_branch="origin/main",
        )
        after = datetime.now(timezone.utc)

        assert before <= result.generated_at <= after
        assert result.generated_at.tzinfo is not None

    def test_serialization_round_trip(self) -> None:
        """Test that a ReviewResult serializes and deserializes correctly."""
        generated_at = datetime(2025, 6, 15, 9, 30, 0, tzinfo=timezone.utc)
        original = ReviewResult(
            project_key="test-project",
            branch="dev",
            base_branch="origin/main",
            generated_at=generated_at,
            files=[
                FileReview(
                    file_path="src/x.py",
                    issues=[
                        ReviewIssue(
                            rule="python:S1481",
                            message="Unused",
                            line=3,
                            severity="MAJOR",
                            is_new_in_sonar=True,
                            doc_url="https://example.com",
                        ),
                    ],
                ),
            ],
        )

        data = original.model_dump()
        restored = ReviewResult(**data)

        assert restored.project_key == original.project_key
        assert restored.branch == original.branch
        assert restored.base_branch == original.base_branch
        assert restored.generated_at == original.generated_at
        assert restored.total_issues == original.total_issues
        assert len(restored.files) == 1
        assert restored.files[0].issues[0].is_new_in_sonar is True

    def test_json_serialization_round_trip(self) -> None:
        """Test JSON serialization and deserialization."""
        generated_at = datetime(2025, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
        original = ReviewResult(
            project_key="proj",
            branch="feat",
            base_branch="origin/main",
            generated_at=generated_at,
            files=[
                FileReview(
                    file_path="src/y.ts",
                    issues=[ReviewIssue(rule="ts:S1", message="M", line=1)],
                ),
            ],
        )

        json_str = original.model_dump_json()
        restored = ReviewResult.model_validate_json(json_str)

        assert restored.project_key == original.project_key
        assert restored.branch == original.branch
        assert restored.generated_at == original.generated_at
        assert restored.total_issues == 1
