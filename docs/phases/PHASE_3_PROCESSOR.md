# Phase 3: Issue Processing ✅ COMPLETE

## Objective

Implement logic to sort and filter SonarQube issues to determine the order and set of issues to fix.

## Status: ✅ COMPLETE

All issue processing features implemented and tested:
- [x] `IssueProcessor` class with filtering and sorting
- [x] `ProcessingResult` model
- [x] Reverse line order sorting (high to low) to avoid line number shifts
- [x] Filtering by fixability (using `is_fixable`)
- [x] Filtering by severity with configurable minimum
- [x] Limiting number of issues to process
- [x] Comprehensive test coverage (18 tests, 90% coverage)

**Test Results**: 18 tests for processor module, 90% coverage
**Overall Progress**: 75 tests passing, 91% code coverage

## Dependencies

- Phase 0, 1, and 2 must be complete
- `SonarQubeIssue` model available

## Files to Create/Modify

```
src/vibe_heal/
├── processor/
│   ├── __init__.py              # Export public API
│   ├── issue_processor.py       # Main processing logic
│   └── models.py                # Processing-related models
tests/
└── processor/
    └── test_issue_processor.py  # Processor tests
```

## Tasks

### 1. Create Processing Models

**File**: `src/vibe_heal/processor/models.py`

```python
from pydantic import BaseModel
from vibe_heal.sonarqube.models import SonarQubeIssue


class ProcessingResult(BaseModel):
    """Result of processing issues."""

    total_issues: int
    fixable_issues: int
    skipped_issues: int
    issues_to_fix: list[SonarQubeIssue]

    @property
    def has_issues(self) -> bool:
        """Check if there are any issues to fix."""
        return len(self.issues_to_fix) > 0
```

### 2. Create Issue Processor

**File**: `src/vibe_heal/processor/issue_processor.py`

```python
from vibe_heal.sonarqube.models import SonarQubeIssue
from vibe_heal.processor.models import ProcessingResult


class IssueProcessor:
    """Processes SonarQube issues to determine fix order."""

    def __init__(
        self,
        min_severity: str | None = None,
        max_issues: int | None = None,
    ):
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
            fixable = [
                issue for issue in fixable
                if self._severity_rank.get(issue.severity, 0) >= min_rank
            ]

        # Step 3: Sort issues in reverse line order (high to low)
        # This ensures fixes don't affect line numbers of subsequent issues
        sorted_issues = self._sort_by_line_descending(fixable)

        # Step 4: Limit number of issues if specified
        if self.max_issues and self.max_issues > 0:
            sorted_issues = sorted_issues[:self.max_issues]

        return ProcessingResult(
            total_issues=total,
            fixable_issues=len(fixable),
            skipped_issues=total - len(sorted_issues),
            issues_to_fix=sorted_issues,
        )

    def _sort_by_line_descending(
        self,
        issues: list[SonarQubeIssue]
    ) -> list[SonarQubeIssue]:
        """Sort issues by line number in descending order.

        Issues without line numbers are placed at the end.

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
```

### 3. Export Public API

**File**: `src/vibe_heal/processor/__init__.py`

```python
from vibe_heal.processor.issue_processor import IssueProcessor
from vibe_heal.processor.models import ProcessingResult

__all__ = [
    "IssueProcessor",
    "ProcessingResult",
]
```

### 4. Write Comprehensive Tests

**File**: `tests/processor/test_issue_processor.py`

Test cases:

**Sorting tests**:
- ✅ Sort issues by line number (descending)
- ✅ Handle issues without line numbers (put at end)
- ✅ Handle empty list
- ✅ Handle single issue
- ✅ Handle all issues on same line

**Filtering tests**:
- ✅ Filter non-fixable issues (no line number)
- ✅ Filter resolved/closed issues
- ✅ Filter by minimum severity (BLOCKER only)
- ✅ Filter by minimum severity (MAJOR and above)
- ✅ All severities when no min specified

