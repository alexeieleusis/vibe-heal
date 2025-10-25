"""SonarQube project lifecycle management for temporary projects."""

import re
from datetime import datetime, timezone

from pydantic import BaseModel

from vibe_heal.sonarqube.client import SonarQubeClient


class TempProjectMetadata(BaseModel):
    """Metadata for temporary SonarQube projects."""

    project_key: str
    project_name: str
    created_at: str  # ISO timestamp
    base_project_key: str
    branch_name: str
    user_email: str


class ProjectManager:
    """Manages temporary SonarQube project lifecycle.

    Creates uniquely named temporary projects for branch analysis and
    ensures proper cleanup even on errors.
    """

    def __init__(self, client: SonarQubeClient) -> None:
        """Initialize the ProjectManager.

        Args:
            client: SonarQube API client
        """
        self.client = client

    async def create_temp_project(
        self,
        base_key: str,
        branch_name: str,
        user_email: str,
    ) -> TempProjectMetadata:
        """Create temporary project for branch analysis.

        Project key/name format: {base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}
        Timestamp format: yymmdd-hhmm
        Sanitization: replace non-alphanumeric with underscore, lowercase.

        Args:
            base_key: Base project key (from .env.vibeheal)
            branch_name: Current branch name
            user_email: Git user email

        Returns:
            Metadata for the created project (for later cleanup)

        Raises:
            SonarQubeAPIError: If project creation fails
        """
        # Sanitize components
        sanitized_email = self._sanitize_identifier(user_email)
        sanitized_branch = self._sanitize_identifier(branch_name)

        # Generate timestamp in yymmdd-hhmm format
        timestamp = datetime.now(timezone.utc).strftime("%y%m%d-%H%M")

        # Build project key and name
        project_key = f"{base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}"
        project_name = project_key  # Use same value for both

        # Create project via API
        await self.client.create_project(project_key, project_name)

        # Build metadata
        metadata = TempProjectMetadata(
            project_key=project_key,
            project_name=project_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            base_project_key=base_key,
            branch_name=branch_name,
            user_email=user_email,
        )

        return metadata

    async def delete_project(self, project_key: str) -> None:
        """Delete a SonarQube project.

        Args:
            project_key: Project key to delete

        Raises:
            SonarQubeAPIError: If project deletion fails
        """
        await self.client.delete_project(project_key)

    async def project_exists(self, project_key: str) -> bool:
        """Check if a project exists.

        Args:
            project_key: Project key to check

        Returns:
            True if project exists, False otherwise

        Raises:
            SonarQubeAPIError: If API request fails
        """
        return await self.client.project_exists(project_key)

    def _sanitize_identifier(self, value: str) -> str:
        """Sanitize string for use in project key.

        Replaces non-alphanumeric characters (except underscores) with underscores
        and converts to lowercase.

        Args:
            value: String to sanitize

        Returns:
            Sanitized string (alphanumeric + underscores, lowercase)

        Examples:
            >>> pm._sanitize_identifier("user@example.com")
            'user_example_com'
            >>> pm._sanitize_identifier("feature/new-api")
            'feature_new_api'
            >>> pm._sanitize_identifier("Fix Bug #123")
            'fix_bug__123'
        """
        # Replace non-alphanumeric (except underscore) with underscore
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", value)
        # Convert to lowercase
        return sanitized.lower()
