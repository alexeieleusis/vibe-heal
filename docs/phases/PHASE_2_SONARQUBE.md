# Phase 2: SonarQube API Integration ✅ COMPLETE

## Objective

Implement a client to interact with the SonarQube Web API to fetch issues for a specific file.

## Status: ✅ COMPLETE

All SonarQube integration features implemented and tested:
- [x] `SonarQubeIssue` model supporting both old and new SonarQube API formats
- [x] `IssuesResponse` model with flexible pagination parsing
- [x] `SonarQubeClient` with async/await support
- [x] Token and basic authentication
- [x] Pagination handling (automatic for large result sets)
- [x] File path filtering
- [x] Error handling for auth failures and API errors
- [x] Comprehensive test coverage (92%)
- [x] All tests passing (29 tests)
- [x] **Bonus**: Validated against real SonarQube API response

**Test Results**: 29 tests, 92% coverage on sonarqube module

**Notable Implementation Details**:
- Models support both old SonarQube API (with `severity`, `status`, `type` fields) and new API (with `issueStatus` and `impacts` array)
- Flexible paging extraction from both top-level fields and `paging` object
- `model_config = {"extra": "ignore"}` to handle additional API fields gracefully
- Added "ACCEPTED" to non-fixable issue statuses

## Dependencies

- Phase 0 and Phase 1 must be complete ✅
- `httpx` installed ✅
- `VibeHealConfig` available ✅

## Files to Create/Modify

```
src/vibe_heal/
├── sonarqube/
│   ├── __init__.py              # Export public API
│   ├── models.py                # Pydantic models for API responses
│   ├── client.py                # SonarQube HTTP client
│   └── exceptions.py            # SonarQube-specific exceptions
tests/
└── sonarqube/
    ├── test_models.py           # Model tests
    ├── test_client.py           # Client tests (mocked)
    └── fixtures/
        └── api_responses.json   # Sample API responses
```

## Tasks

### 1. Create SonarQube Exceptions

**File**: `src/vibe_heal/sonarqube/exceptions.py`

```python
class SonarQubeError(Exception):
    """Base exception for SonarQube errors."""
    pass


class SonarQubeAuthError(SonarQubeError):
    """Authentication failed."""
    pass


class SonarQubeAPIError(SonarQubeError):
    """API request failed."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
```

### 2. Create Response Models

**File**: `src/vibe_heal/sonarqube/models.py`

```python
from pydantic import BaseModel, Field


class SonarQubeIssue(BaseModel):
    """Represents a SonarQube issue."""

    key: str = Field(description="Unique issue identifier")
    rule: str = Field(description="Rule identifier (e.g., 'python:S1481')")
    severity: str = Field(description="Issue severity (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)")
    message: str = Field(description="Issue description")
    component: str = Field(description="Component/file path")
    line: int | None = Field(default=None, description="Line number where issue occurs")
    status: str = Field(description="Issue status (OPEN, CONFIRMED, REOPENED, etc.)")
    type: str = Field(description="Issue type (BUG, VULNERABILITY, CODE_SMELL)")

    @property
    def is_fixable(self) -> bool:
        """Check if issue is potentially fixable."""
        # Issues without line numbers are harder to fix
        if self.line is None:
            return False
        # Don't auto-fix resolved issues
        if self.status in ["RESOLVED", "CLOSED", "WONTFIX", "FALSE-POSITIVE"]:
            return False
        return True


class IssuesResponse(BaseModel):
    """Response from SonarQube issues API."""

    total: int = Field(description="Total number of issues")
    p: int = Field(description="Current page")
    ps: int = Field(description="Page size")
    issues: list[SonarQubeIssue] = Field(default_factory=list)
    paging: dict = Field(default_factory=dict, description="Pagination info")
```

### 3. Create SonarQube Client

**File**: `src/vibe_heal/sonarqube/client.py`