**Limiting tests**:
- ✅ Limit to N issues
- ✅ Limit greater than available issues
- ✅ No limit specified (process all)

**Integration tests**:
- ✅ Complex scenario: multiple filters + sorting + limiting
- ✅ ProcessingResult properties
- ✅ has_issues property

**Example test structure**:
```python
import pytest
from vibe_heal.sonarqube.models import SonarQubeIssue
from vibe_heal.processor import IssueProcessor


def test_sort_by_line_descending():
    issues = [
        SonarQubeIssue(
            key="1",
            rule="rule:1",
            severity="MAJOR",
            message="Issue 1",
            component="file.py",
            line=10,
            status="OPEN",
            type="CODE_SMELL",
        ),
        SonarQubeIssue(
            key="2",
            rule="rule:2",
            severity="MAJOR",
            message="Issue 2",
            component="file.py",
            line=50,
            status="OPEN",
            type="CODE_SMELL",
        ),
        SonarQubeIssue(
            key="3",
            rule="rule:3",
            severity="MAJOR",
            message="Issue 3",
            component="file.py",
            line=30,
            status="OPEN",
            type="CODE_SMELL",
        ),
    ]

    processor = IssueProcessor()
    result = processor.process(issues)

    # Should be sorted: 50, 30, 10
    assert result.issues_to_fix[0].line == 50
    assert result.issues_to_fix[1].line == 30
    assert result.issues_to_fix[2].line == 10
```

## Example Usage

```python
from vibe_heal.sonarqube import SonarQubeClient
from vibe_heal.processor import IssueProcessor
from vibe_heal.config import VibeHealConfig

config = VibeHealConfig()

async with SonarQubeClient(config) as client:
    # Fetch issues
    issues = await client.get_issues_for_file("src/main.py")

    # Process: filter, sort, limit
    processor = IssueProcessor(
        min_severity="MAJOR",
        max_issues=10
    )
    result = processor.process(issues)

    print(f"Total issues: {result.total_issues}")
    print(f"Fixable issues: {result.fixable_issues}")
    print(f"Processing {len(result.issues_to_fix)} issues")

    for issue in result.issues_to_fix:
        print(f"Line {issue.line}: {issue.severity} - {issue.message}")
```

## Verification Steps

1. Run tests:
   ```bash
   uv run pytest tests/processor/ -v --cov=src/vibe_heal/processor
   ```

2. Type checking:
   ```bash
   uv run mypy src/vibe_heal/processor/
   ```

3. Integration test:
   ```python
   from vibe_heal.processor import IssueProcessor
   from vibe_heal.sonarqube.models import SonarQubeIssue

   # Create test issues
   issues = [
       SonarQubeIssue(
           key=f"issue-{i}",
           rule="test:rule",
           severity="MAJOR",
           message=f"Issue {i}",
           component="test.py",
           line=i * 10,
           status="OPEN",
           type="CODE_SMELL",
       )
       for i in range(1, 11)
   ]

   processor = IssueProcessor(max_issues=5)
   result = processor.process(issues)

   assert len(result.issues_to_fix) == 5
   assert result.issues_to_fix[0].line == 100  # Highest line first
   ```

## Definition of Done

- ✅ `IssueProcessor` class implemented
- ✅ Sorting by line number (descending)
- ✅ Filtering by fixability (using `is_fixable`)
- ✅ Filtering by severity
- ✅ Limiting number of issues
- ✅ `ProcessingResult` model
- ✅ Comprehensive tests (>90% coverage)
- ✅ Type checking passes
- ✅ All edge cases handled (empty lists, None values, etc.)

## Notes

- Reverse line order is critical - fixes at the end of the file don't affect earlier line numbers
- The processor is stateless - just pure functions
- Keep it simple - don't over-engineer
- Later phases may add more sophisticated filtering (by rule type, file patterns, etc.)
