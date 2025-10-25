"""Tests for AnalysisRunner class."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from vibe_heal.config import VibeHealConfig
from vibe_heal.sonarqube.analysis_runner import AnalysisResult, AnalysisRunner
from vibe_heal.sonarqube.client import SonarQubeClient
from vibe_heal.sonarqube.exceptions import SonarQubeAPIError


@pytest.fixture
def config() -> VibeHealConfig:
    """Create test configuration."""
    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_token="test-token",
        sonarqube_project_key="my-project",
    )


@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock SonarQubeClient."""
    client = AsyncMock(spec=SonarQubeClient)
    return client


@pytest.fixture
def analysis_runner(config: VibeHealConfig, mock_client: AsyncMock) -> AnalysisRunner:
    """Create an AnalysisRunner with mocked client."""
    return AnalysisRunner(config, mock_client)


class TestAnalysisRunnerInit:
    """Tests for AnalysisRunner initialization."""

    def test_init(self, config: VibeHealConfig, mock_client: AsyncMock) -> None:
        """Test AnalysisRunner initialization."""
        runner = AnalysisRunner(config, mock_client)

        assert runner.config == config
        assert runner.client == mock_client


class TestValidateScannerAvailable:
    """Tests for validate_scanner_available method."""

    def test_scanner_available(self, analysis_runner: AnalysisRunner) -> None:
        """Test when scanner is available in PATH."""
        with patch("shutil.which", return_value="/usr/bin/sonar-scanner"):
            assert analysis_runner.validate_scanner_available() is True

    def test_scanner_not_available(self, analysis_runner: AnalysisRunner) -> None:
        """Test when scanner is not in PATH."""
        with patch("shutil.which", return_value=None):
            assert analysis_runner.validate_scanner_available() is False


