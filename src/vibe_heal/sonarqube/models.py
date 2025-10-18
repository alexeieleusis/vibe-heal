"""Models for SonarQube API responses."""

from typing import Any

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class SonarQubeIssue(BaseModel):
    """Represents a SonarQube issue.

    Supports both old and new SonarQube API formats.
    """

    model_config = {"extra": "ignore"}  # Ignore extra fields from API

    key: str = Field(description="Unique issue identifier")
    rule: str = Field(description="Rule identifier (e.g., 'python:S1481')")
    message: str = Field(description="Issue description")
    component: str = Field(description="Component/file path")
    line: int | None = Field(default=None, description="Line number where issue occurs")

    # New API format fields
    issue_status: str | None = Field(
        default=None,
        alias="issueStatus",
        description="Issue status (new API)",
    )
    impacts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Impact array with severity (new API)",
    )

    # Old API format fields (for backward compatibility)
    severity: str | None = Field(
        default=None,
        description="Issue severity (old API or extracted from impacts)",
    )
    status: str | None = Field(
        default=None,
        description="Issue status (old API)",
    )
    type: str | None = Field(
        default=None,
        description="Issue type (old API)",
    )

    @model_validator(mode="after")
    def extract_fields_from_new_api(self) -> Self:
        """Extract severity and status from new API format if needed."""
        # Extract severity from impacts if not already set
        if not self.severity and self.impacts:
            # Get highest severity from impacts
            self.severity = self.impacts[0].get("severity", "INFO")

        # Use issueStatus if status not set
        if not self.status and self.issue_status:
            self.status = self.issue_status

        # Default values if still not set
        if not self.severity:
            self.severity = "INFO"
        if not self.status:
            self.status = "OPEN"

        return self

    @property
    def is_fixable(self) -> bool:
        """Check if issue is potentially fixable.

        Returns:
            True if issue is fixable
        """
        # Issues without line numbers are harder to fix
        if self.line is None:
            return False
        # Don't auto-fix resolved/accepted issues
        status_upper = (self.status or "").upper()
        return status_upper not in [
            "RESOLVED",
            "CLOSED",
            "WONTFIX",
            "FALSE-POSITIVE",
            "ACCEPTED",
        ]


class IssuesResponse(BaseModel):
    """Response from SonarQube issues API.

    Supports both old and new SonarQube API formats.
    """

    model_config = {"extra": "ignore"}  # Ignore extra fields from API

    # These can come from either top-level (old API) or paging object (new API)
    total: int | None = Field(default=None, description="Total number of issues")
    p: int | None = Field(default=None, description="Current page")
    ps: int | None = Field(default=None, description="Page size")

    issues: list[SonarQubeIssue] = Field(default_factory=list)
    paging: dict[str, Any] = Field(default_factory=dict, description="Pagination info")

    @model_validator(mode="after")
    def extract_paging_info(self) -> Self:
        """Extract pagination from paging object if not in top-level fields."""
        # Extract from paging object if top-level fields not set
        if self.total is None and "total" in self.paging:
            self.total = self.paging["total"]

        if self.p is None:
            # Try pageIndex (new API) or p (old API)
            self.p = self.paging.get("pageIndex") or self.paging.get("p", 1)

        if self.ps is None:
            # Try pageSize (new API) or ps (old API)
            self.ps = self.paging.get("pageSize") or self.paging.get("ps", 100)

        # Set defaults if still not set
        if self.total is None:
            self.total = len(self.issues)
        if self.p is None:
            self.p = 1
        if self.ps is None:
            self.ps = 100

        return self
