"""SonarQube analysis execution via sonar-scanner CLI."""

import asyncio
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import SonarQubeAPIError

console = Console()
logger = logging.getLogger(__name__)


class AnalysisResult(BaseModel):
    """Result of a SonarQube analysis run."""

    success: bool
    task_id: str | None = None
    dashboard_url: str | None = None
    error_message: str | None = None


class AnalysisRunner:
    """Executes SonarQube analysis using sonar-scanner CLI.

    Runs sonar-scanner as a subprocess and waits for analysis completion
    on the SonarQube server.
    """

    def __init__(self, config: VibeHealConfig, client: SonarQubeClient) -> None:
        """Initialize the AnalysisRunner.

        Args:
            config: Application configuration
            client: SonarQube API client (for polling analysis status)
        """
        self.config = config
        self.client = client

    async def run_analysis(
        self,
        project_key: str,
        project_name: str,
        project_dir: Path,
        sources: list[Path] | None = None,
    ) -> AnalysisResult:
        """Run SonarQube analysis on project.

        Args:
            project_key: SonarQube project key
            project_name: SonarQube project name
            project_dir: Root directory to analyze
            sources: Optional list of specific files/dirs to analyze (relative to project_dir)

        Returns:
            AnalysisResult with success status and details

        Raises:
            SonarQubeAPIError: If scanner execution fails or analysis times out
        """
        # Check scanner is available
        if not self.validate_scanner_available():
            return AnalysisResult(
                success=False,
                error_message="sonar-scanner is not installed or not in PATH. "
                "Install from: https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/",
            )

        # Build scanner command
        command = self._get_scanner_command(
            project_key=project_key,
            project_name=project_name,
            project_dir=project_dir,
            sources=sources,
        )

        # Execute scanner
        try:
            console.print(f"[dim]    Executing: sonar-scanner (project: {project_key})[/dim]")
            result = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            console.print("[dim]    Waiting for scanner to complete...[/dim]")
            stdout, stderr = await result.communicate()
            console.print(f"[dim]    Scanner finished with exit code: {result.returncode}[/dim]")

            if result.returncode != 0:
                error_output = stderr.decode() if stderr else stdout.decode()
                console.print(f"[red]    Scanner error: {error_output[:500]}[/red]")
                return AnalysisResult(
                    success=False,
                    error_message=f"sonar-scanner failed with exit code {result.returncode}: {error_output}",
                )

            # Extract task ID from scanner output
            scanner_output = stdout.decode()
            console.print("[dim]    Extracting task ID from scanner output...[/dim]")
            task_id = self._extract_task_id(scanner_output)

            if not task_id:
                console.print("[red]    Could not find task ID in scanner output[/red]")
                console.print("[dim]    See debug log for full scanner output[/dim]")
                # Log full scanner output to debug log for troubleshooting
                logger.debug("Full scanner output when task ID extraction failed:\n%s", scanner_output)
                return AnalysisResult(
                    success=False,
                    error_message="Could not extract task ID from scanner output",
                )

            console.print(f"[dim]    Task ID: {task_id}[/dim]")

            # Wait for analysis to complete on server
            console.print("[dim]    Waiting for server-side analysis to complete...[/dim]")
            analysis_success = await self._wait_for_analysis(task_id, timeout=300)

            if not analysis_success:
                console.print("[red]    Analysis timed out or failed on server[/red]")
                return AnalysisResult(
                    success=False,
                    task_id=task_id,
                    error_message="Analysis timed out or failed on server",
                )

            console.print("[green]    ✓ Server-side analysis completed successfully[/green]")

            # Build dashboard URL
            dashboard_url = f"{self.config.sonarqube_url}/dashboard?id={project_key}"

            return AnalysisResult(
                success=True,
                task_id=task_id,
                dashboard_url=dashboard_url,
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                error_message=f"Failed to run analysis: {e}",
            )

    def _get_scanner_command(
        self,
        project_key: str,
        project_name: str,
        project_dir: Path,
        sources: list[Path] | None = None,
    ) -> list[str]:
        """Build sonar-scanner command with parameters.

        Args:
            project_key: SonarQube project key
            project_name: SonarQube project name
            project_dir: Root directory to analyze
            sources: Optional list of specific files/dirs to analyze

        Returns:
            Command list ready for subprocess execution
        """
        command = [
            "sonar-scanner",
            f"-Dsonar.projectKey={project_key}",
            f"-Dsonar.projectName={project_name}",
            f"-Dsonar.host.url={self.config.sonarqube_url}",
        ]

        # Add authentication
        if self.config.use_token_auth:
            command.append(f"-Dsonar.token={self.config.sonarqube_token}")
        else:
            command.append(f"-Dsonar.login={self.config.sonarqube_username}")
            command.append(f"-Dsonar.password={self.config.sonarqube_password}")

        # Add sources if specified (optimization for partial analysis)
        if sources:
            # Convert Paths to strings, relative to project_dir
            sources_str = ",".join(str(s) for s in sources)
            command.append(f"-Dsonar.sources={sources_str}")
        else:
            # Default to current directory
            command.append("-Dsonar.sources=.")

        return command

    async def _wait_for_analysis(self, task_id: str, timeout: int = 300) -> bool:
        """Poll SonarQube for analysis completion.

        Args:
            task_id: Analysis task ID from scanner
            timeout: Maximum seconds to wait (default: 300)

        Returns:
            True if analysis succeeded, False if failed or timed out
        """
        poll_interval = 2  # seconds between polls
        elapsed = 0
        last_status = None

        while elapsed < timeout:
            try:
                # Query task status via API
                data = await self.client._request("GET", "/api/ce/task", params={"id": task_id})

                task = data.get("task", {})
                status = task.get("status")

                # Only log status changes to reduce noise
                if status != last_status:
                    console.print(f"[dim]    Analysis status: {status}[/dim]")
                    last_status = status

                if status == "SUCCESS":
                    return True
                if status in ("FAILED", "CANCELED"):
                    console.print(f"[red]    Analysis failed with status: {status}[/red]")
                    return False

                # Status is PENDING or IN_PROGRESS, keep waiting
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            except SonarQubeAPIError as e:
                console.print(f"[yellow]    Warning: API error while polling: {e}[/yellow]")
                # API error, keep trying
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        # Timeout reached
        console.print(f"[red]    Timeout reached after {timeout} seconds[/red]")
        return False

    def _extract_task_id(self, scanner_output: str) -> str | None:
        """Extract task ID from sonar-scanner output.

        The scanner prints a line like:
        "More about the report processing at https://sonar.example.com/api/ce/task?id=AY..."

        Args:
            scanner_output: stdout from sonar-scanner

        Returns:
            Task ID if found, None otherwise
        """
        for line in scanner_output.split("\n"):
            if "api/ce/task?id=" in line:
                # Extract task ID from URL
                parts = line.split("api/ce/task?id=")
                if len(parts) > 1:
                    # Task ID is everything after "id=" until whitespace or end
                    task_id = parts[1].split()[0].strip()
                    return task_id

        return None

    def validate_scanner_available(self) -> bool:
        """Check if sonar-scanner is installed and available.

        Returns:
            True if sonar-scanner is in PATH, False otherwise
        """
        return shutil.which("sonar-scanner") is not None
