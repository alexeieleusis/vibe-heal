"""SonarQube API client."""

import logging
from typing import Any

import httpx

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.exceptions import (
    ComponentNotFoundError,
    SonarQubeAPIError,
    SonarQubeAuthError,
)
from vibe_heal.sonarqube.models import (
    IssuesResponse,
    RuleResponse,
    SonarQubeIssue,
    SonarQubeRule,
    SourceLine,
    SourceLinesResponse,
)

logger = logging.getLogger(__name__)


class SonarQubeClient:
    """Client for interacting with SonarQube Web API."""

    def __init__(self, config: VibeHealConfig) -> None:
        """Initialize the SonarQube client.

        Args:
            config: Application configuration
        """
        self.config = config
        self.base_url = config.sonarqube_url
        self._client: httpx.AsyncClient | None = None

    def _get_auth(self) -> httpx.Auth:
        """Get authentication for requests.

        Returns:
            HTTP authentication object
        """
        if self.config.use_token_auth:
            # Token auth uses token as username with empty password
            return httpx.BasicAuth(self.config.sonarqube_token or "", "")
        # Basic auth with username and password
        return httpx.BasicAuth(
            self.config.sonarqube_username or "",
            self.config.sonarqube_password or "",
        )

    async def __aenter__(self) -> "SonarQubeClient":
        """Async context manager entry.

        Returns:
            Self
        """
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=self._get_auth(),
            timeout=30.0,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit.

        Args:
            exc_type: Exception type
            exc_val: Exception value
            exc_tb: Exception traceback
        """
        if self._client:
            await self._client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict:
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

            if response.status_code == 404:
                # Check if this is a component not found error
                try:
                    error_data = response.json()
                    errors = error_data.get("errors", [])
                    if errors and any("not found" in str(err.get("msg", "")).lower() for err in errors):
                        raise ComponentNotFoundError(f"Component not found: {response.text}")
                except (ValueError, KeyError):
                    pass  # Not a JSON response or missing expected fields

            if response.status_code >= 400:
                raise SonarQubeAPIError(
                    f"API request failed: {response.text}",
                    status_code=response.status_code,
                )

            # Handle 204 No Content responses (e.g., delete operations)
            if response.status_code == 204 or not response.content:
                return {}

            result: dict[Any, Any] = response.json()
            return result

        except httpx.HTTPError as e:
            raise SonarQubeAPIError(f"HTTP error: {e}") from e

    def _log_first_page_raw_response(self, data: dict) -> None:
        """Log raw API response details for the first page.

        Args:
            data: Raw API response data
        """
        raw_issues = data.get("issues", [])
        if raw_issues:
            logger.debug(f"First issue raw data: {raw_issues[0]}")
        else:
            logger.debug(f"API returned 0 issues. Full response keys: {list(data.keys())}")
            logger.debug(f"Full paging info: {data.get('paging', {})}")

    def _log_first_page_parsed_issues(self, response: IssuesResponse) -> None:
        """Log parsed issue details for the first page.

        Args:
            response: Parsed issues response
        """
        for idx, issue in enumerate(response.issues[:3], 1):
            logger.debug(
                f"Issue {idx}: key={issue.key}, rule={issue.rule}, line={issue.line}, "
                f"status={issue.status!r}, issue_status={issue.issue_status!r}, "
                f"severity={issue.severity!r}, message={issue.message[:50]}{'...' if issue.message and len(issue.message) > 50 else ''}"
            )

    async def get_issues(
        self,
        component: str | None = None,
        resolved: bool = False,
        page_size: int = 100,
    ) -> list[SonarQubeIssue]:
        """Get issues with optional filtering.

        Args:
            component: Optional component identifier (e.g., "projectKey:file/path.py").
                      If None, fetches all project issues.
            resolved: Include resolved issues (default: False)
            page_size: Number of issues per page (default: 100)

        Returns:
            List of SonarQube issues

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        issues: list[SonarQubeIssue] = []
        page = 1

        while True:
            params: dict[str, Any] = {
                "p": page,
                "ps": page_size,
            }

            # Add component filter if specified
            if component:
                params["components"] = component
            else:
                # No file filter - get all project issues
                params["componentKeys"] = self.config.sonarqube_project_key

            # Add status filter
            if not resolved:
                params["issueStatuses"] = "OPEN,CONFIRMED"

            logger.debug(f"Fetching issues with params={params}")
            data = await self._request("GET", "/api/issues/search", params=params)

            # Log raw API response before parsing
            logger.debug(f"Raw API response: total={data.get('total')}, issues count={len(data.get('issues', []))}")
            if page == 1:
                self._log_first_page_raw_response(data)

            response = IssuesResponse(**data)

            logger.debug(f"Received {len(response.issues)} issues from page {page} (total={response.total})")

            # Log raw issue data for the first few issues on the first page
            if page == 1 and response.issues:
                self._log_first_page_parsed_issues(response)

            issues.extend(response.issues)

            # Check if there are more pages
            if response.total is None:
                raise SonarQubeAPIError("API response missing total count")
            total_pages = (response.total + page_size - 1) // page_size
            if page >= total_pages:
                break

            page += 1

        logger.debug(f"Total issues fetched: {len(issues)}")
        return issues

    async def get_issues_for_file(self, file_path: str, resolved: bool = False) -> list[SonarQubeIssue]:
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
        # Build component identifier: projectKey:filePath
        # Use the project key as-is (case-sensitive)
        component = f"{self.config.sonarqube_project_key}:{file_path}"
        return await self.get_issues(component=component, resolved=resolved)

    async def get_rule_details(self, rule_key: str) -> SonarQubeRule:
        """Get detailed information about a specific rule.

        Args:
            rule_key: Rule identifier (e.g., 'typescript:S3801')

        Returns:
            Detailed rule information

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        params = {
            "key": rule_key,
            "actives": "true",  # Include active profiles information
        }

        data = await self._request("GET", "/api/rules/show", params=params)
        response = RuleResponse(**data)

        return response.rule

    async def get_source_lines(
        self,
        file_path: str,
        from_line: int | None = None,
        to_line: int | None = None,
    ) -> list[SourceLine]:
        """Get source code lines for a specific file.

        Args:
            file_path: Path to the file (relative to project root)
            from_line: Start line number (1-based, inclusive). If None, starts from line 1
            to_line: End line number (1-based, inclusive). If None, gets all lines

        Returns:
            List of source code lines

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        # Build component identifier: projectKey:filePath
        component = f"{self.config.sonarqube_project_key}:{file_path}"

        params: dict[str, Any] = {
            "key": component,
        }

        if from_line is not None:
            params["from"] = from_line
        if to_line is not None:
            params["to"] = to_line

        data = await self._request("GET", "/api/sources/lines", params=params)
        response = SourceLinesResponse(**data)

        return response.sources

    async def create_project(self, key: str, name: str) -> None:
        """Create a new SonarQube project.

        Args:
            key: Project key (unique identifier)
            name: Project name (display name)

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed (e.g., project already exists)
        """
        params = {
            "project": key,
            "name": name,
        }

        await self._request("POST", "/api/projects/create", params=params)

    async def delete_project(self, key: str) -> None:
        """Delete a SonarQube project.

        Args:
            key: Project key to delete

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed (e.g., project doesn't exist)
        """
        params = {
            "project": key,
        }

        await self._request("POST", "/api/projects/delete", params=params)

    async def project_exists(self, key: str) -> bool:
        """Check if a project exists.

        Args:
            key: Project key to check

        Returns:
            True if project exists, False otherwise

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        params = {
            "projects": key,
        }

        data = await self._request("GET", "/api/projects/search", params=params)

        # Response format: {"components": [...], "paging": {...}}
        components = data.get("components", [])
        return len(components) > 0

    async def get_project_analyses_count(self, project_key: str) -> int:
        """Get the number of analyses run for a project.

        Args:
            project_key: Project key to check

        Returns:
            Number of analyses run on this project

        Raises:
            SonarQubeAuthError: Authentication failed
            SonarQubeAPIError: API request failed
        """
        params = {
            "project": project_key,
        }

        data = await self._request("GET", "/api/project_analyses/search", params=params)

        # Response format: {"analyses": [...], "paging": {...}}
        analyses = data.get("analyses", [])
        return len(analyses)
