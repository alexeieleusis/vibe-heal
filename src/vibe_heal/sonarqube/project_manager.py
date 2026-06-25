"""SonarQube project lifecycle management for temporary projects."""

import logging
import re
from datetime import datetime, timezone
from typing import ClassVar

from pydantic import BaseModel

from vibe_heal.output import console, dim, warn
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import SonarQubeError

logger = logging.getLogger(__name__)


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

    EXCLUSION_SETTINGS: ClassVar[tuple[str, ...]] = (
        "sonar.exclusions",
        "sonar.test.exclusions",
        "sonar.coverage.exclusions",
        "sonar.cpd.exclusions",
        "sonar.inclusions",
        "sonar.test.inclusions",
    )

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
        command_name: str = "analysis",
    ) -> TempProjectMetadata:
        """Create temporary project for branch analysis.

        Project key format: {base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}
        Project name format: {base_key} {command_name} {email_local_part} {branch_with_dashes}
        Timestamp format: yymmdd-hhmm
        Sanitization: replace non-alphanumeric with underscore, lowercase.

        Args:
            base_key: Base project key (from .env.vibeheal)
            branch_name: Current branch name
            user_email: Git user email
            command_name: Name of the command creating the project (e.g. "cleanup", "review")

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

        project_key = f"{base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}"
        email_local = user_email.split("@")[0] if "@" in user_email else user_email
        branch_display = branch_name.replace("/", "-")
        project_name = f"{base_key} {command_name} {email_local} {branch_display}"

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

    async def copy_exclusion_settings(self, source_key: str, target_key: str) -> tuple[list[str], int, int]:
        """Copy exclusion settings from source project to target project.

        Args:
            source_key: Source project key to copy settings from
            target_key: Target project key to copy settings to

        Returns:
            Tuple of (list of keys that were copied, count of inherited keys skipped,
            count of keys that failed to apply)

        Raises:
            SonarQubeError: If fetching settings from the source project fails
        """
        settings = await self.client.get_project_settings(source_key)
        copied: list[str] = []
        inherited_count = 0
        failed_count = 0

        for setting in settings:
            key = setting.get("key")
            inherited = setting.get("inherited", False)

            if key not in self.EXCLUSION_SETTINGS:
                continue

            if inherited:
                inherited_count += 1
                continue

            values = self._normalize_setting_values(setting)
            if not values:
                continue

            try:
                await self.client.set_project_setting(target_key, key, values)
            except SonarQubeError as e:
                logger.warning(f"Failed to set {key} on {target_key}: {e}")
                failed_count += 1
                continue

            copied.append(key)

        return copied, inherited_count, failed_count

    def _normalize_setting_values(self, setting: dict) -> list[str]:
        """Normalize setting values to a list of strings.

        Handles both scalar ('value') and multi-value ('values') shapes.

        Args:
            setting: Raw setting dict from the API

        Returns:
            List of string values
        """
        if "values" in setting:
            vals = setting["values"]
            if isinstance(vals, list):
                return [str(v) for v in vals]
            return [str(vals)]
        if "value" in setting:
            val = setting["value"]
            if val is None:
                return []
            if isinstance(val, list):
                return [str(v) for v in val]
            return [str(val)]
        return []

    async def create_temp_project_with_settings(
        self,
        base_key: str,
        branch_name: str,
        user_email: str,
        command_name: str = "analysis",
    ) -> TempProjectMetadata:
        """Create temporary project and copy exclusion settings from source.

        Combines temp project creation with exclusion settings copy into a
        single operation, used by both cleanup and deduplication workflows.

        Args:
            base_key: Base project key (source project to copy settings from)
            branch_name: Current branch name
            user_email: Git user email
            command_name: Name of the command creating the project (e.g. "cleanup", "review")

        Returns:
            Metadata for the created project
        """
        console.print("\n[dim]Creating temporary SonarQube project...[/dim]")
        temp_project = await self.create_temp_project(
            base_key=base_key,
            branch_name=branch_name,
            user_email=user_email,
            command_name=command_name,
        )
        dim(f"Created project: {temp_project.project_key}")

        try:
            copied, inherited_count, failed_count = await self.copy_exclusion_settings(
                source_key=base_key,
                target_key=temp_project.project_key,
            )
            if copied:
                dim(f"Copied {len(copied)} exclusion setting(s): {', '.join(copied)}")
            if inherited_count:
                dim(f"Skipped {inherited_count} inherited setting(s)")
            if failed_count:
                warn(f"Warning: Failed to apply {failed_count} exclusion setting(s)")
            if not copied and not inherited_count and not failed_count:
                console.print("[dim]No exclusion settings configured on source project[/dim]")
        except SonarQubeError as e:
            warn(f"Warning: Could not copy exclusion settings: {e}")

        return temp_project

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
        sanitized = re.sub(r"\W", "_", value)
        # Convert to lowercase
        return sanitized.lower()
