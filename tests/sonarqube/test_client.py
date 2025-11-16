"""Tests for SonarQube client."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube import (
    SonarQubeAPIError,
    SonarQubeAuthError,
    SonarQubeClient,
)


@pytest.fixture
def config() -> VibeHealConfig:
    """Create test configuration."""
    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_token="test-token",
        sonarqube_project_key="my-project",
    )


@pytest.fixture
def config_basic_auth() -> VibeHealConfig:
    """Create test configuration with basic auth."""
    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_username="testuser",
        sonarqube_password="testpass",
        sonarqube_project_key="my-project",
    )


@pytest.fixture
def api_responses() -> dict:
    """Load API response fixtures."""
    fixtures_path = Path(__file__).parent / "fixtures" / "api_responses.json"
    with fixtures_path.open() as f:
        return json.load(f)


class TestSonarQubeClient:
    """Tests for SonarQubeClient."""

    def test_init(self, config: VibeHealConfig) -> None:
        """Test client initialization."""
        client = SonarQubeClient(config)

        assert client.config == config
        assert client.base_url == "https://sonar.test.com"
        assert client._client is None

    def test_get_auth_with_token(self, config: VibeHealConfig) -> None:
        """Test authentication setup with token."""
        client = SonarQubeClient(config)
        auth = client._get_auth()

        assert isinstance(auth, httpx.BasicAuth)
        # Just verify it's BasicAuth - the actual auth will be tested in integration

    def test_get_auth_with_basic(self, config_basic_auth: VibeHealConfig) -> None:
        """Test authentication setup with username/password."""
        client = SonarQubeClient(config_basic_auth)
        auth = client._get_auth()

        assert isinstance(auth, httpx.BasicAuth)
        # Just verify it's BasicAuth - the actual auth will be tested in integration

    @pytest.mark.asyncio
    async def test_context_manager(self, config: VibeHealConfig) -> None:
        """Test async context manager."""
        client = SonarQubeClient(config)

        assert client._client is None

        async with client:
            assert client._client is not None
            assert isinstance(client._client, httpx.AsyncClient)

        # Client should be closed after exiting context
        assert client._client is not None  # Reference remains but connection is closed

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_api_call(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test successful API call."""
        # Mock the API response
        route = respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_main_py"])
        )

        async with SonarQubeClient(config) as client:
            response = await client._request("GET", "/api/issues/search", params={"p": 1})

            assert response == api_responses["issues_response_main_py"]
            assert route.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_authentication_failure(self, config: VibeHealConfig) -> None:
        """Test authentication failure (401)."""
        respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(401, text="Unauthorized")
        )

        async with SonarQubeClient(config) as client:
            with pytest.raises(SonarQubeAuthError, match="Authentication failed"):
                await client._request("GET", "/api/issues/search")

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_500(self, config: VibeHealConfig) -> None:
        """Test API error (500)."""
        respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        async with SonarQubeClient(config) as client:
            with pytest.raises(SonarQubeAPIError) as exc_info:
                await client._request("GET", "/api/issues/search")

            assert exc_info.value.status_code == 500
            assert "API request failed" in str(exc_info.value)

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_404(self, config: VibeHealConfig) -> None:
        """Test API error (404)."""
        respx.get("https://sonar.test.com/api/issues/search").mock(return_value=httpx.Response(404, text="Not Found"))

        async with SonarQubeClient(config) as client:
            with pytest.raises(SonarQubeAPIError) as exc_info:
                await client._request("GET", "/api/issues/search")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_request_without_context_manager(self, config: VibeHealConfig) -> None:
        """Test that request fails without context manager."""
        client = SonarQubeClient(config)

        with pytest.raises(RuntimeError, match="Client not initialized"):
            await client._request("GET", "/api/issues/search")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_issues_for_file(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test getting issues for a specific file."""
        route = respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_main_py"])
        )

        async with SonarQubeClient(config) as client:
            issues = await client.get_issues_for_file("src/main.py")

            # Should return 2 issues (issue-1 and issue-2 are in src/main.py)
            assert len(issues) == 2
            assert issues[0].key == "issue-1"
            assert issues[1].key == "issue-2"

            # Verify the correct parameters were sent
            assert route.calls.last.request.url.params["components"] == "my-project:src/main.py"
            assert route.calls.last.request.url.params["issueStatuses"] == "OPEN,CONFIRMED"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_issues_for_file_no_matches(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test getting issues for file with no matches."""
        # API returns empty response when file has no issues
        route = respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_empty"])
        )

        async with SonarQubeClient(config) as client:
            issues = await client.get_issues_for_file("nonexistent.py")

            assert len(issues) == 0
            # Verify the correct component parameter was sent
            assert route.calls.last.request.url.params["components"] == "my-project:nonexistent.py"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_issues_for_file_empty_response(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test getting issues when API returns no issues."""
        respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_empty"])
        )

        async with SonarQubeClient(config) as client:
            issues = await client.get_issues_for_file("src/main.py")

            assert len(issues) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_issues_pagination(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test pagination handling."""
        # Create a response that indicates there are more pages
        page1_response = {
            "total": 250,  # More than page size (100)
            "p": 1,
            "ps": 100,
            "paging": {"pageIndex": 1, "pageSize": 100, "total": 250},
            "issues": [
                {
                    "key": f"issue-{i}",
                    "rule": "python:S1481",
                    "severity": "MAJOR",
                    "message": f"Issue {i}",
                    "component": "my-project:src/main.py",
                    "line": i,
                    "status": "OPEN",
                    "type": "CODE_SMELL",
                }
                for i in range(1, 11)  # 10 issues on page 1
            ],
        }

        page2_response = {
            "total": 250,
            "p": 2,
            "ps": 100,
            "paging": {"pageIndex": 2, "pageSize": 100, "total": 250},
            "issues": [
                {
                    "key": f"issue-{i}",
                    "rule": "python:S1481",
                    "severity": "MAJOR",
                    "message": f"Issue {i}",
                    "component": "my-project:src/main.py",
                    "line": i + 10,
                    "status": "OPEN",
                    "type": "CODE_SMELL",
                }
                for i in range(11, 21)  # 10 issues on page 2
            ],
        }

        page3_response = {
            "total": 250,
            "p": 3,
            "ps": 100,
            "paging": {"pageIndex": 3, "pageSize": 100, "total": 250},
            "issues": [],  # Empty last page
        }

        # Mock responses for multiple pages
        route = respx.get("https://sonar.test.com/api/issues/search")
        route.side_effect = [
            httpx.Response(200, json=page1_response),
            httpx.Response(200, json=page2_response),
            httpx.Response(200, json=page3_response),
        ]

        async with SonarQubeClient(config) as client:
            issues = await client.get_issues_for_file("src/main.py")

            # Should get issues from both pages
            assert len(issues) == 20
            assert issues[0].key == "issue-1"
            assert issues[-1].key == "issue-20"

            # Verify all pages used the correct component parameter
            for call in route.calls:
                assert call.request.url.params["components"] == "my-project:src/main.py"
                assert call.request.url.params["issueStatuses"] == "OPEN,CONFIRMED"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_issues_with_resolved_param(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test getting issues with resolved parameter."""
        route = respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_main_py"])
        )

        async with SonarQubeClient(config) as client:
            await client.get_issues_for_file("src/main.py", resolved=True)

            # When resolved=True, issueStatuses should not be in params (includes all statuses)
            assert "issueStatuses" not in route.calls.last.request.url.params
            assert route.calls.last.request.url.params["components"] == "my-project:src/main.py"

    @pytest.mark.asyncio
    @respx.mock
    async def test_component_path_construction(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test component path preserves project key case."""
        route = respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_main_py"])
        )

        async with SonarQubeClient(config) as client:
            # Component path should use project key as-is (case-sensitive)
            await client.get_issues_for_file("src/main.py")

            # Config has "my-project" (lowercase) so component should be "my-project:src/main.py"
            assert route.calls.last.request.url.params["components"] == "my-project:src/main.py"

    @pytest.mark.asyncio
    @respx.mock
    async def test_component_path_case_sensitive(self, api_responses: dict) -> None:
        """Test component path respects uppercase project keys (case-sensitive)."""
        # Create config with uppercase project key
        config_uppercase = VibeHealConfig(
            sonarqube_url="https://sonar.test.com",
            sonarqube_token="test-token",
            sonarqube_project_key="MY-PROJECT",  # Uppercase
        )

        route = respx.get("https://sonar.test.com/api/issues/search").mock(
            return_value=httpx.Response(200, json=api_responses["issues_response_main_py"])
        )

        async with SonarQubeClient(config_uppercase) as client:
            await client.get_issues_for_file("src/main.py")

            # Component should preserve uppercase: "MY-PROJECT:src/main.py"
            assert route.calls.last.request.url.params["components"] == "MY-PROJECT:src/main.py"

    @pytest.mark.asyncio
    @respx.mock
    async def test_different_files_get_different_components(self, config: VibeHealConfig, api_responses: dict) -> None:
        """Test that different files query different components."""
        route = respx.get("https://sonar.test.com/api/issues/search")
        route.side_effect = [
            httpx.Response(200, json=api_responses["issues_response_main_py"]),
            httpx.Response(200, json=api_responses["issues_response_utils_py"]),
        ]

        async with SonarQubeClient(config) as client:
            # Query for main.py
            issues1 = await client.get_issues_for_file("src/main.py")
            assert len(issues1) == 2
            assert route.calls[0].request.url.params["components"] == "my-project:src/main.py"

            # Query for utils.py
            issues2 = await client.get_issues_for_file("src/utils.py")
            assert len(issues2) == 1
            assert route.calls[1].request.url.params["components"] == "my-project:src/utils.py"

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_project_success(self, config: VibeHealConfig) -> None:
        """Test successful project creation."""
        route = respx.post("https://sonar.test.com/api/projects/create").mock(
            return_value=httpx.Response(200, json={"project": {"key": "test-project"}})
        )

        async with SonarQubeClient(config) as client:
            await client.create_project("test-project", "Test Project")

        assert route.called
        assert route.calls.last.request.url.params["project"] == "test-project"
        assert route.calls.last.request.url.params["name"] == "Test Project"

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_project_already_exists(self, config: VibeHealConfig) -> None:
        """Test error when creating duplicate project."""
        respx.post("https://sonar.test.com/api/projects/create").mock(
            return_value=httpx.Response(400, text="Project already exists")
        )

        async with SonarQubeClient(config) as client:
            with pytest.raises(SonarQubeAPIError, match="API request failed"):
                await client.create_project("existing-project", "Existing")

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_project_success(self, config: VibeHealConfig) -> None:
        """Test successful project deletion."""
        route = respx.post("https://sonar.test.com/api/projects/delete").mock(return_value=httpx.Response(204))

        async with SonarQubeClient(config) as client:
            await client.delete_project("test-project")

        assert route.called
        assert route.calls.last.request.url.params["project"] == "test-project"

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_project_not_found(self, config: VibeHealConfig) -> None:
        """Test error when deleting non-existent project."""
        respx.post("https://sonar.test.com/api/projects/delete").mock(
            return_value=httpx.Response(404, text="Project not found")
        )

        async with SonarQubeClient(config) as client:
            with pytest.raises(SonarQubeAPIError, match="API request failed"):
                await client.delete_project("nonexistent-project")

    @pytest.mark.asyncio
    @respx.mock
    async def test_project_exists_true(self, config: VibeHealConfig) -> None:
        """Test checking existence of existing project."""
        response_data = {
            "components": [{"key": "test-project", "name": "Test Project"}],
            "paging": {"pageIndex": 1, "pageSize": 100, "total": 1},
        }
        respx.get("https://sonar.test.com/api/projects/search").mock(
            return_value=httpx.Response(200, json=response_data)
        )

        async with SonarQubeClient(config) as client:
            exists = await client.project_exists("test-project")

        assert exists is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_project_exists_false(self, config: VibeHealConfig) -> None:
        """Test checking existence of non-existent project."""
        response_data = {
            "components": [],
            "paging": {"pageIndex": 1, "pageSize": 100, "total": 0},
        }
        respx.get("https://sonar.test.com/api/projects/search").mock(
            return_value=httpx.Response(200, json=response_data)
        )

        async with SonarQubeClient(config) as client:
            exists = await client.project_exists("nonexistent-project")

        assert exists is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_project_exists_query_params(self, config: VibeHealConfig) -> None:
        """Test that project_exists uses correct query parameters."""
        route = respx.get("https://sonar.test.com/api/projects/search").mock(
            return_value=httpx.Response(
                200, json={"components": [], "paging": {"pageIndex": 1, "pageSize": 100, "total": 0}}
            )
        )

        async with SonarQubeClient(config) as client:
            await client.project_exists("my-test-project")

        assert route.called
        assert route.calls.last.request.url.params["projects"] == "my-test-project"
