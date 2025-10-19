"""SonarQube API client."""

from typing import Any

import httpx

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.exceptions import (
    SonarQubeAPIError,
    SonarQubeAuthError,
)
from vibe_heal.sonarqube.models import IssuesResponse, SonarQubeIssue


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

            if response.status_code >= 400:
                raise SonarQubeAPIError(
                    f"API request failed: {response.text}",
                    status_code=response.status_code,
                )

            result: dict[Any, Any] = response.json()
            return result

        except httpx.HTTPError as e:
            raise SonarQubeAPIError(f"HTTP error: {e}") from e

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
        issues: list[SonarQubeIssue] = []
        page = 1
        page_size = 100

        # Build component identifier: projectKey:filePath
        # SonarQube uses lowercase project key in component paths
        component = f"{self.config.sonarqube_project_key.lower()}:{file_path}"

        while True:
            params = {
                "components": component,  # Use components (not componentKeys) for specific file
                "p": page,
                "ps": page_size,
            }

            # Use issueStatuses instead of resolved for more precise filtering
            if not resolved:
                params["issueStatuses"] = "OPEN,CONFIRMED"

            data = await self._request("GET", "/api/issues/search", params=params)
            response = IssuesResponse(**data)

            # Add all issues from this page (already filtered by component)
            issues.extend(response.issues)

            # Check if there are more pages
            # Model validator ensures total is never None, but check for safety
            if response.total is None:
                raise SonarQubeAPIError("API response missing total count")
            total_pages = (response.total + page_size - 1) // page_size
            if page >= total_pages:
                break

            page += 1

        return issues
