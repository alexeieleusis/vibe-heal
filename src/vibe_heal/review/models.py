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


class FileDiagnostics(BaseModel):
    """Per-file diagnostic data written to review.json.

    # TODO: remove this class and all references once the line-filter pipeline
    # is considered stable — it is only here to aid debugging.


    Captures the intermediate state at each pipeline stage so that a mismatch
    (0 issues when some are expected) can be traced to the exact failure point:

    - ``changed_lines`` empty → the changed-lines map lookup missed this file
      (path mismatch between DiffParser and BranchAnalyzer keys).
    - ``sonar_issue_lines`` empty → SonarQube returned no issues for the file
      (component-path mismatch or file not scanned).
    - Issue line present in ``sonar_issue_lines`` but absent from ``changed_lines``
      → line filter too strict (trailing-context fix may not have been enough).
    """

    file_path: str = Field(description="Path passed to SonarQube component query")
    lookup_key: str = Field(description="Key used to look up this file in the diff changed-lines map")
    changed_lines: list[int] = Field(
        default_factory=list,
        description="Line numbers from git diff (sorted); empty = path lookup missed or no diff for file",
    )
    sonar_issue_count: int = Field(default=0, description="Issues from SonarQube before line filtering")
    sonar_issue_lines: list[int] = Field(
        default_factory=list,
        description="Line numbers of those issues (sorted)",
    )


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
    # TODO: remove diagnostics/diff_* fields once the line-filter pipeline is stable
    diagnostics: list[FileDiagnostics] = Field(
        default_factory=list,
        description="Per-file diagnostic data for debugging line-filter behaviour",
    )
    diff_files_found: int = Field(
        default=0,
        description="Number of files the git diff parser found with changes",
    )
    diff_map_keys: list[str] = Field(
        default_factory=list,
        description="Keys from the git diff changed-lines map (compare against diagnostics.lookup_key to spot mismatches)",
    )
    diff_output_sample: str = Field(
        default="",
        description="First 500 chars of raw git diff output (empty = diff returned nothing; helps distinguish empty diff from parse failure)",
    )

    @property
    def total_issues(self) -> int:
        """Return the total number of issues across all files."""
        return sum(len(f.issues) for f in self.files)
