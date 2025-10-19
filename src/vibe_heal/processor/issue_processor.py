"""Issue processor for sorting and filtering SonarQube issues."""

from vibe_heal.processor.models import ProcessingResult
from vibe_heal.sonarqube.models import SonarQubeIssue


class IssueProcessor:
    """Processes SonarQube issues to determine fix order.

    Filters issues by fixability and severity, sorts them in reverse line order
    (highest line number first) to avoid line number shifts, and optionally limits
    the number of issues to process.
    """

    def __init__(
        self,
        min_severity: str | None = None,
        max_issues: int | None = None,
    ) -> None:
        """Initialize the issue processor.

        Args:
            min_severity: Minimum severity to process (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)
            max_issues: Maximum number of issues to process
        """
        self.min_severity = min_severity
        self.max_issues = max_issues

        # Severity ranking (higher is more severe)
        self._severity_rank = {
            "BLOCKER": 5,
            "CRITICAL": 4,
            "MAJOR": 3,
            "MINOR": 2,
            "INFO": 1,
        }

    def process(self, issues: list[SonarQubeIssue]) -> ProcessingResult:
        """Process issues: filter and sort.

        Processing steps:
        1. Filter fixable issues (those with line numbers and not resolved)
        2. Filter by severity if min_severity is specified
        3. Sort issues in reverse line order (high to low)
        4. Limit number of issues if max_issues is specified

        Args:
            issues: List of SonarQube issues

        Returns:
            ProcessingResult with processed issues
        """
        total = len(issues)

        # Step 1: Filter fixable issues
        fixable = [issue for issue in issues if issue.is_fixable]

        # Step 2: Filter by severity if specified
        if self.min_severity:
            min_rank = self._severity_rank.get(self.min_severity.upper(), 0)
            fixable = [issue for issue in fixable if self._severity_rank.get(issue.severity or "INFO", 0) >= min_rank]

        # Step 3: Sort issues in reverse line order (high to low)
        # This ensures fixes don't affect line numbers of subsequent issues
        sorted_issues = self._sort_by_line_descending(fixable)

        # Step 4: Limit number of issues if specified
        if self.max_issues and self.max_issues > 0:
            sorted_issues = sorted_issues[: self.max_issues]

        return ProcessingResult(
            total_issues=total,
            fixable_issues=len(fixable),
            skipped_issues=total - len(sorted_issues),
            issues_to_fix=sorted_issues,
        )

    def _sort_by_line_descending(
        self,
        issues: list[SonarQubeIssue],
    ) -> list[SonarQubeIssue]:
        """Sort issues by line number in descending order.

        Issues without line numbers are placed at the end (though they should
        have been filtered out by is_fixable).

        Args:
            issues: List of issues to sort

        Returns:
            Sorted list of issues
        """
        # Separate issues with and without line numbers
        with_line = [issue for issue in issues if issue.line is not None]
        without_line = [issue for issue in issues if issue.line is None]

        # Sort issues with line numbers in descending order
        with_line.sort(key=lambda x: x.line or 0, reverse=True)

        # Return issues with line numbers first, then those without
        return with_line + without_line
