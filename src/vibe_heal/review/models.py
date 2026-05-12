"""Models for the review command."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ReviewIssue(BaseModel):
    """Represents a single SonarQube issue found on a changed line."""

    model_config = {"extra": "ignore"}

    rule: str = Field(description="Rule identifier (e.g., 'python:S1481')")
    message: str = Field(description="Issue description")
    line: int = Field(description="Line number where the issue occurs")
    severity: str = Field(default="INFO", description="Issue severity (MAJOR, MINOR, CRITICAL, INFO)")
    doc_url: str | None = Field(default=None, description="Link to rule documentation")
    is_new_in_sonar: bool = Field(
        default=False,
        description="Whether this issue is new code per SonarQube",
    )


class FileReview(BaseModel):
    """Review results for a single file."""

    model_config = {"extra": "ignore"}

    file_path: str = Field(description="Path to the file relative to project root")
    issues: list[ReviewIssue] = Field(default_factory=list, description="Issues found in this file")


class ReviewResult(BaseModel):
    """Complete review result for a branch."""

    model_config = {"extra": "ignore"}

    project_key: str = Field(description="SonarQube project key")
    branch: str = Field(description="Current branch name")
    base_branch: str = Field(description="Base branch for comparison (e.g., 'origin/main')")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the review was generated",
    )
    files: list[FileReview] = Field(default_factory=list, description="Per-file review results")

    @property
    def total_issues(self) -> int:
        """Return the total number of issues across all files."""
        return sum(len(f.issues) for f in self.files)