```python
import httpx
from typing import Any

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.models import SonarQubeIssue, IssuesResponse
from vibe_heal.sonarqube.exceptions import (
    SonarQubeAPIError,
    SonarQubeAuthError,
)


class SonarQubeClient:
    """Client for interacting with SonarQube Web API."""

    def __init__(self, config: VibeHealConfig):
        """Initialize the SonarQube client.

        Args:
            config: Application configuration
        """
        self.config = config
        self.base_url = config.sonarqube_url
        self._client: httpx.AsyncClient | None = None

    def _get_auth(self) -> httpx.Auth | tuple[str, str] | None:
        """Get authentication for requests."""
        if self.config.use_token_auth:
            # Token auth uses token as username with empty password
            return httpx.BasicAuth(self.config.sonarqube_token or "", "")
        elif self.config.sonarqube_username and self.config.sonarqube_password:
            return httpx.BasicAuth(
                self.config.sonarqube_username,
                self.config.sonarqube_password
            )
        return None

    async def __aenter__(self) -> "SonarQubeClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=self._get_auth(),
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> dict:
        """Make an HTTP request to SonarQube API.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for httpx

        Returns:
            JSON response as dict

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            response = await self._client.request(method, endpoint, **kwargs)

            if response.status_code == 401:
                raise SonarQubeAuthError("Authentication failed. Check your credentials.")

            if response.status_code >= 400:
                raise SonarQubeAPIError(
                    f"API request failed: {response.text}",
                    status_code=response.status_code
                )

            return response.json()

        except httpx.HTTPError as e:
            raise SonarQubeAPIError(f"HTTP error: {e}") from e

    async def get_issues_for_file(
        self,
        file_path: str,
        resolved: bool = False
    ) -> list[SonarQubeIssue]:
        """Get all issues for a specific file.

        Args:
            file_path: Path to the file (relative to project root)
            resolved: Include resolved issues (default: False)

        Returns:
            List of SonarQube issues for the file

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        issues: list[SonarQubeIssue] = []
        page = 1
        page_size = 100

        while True:
            params = {
                "componentKeys": self.config.sonarqube_project_key,
                "resolved": str(resolved).lower(),
                "p": page,
                "ps": page_size,
            }

            data = await self._request("GET", "/api/issues/search", params=params)
            response = IssuesResponse(**data)

            # Filter issues for the specific file
            for issue in response.issues:
                # Component format is usually: project_key:path/to/file
                component_path = issue.component.split(":", 1)[-1]
                if component_path == file_path or component_path.endswith(f"/{file_path}"):
                    issues.append(issue)

            # Check if there are more pages
            total_pages = (response.total + page_size - 1) // page_size
            if page >= total_pages:
                break

            page += 1

        return issues
```

### 4. Export Public API

**File**: `src/vibe_heal/sonarqube/__init__.py`

```python
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import (
    SonarQubeAPIError,
    SonarQubeAuthError,
    SonarQubeError,
)
from vibe_heal.sonarqube.models import IssuesResponse, SonarQubeIssue

__all__ = [
    "SonarQubeClient",
    "SonarQubeIssue",
    "IssuesResponse",
    "SonarQubeError",
    "SonarQubeAPIError",
    "SonarQubeAuthError",
]
```

### 5. Create Test Fixtures

**File**: `tests/sonarqube/fixtures/api_responses.json`

Sample SonarQube API responses for testing.

### 6. Write Tests

**File**: `tests/sonarqube/test_models.py`
- Test `SonarQubeIssue` model parsing
- Test `is_fixable` property
- Test `IssuesResponse` model parsing

**File**: `tests/sonarqube/test_client.py`
- Test authentication setup (token vs basic)
- Test successful API call (mocked with `responses` library)
- Test authentication failure (401)
- Test API error (500)
- Test pagination
- Test file filtering
- Test resolved issues parameter

## Example Usage

```python
from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube import SonarQubeClient

config = VibeHealConfig()

async with SonarQubeClient(config) as client:
    issues = await client.get_issues_for_file("src/main.py")
    print(f"Found {len(issues)} issues")
    for issue in issues:
        if issue.is_fixable:
            print(f"Line {issue.line}: {issue.message}")
```

## Verification Steps

1. Run tests:
   ```bash
   uv run pytest tests/sonarqube/ -v
   ```

2. Manual test with real SonarQube (optional):
   ```python
   import asyncio
   from vibe_heal.config import VibeHealConfig
   from vibe_heal.sonarqube import SonarQubeClient

   async def test():
       config = VibeHealConfig()
       async with SonarQubeClient(config) as client:
           issues = await client.get_issues_for_file("your_file.py")
           print(issues)

   asyncio.run(test())
   ```

3. Type checking:
   ```bash
   uv run mypy src/vibe_heal/sonarqube/
   ```

## Definition of Done

- ✅ `SonarQubeIssue` and `IssuesResponse` models implemented
- ✅ `SonarQubeClient` with async support
- ✅ Token and basic authentication support
- ✅ Pagination handling
- ✅ File path filtering
- ✅ Error handling (auth errors, API errors)
- ✅ Comprehensive tests with mocked API responses
- ✅ Test coverage >85%
- ✅ Type checking passes
- ✅ Can fetch issues from SonarQube API

## Notes

- Use `httpx` async client for better performance
- Implement proper pagination to handle projects with many issues
- Filter issues client-side by file path (SonarQube API doesn't have direct file filtering)
- Consider rate limiting in future if needed
- The `is_fixable` property on issues will be used by the processor