class TestGetScannerCommand:
    """Tests for _get_scanner_command method."""

    def test_basic_command(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test basic scanner command generation."""
        command = analysis_runner._get_scanner_command(
            project_key="test-project",
            project_name="Test Project",
            project_dir=tmp_path,
            sources=None,
        )

        assert "sonar-scanner" in command
        assert "-Dsonar.projectKey=test-project" in command
        assert "-Dsonar.projectName=Test Project" in command
        assert "-Dsonar.host.url=https://sonar.test.com" in command
        assert "-Dsonar.token=test-token" in command
        assert "-Dsonar.sources=." in command

    def test_command_with_sources(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test scanner command with specific sources."""
        sources = [Path("src/file1.py"), Path("src/file2.py")]

        command = analysis_runner._get_scanner_command(
            project_key="test-project",
            project_name="Test Project",
            project_dir=tmp_path,
            sources=sources,
        )

        assert "-Dsonar.sources=src/file1.py,src/file2.py" in command

    def test_command_with_basic_auth(self, mock_client: AsyncMock, tmp_path: Path) -> None:
        """Test scanner command with basic auth instead of token."""
        config = VibeHealConfig(
            sonarqube_url="https://sonar.test.com",
            sonarqube_username="testuser",
            sonarqube_password="testpass",
            sonarqube_project_key="my-project",
        )
        runner = AnalysisRunner(config, mock_client)

        command = runner._get_scanner_command(
            project_key="test-project",
            project_name="Test Project",
            project_dir=tmp_path,
            sources=None,
        )

        assert "-Dsonar.login=testuser" in command
        assert "-Dsonar.password=testpass" in command
        assert "-Dsonar.token" not in " ".join(command)


class TestExtractTaskId:
    """Tests for _extract_task_id method."""

    def test_extract_from_typical_output(self, analysis_runner: AnalysisRunner) -> None:
        """Test extracting task ID from typical scanner output."""
        output = """
INFO: Analysis report generated in 123ms
INFO: Analysis report uploaded in 456ms
INFO: More about the report processing at https://sonar.test.com/api/ce/task?id=AY1234567890
INFO: Analysis total time: 10.234 s
"""
        task_id = analysis_runner._extract_task_id(output)
        assert task_id == "AY1234567890"

    def test_extract_from_output_with_trailing_content(self, analysis_runner: AnalysisRunner) -> None:
        """Test extracting task ID when there's content after the ID."""
        output = """
INFO: More about the report processing at https://sonar.test.com/api/ce/task?id=AY_ABCD some other text
"""
        task_id = analysis_runner._extract_task_id(output)
        assert task_id == "AY_ABCD"

    def test_extract_returns_none_when_not_found(self, analysis_runner: AnalysisRunner) -> None:
        """Test that None is returned when task ID is not in output."""
        output = """
INFO: Analysis report generated
INFO: Some other info
"""
        task_id = analysis_runner._extract_task_id(output)
        assert task_id is None


class TestWaitForAnalysis:
    """Tests for _wait_for_analysis method."""

    @pytest.mark.asyncio
    async def test_analysis_succeeds_immediately(self, analysis_runner: AnalysisRunner, mock_client: AsyncMock) -> None:
        """Test when analysis succeeds on first poll."""
        mock_client._request.return_value = {"task": {"status": "SUCCESS"}}

        result = await analysis_runner._wait_for_analysis("test-task-id")

        assert result is True
        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_analysis_succeeds_after_pending(
        self, analysis_runner: AnalysisRunner, mock_client: AsyncMock
    ) -> None:
        """Test when analysis succeeds after being pending."""
        # First call: PENDING, second call: IN_PROGRESS, third call: SUCCESS
        mock_client._request.side_effect = [
            {"task": {"status": "PENDING"}},
            {"task": {"status": "IN_PROGRESS"}},
            {"task": {"status": "SUCCESS"}},
        ]

        result = await analysis_runner._wait_for_analysis("test-task-id")

        assert result is True
        assert mock_client._request.call_count == 3

    @pytest.mark.asyncio
    async def test_analysis_fails(self, analysis_runner: AnalysisRunner, mock_client: AsyncMock) -> None:
        """Test when analysis fails."""
        mock_client._request.return_value = {"task": {"status": "FAILED"}}

        result = await analysis_runner._wait_for_analysis("test-task-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_analysis_canceled(self, analysis_runner: AnalysisRunner, mock_client: AsyncMock) -> None:
        """Test when analysis is canceled."""
        mock_client._request.return_value = {"task": {"status": "CANCELED"}}

        result = await analysis_runner._wait_for_analysis("test-task-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_analysis_timeout(self, analysis_runner: AnalysisRunner, mock_client: AsyncMock) -> None:
        """Test when analysis times out."""
        import asyncio

        # Always return IN_PROGRESS to simulate timeout
        mock_client._request.return_value = {"task": {"status": "IN_PROGRESS"}}

        # Use timeout context manager as the caller would
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.1):  # Very short timeout for test
                await analysis_runner._wait_for_analysis("test-task-id")

    @pytest.mark.asyncio
    async def test_analysis_api_error_recovers(self, analysis_runner: AnalysisRunner, mock_client: AsyncMock) -> None:
        """Test recovery from temporary API errors."""
        # First call fails, second succeeds
        mock_client._request.side_effect = [
            SonarQubeAPIError("Temporary error"),
            {"task": {"status": "SUCCESS"}},
        ]

        result = await analysis_runner._wait_for_analysis("test-task-id")

        assert result is True
        assert mock_client._request.call_count == 2


class TestRunAnalysis:
    """Tests for run_analysis method."""

    @pytest.mark.asyncio
    async def test_scanner_not_available(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test when scanner is not installed."""
        with patch.object(analysis_runner, "validate_scanner_available", return_value=False):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is False
        assert "not installed" in result.error_message

    @pytest.mark.asyncio
    async def test_successful_analysis(
        self, analysis_runner: AnalysisRunner, mock_client: AsyncMock, tmp_path: Path
    ) -> None:
        """Test successful analysis execution."""
        scanner_output = b"""
INFO: Analysis report uploaded in 456ms
INFO: More about the report processing at https://sonar.test.com/api/ce/task?id=AY123
INFO: Analysis total time: 10.234 s
"""

        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(scanner_output, b""))

        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch.object(analysis_runner, "_wait_for_analysis", return_value=True),
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is True
        assert result.task_id == "AY123"
        assert result.dashboard_url == "https://sonar.test.com/dashboard?id=test-key"
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_scanner_execution_fails(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test when scanner execution fails."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"ERROR: Analysis failed"))

        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is False
        assert "exit code 1" in result.error_message
        assert "ERROR: Analysis failed" in result.error_message

    @pytest.mark.asyncio
    async def test_no_task_id_in_output(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test when task ID cannot be extracted from output."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"No task ID here", b""))

        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is False
        assert "Could not extract task ID" in result.error_message

    @pytest.mark.asyncio
    async def test_analysis_failed_on_server(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test when analysis fails on SonarQube server."""
        scanner_output = b"""
INFO: More about the report processing at https://sonar.test.com/api/ce/task?id=AY123
"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(scanner_output, b""))

        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch.object(analysis_runner, "_wait_for_analysis", return_value=False),
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is False
        assert result.task_id == "AY123"
        assert "failed on server" in result.error_message

    @pytest.mark.asyncio
    async def test_analysis_timeout_on_server(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test when analysis times out on SonarQube server."""
        import asyncio

        scanner_output = b"""
INFO: More about the report processing at https://sonar.test.com/api/ce/task?id=AY123
"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(scanner_output, b""))

        # Mock _wait_for_analysis to sleep forever (simulating timeout)
        async def wait_forever(task_id: str) -> bool:
            await asyncio.sleep(1000)
            return True

        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch.object(analysis_runner, "_wait_for_analysis", side_effect=wait_forever),
            patch("asyncio.timeout", return_value=asyncio.timeout(0.1)),  # Very short timeout
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is False
        assert result.task_id == "AY123"
        assert "timed out after 300 seconds" in result.error_message

    @pytest.mark.asyncio
    async def test_subprocess_exception(self, analysis_runner: AnalysisRunner, tmp_path: Path) -> None:
        """Test handling of subprocess exceptions."""
        with (
            patch.object(analysis_runner, "validate_scanner_available", return_value=True),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=Exception("Subprocess error"),
            ),
        ):
            result = await analysis_runner.run_analysis(
                project_key="test-key",
                project_name="Test Project",
                project_dir=tmp_path,
            )

        assert result.success is False
        assert "Failed to run analysis" in result.error_message
        assert "Subprocess error" in result.error_message


class TestAnalysisResult:
    """Tests for AnalysisResult model."""

    def test_successful_result(self) -> None:
        """Test creating a successful result."""
        result = AnalysisResult(
            success=True,
            task_id="AY123",
            dashboard_url="https://sonar.test.com/dashboard?id=test",
        )

        assert result.success is True
        assert result.task_id == "AY123"
        assert result.dashboard_url == "https://sonar.test.com/dashboard?id=test"
        assert result.error_message is None

    def test_failed_result(self) -> None:
        """Test creating a failed result."""
        result = AnalysisResult(
            success=False,
            error_message="Analysis failed",
        )

        assert result.success is False
        assert result.error_message == "Analysis failed"
        assert result.task_id is None
        assert result.dashboard_url is None
