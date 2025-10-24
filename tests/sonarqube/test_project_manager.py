"""Tests for ProjectManager class."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import SonarQubeAPIError
from vibe_heal.sonarqube.project_manager import ProjectManager, TempProjectMetadata


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock SonarQubeClient."""
    client = AsyncMock(spec=SonarQubeClient)
    return client


@pytest.fixture
def project_manager(mock_client: AsyncMock) -> ProjectManager:
    """Create a ProjectManager with mocked client."""
    return ProjectManager(mock_client)


class TestProjectManagerInit:
    """Tests for ProjectManager initialization."""

    def test_init(self, mock_client: AsyncMock) -> None:
        """Test ProjectManager initialization."""
        manager = ProjectManager(mock_client)

        assert manager.client == mock_client


class TestCreateTempProject:
    """Tests for create_temp_project method."""

    @pytest.mark.asyncio
    async def test_create_temp_project_success(self, project_manager: ProjectManager, mock_client: AsyncMock) -> None:
        """Test successful temporary project creation."""
        base_key = "my_project"
        branch_name = "feature/new-api"
        user_email = "user@example.com"

        mock_client.create_project = AsyncMock()

        metadata = await project_manager.create_temp_project(base_key, branch_name, user_email)

        # Verify project was created with sanitized key
        expected_key = "my_project_user_example_com_feature_new_api"
        mock_client.create_project.assert_called_once_with(expected_key, expected_key)

        # Verify metadata
        assert metadata.project_key == expected_key
        assert metadata.project_name == expected_key
        assert metadata.base_project_key == base_key
        assert metadata.branch_name == branch_name
        assert metadata.user_email == user_email
        assert isinstance(metadata.created_at, str)

        # Verify timestamp is recent (within last minute)
        created_time = datetime.fromisoformat(metadata.created_at)
        now = datetime.now(timezone.utc)
        time_diff = (now - created_time).total_seconds()
        assert time_diff < 60

    @pytest.mark.asyncio
    async def test_create_temp_project_sanitizes_email(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        """Test that email addresses are properly sanitized."""
        mock_client.create_project = AsyncMock()

        metadata = await project_manager.create_temp_project("project", "main", "user+tag@example.co.uk")

        expected_key = "project_user_tag_example_co_uk_main"
        assert metadata.project_key == expected_key
        mock_client.create_project.assert_called_once_with(expected_key, expected_key)

    @pytest.mark.asyncio
    async def test_create_temp_project_sanitizes_branch(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        """Test that branch names are properly sanitized."""
        mock_client.create_project = AsyncMock()

        test_branches = [
            ("feature/api-v2", "feature_api_v2"),
            ("bugfix/issue-#123", "bugfix_issue__123"),
            ("hotfix/urgent!!", "hotfix_urgent__"),
            ("release/1.2.3", "release_1_2_3"),
        ]

        for branch, expected_sanitized in test_branches:
            metadata = await project_manager.create_temp_project("proj", branch, "user@test.com")
            expected_key = f"proj_user_test_com_{expected_sanitized}"
            assert metadata.project_key == expected_key

    @pytest.mark.asyncio
    async def test_create_temp_project_api_error(self, project_manager: ProjectManager, mock_client: AsyncMock) -> None:
        """Test error handling when project creation fails."""
        mock_client.create_project = AsyncMock(side_effect=SonarQubeAPIError("Project already exists", status_code=400))

        with pytest.raises(SonarQubeAPIError, match="Project already exists"):
            await project_manager.create_temp_project("project", "main", "user@test.com")

    @pytest.mark.asyncio
    async def test_create_temp_project_unique_keys(
        self, project_manager: ProjectManager, mock_client: AsyncMock
    ) -> None:
        """Test that different branches/users generate different project keys."""
        mock_client.create_project = AsyncMock()

        metadata1 = await project_manager.create_temp_project("proj", "branch1", "user1@test.com")
        metadata2 = await project_manager.create_temp_project("proj", "branch2", "user1@test.com")
        metadata3 = await project_manager.create_temp_project("proj", "branch1", "user2@test.com")

        # All keys should be different
        assert metadata1.project_key != metadata2.project_key
        assert metadata1.project_key != metadata3.project_key
        assert metadata2.project_key != metadata3.project_key


class TestDeleteProject:
    """Tests for delete_project method."""

    @pytest.mark.asyncio
    async def test_delete_project_success(self, project_manager: ProjectManager, mock_client: AsyncMock) -> None:
        """Test successful project deletion."""
        mock_client.delete_project = AsyncMock()

        await project_manager.delete_project("test_project")

        mock_client.delete_project.assert_called_once_with("test_project")

    @pytest.mark.asyncio
    async def test_delete_project_api_error(self, project_manager: ProjectManager, mock_client: AsyncMock) -> None:
        """Test error handling when project deletion fails."""
        mock_client.delete_project = AsyncMock(side_effect=SonarQubeAPIError("Project not found", status_code=404))

        with pytest.raises(SonarQubeAPIError, match="Project not found"):
            await project_manager.delete_project("nonexistent")


class TestProjectExists:
    """Tests for project_exists method."""

    @pytest.mark.asyncio
    async def test_project_exists_true(self, project_manager: ProjectManager, mock_client: AsyncMock) -> None:
        """Test checking existence of existing project."""
        mock_client.project_exists = AsyncMock(return_value=True)

        exists = await project_manager.project_exists("test_project")

        assert exists is True
        mock_client.project_exists.assert_called_once_with("test_project")

    @pytest.mark.asyncio
    async def test_project_exists_false(self, project_manager: ProjectManager, mock_client: AsyncMock) -> None:
        """Test checking existence of non-existent project."""
        mock_client.project_exists = AsyncMock(return_value=False)

        exists = await project_manager.project_exists("nonexistent")

        assert exists is False
        mock_client.project_exists.assert_called_once_with("nonexistent")


class TestSanitizeIdentifier:
    """Tests for _sanitize_identifier method."""

    def test_sanitize_email(self, project_manager: ProjectManager) -> None:
        """Test sanitization of email addresses."""
        test_cases = [
            ("user@example.com", "user_example_com"),
            ("first.last@example.com", "first_last_example_com"),
            ("user+tag@example.co.uk", "user_tag_example_co_uk"),
            ("123@test.com", "123_test_com"),
        ]

        for input_val, expected in test_cases:
            result = project_manager._sanitize_identifier(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_sanitize_branch_names(self, project_manager: ProjectManager) -> None:
        """Test sanitization of branch names."""
        test_cases = [
            ("feature/new-api", "feature_new_api"),
            ("bugfix/issue-#123", "bugfix_issue__123"),
            ("release/1.2.3", "release_1_2_3"),
            ("hotfix/urgent!", "hotfix_urgent_"),
            ("main", "main"),
            ("feature_branch", "feature_branch"),
        ]

        for input_val, expected in test_cases:
            result = project_manager._sanitize_identifier(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_sanitize_special_characters(self, project_manager: ProjectManager) -> None:
        """Test sanitization of various special characters."""
        test_cases = [
            ("test@#$%", "test____"),
            ("hello world", "hello_world"),
            ("Test-Case_123", "test_case_123"),
            ("a.b.c.d", "a_b_c_d"),
            ("mixed/chars-here_123", "mixed_chars_here_123"),
        ]

        for input_val, expected in test_cases:
            result = project_manager._sanitize_identifier(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_sanitize_uppercase_to_lowercase(self, project_manager: ProjectManager) -> None:
        """Test that sanitization converts to lowercase."""
        test_cases = [
            ("UPPERCASE", "uppercase"),
            ("MixedCase", "mixedcase"),
            ("User@Example.COM", "user_example_com"),
        ]

        for input_val, expected in test_cases:
            result = project_manager._sanitize_identifier(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_sanitize_preserves_underscores(self, project_manager: ProjectManager) -> None:
        """Test that underscores are preserved during sanitization."""
        test_cases = [
            ("already_sanitized", "already_sanitized"),
            ("test_with_underscores_123", "test_with_underscores_123"),
            ("_leading_underscore", "_leading_underscore"),
            ("trailing_underscore_", "trailing_underscore_"),
        ]

        for input_val, expected in test_cases:
            result = project_manager._sanitize_identifier(input_val)
            assert result == expected, f"Failed for input: {input_val}"

    def test_sanitize_consecutive_special_chars(self, project_manager: ProjectManager) -> None:
        """Test sanitization with consecutive special characters."""
        test_cases = [
            ("test---case", "test___case"),
            ("hello...world", "hello___world"),
            ("a@@b##c", "a__b__c"),
        ]

        for input_val, expected in test_cases:
            result = project_manager._sanitize_identifier(input_val)
            assert result == expected, f"Failed for input: {input_val}"


class TestTempProjectMetadata:
    """Tests for TempProjectMetadata model."""

    def test_metadata_creation(self) -> None:
        """Test creating TempProjectMetadata."""
        metadata = TempProjectMetadata(
            project_key="proj_user_test_com_main",
            project_name="proj_user_test_com_main",
            created_at="2025-10-23T12:00:00+00:00",
            base_project_key="proj",
            branch_name="main",
            user_email="user@test.com",
        )

        assert metadata.project_key == "proj_user_test_com_main"
        assert metadata.project_name == "proj_user_test_com_main"
        assert metadata.base_project_key == "proj"
        assert metadata.branch_name == "main"
        assert metadata.user_email == "user@test.com"
        assert metadata.created_at == "2025-10-23T12:00:00+00:00"

    def test_metadata_validation(self) -> None:
        """Test that metadata validates required fields."""
        from pydantic import ValidationError

        # Missing required field should raise error
        with pytest.raises(ValidationError):
            TempProjectMetadata(
                project_key="test",
                project_name="test",
                # Missing created_at
                base_project_key="base",
                branch_name="main",
            )
