"""Tests for ReviewOrchestrator class."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from vibe_heal.config import VibeHealConfig

from vibe_heal.review.models import FileReview, ReviewIssue, ReviewResult
from vibe_heal.review.reporter import load_report, write_reports
from vibe_heal.sonarqube.analysis_runner import AnalysisResult
from vibe_heal.sonarqube.models import SonarQubeIssue


@pytest.fixture
def config() -> VibeHealConfig:
    """Create test configuration."""
    from vibe_heal.config import VibeHealConfig

    return VibeHealConfig(
        sonarqube_url="https://sonar.test.com",
        sonarqube_token="test-token",
        sonarqube_project_key="my-project",
    )


def _make_sonar_issue(line: int, file_path: str = "src/file.py") -> SonarQubeIssue:
    """Create a SonarQube issue for testing."""
    return SonarQubeIssue(
        key=f"issue-{line}",
        rule="python:S1481",
        message=f"Issue at line {line}",
        component=file_path,
        line=line,
        severity="MAJOR",
    )


def _make_review_result(total_issues: int = 2) -> ReviewResult:
    """Create a sample ReviewResult for testing."""
    return ReviewResult(
        project_key="temp-project-key",
        branch="feature/test",
        base_branch="origin/main",
        generated_at=datetime(2025, 10, 24, 14, 30, 0, tzinfo=timezone.utc),
        files=[
            FileReview(
                file_path="src/file.py",
                issues=[
                    ReviewIssue(rule="python:S1481", message="Issue 1", line=10, severity="MAJOR"),
                    ReviewIssue(rule="python:S1192", message="Issue 2", line=20, severity="MINOR"),
                ],
            )
        ],
    )


class TestReviewOrchestratorInit:
    """Tests for ReviewOrchestrator initialization."""

    def test_init_creates_sub_components(self, config: VibeHealConfig) -> None:
        """Test that the orchestrator creates all required sub-components."""
        from vibe_heal.review.orchestrator import ReviewOrchestrator

        mock_client = AsyncMock()
        mock_analyzer = MagicMock()
        mock_parser = MagicMock()
        orchestrator = ReviewOrchestrator(config, mock_client, mock_analyzer, mock_parser)

        assert orchestrator.config == config
        assert orchestrator.client == mock_client
        assert orchestrator.branch_analyzer is mock_analyzer
        assert orchestrator.diff_parser is mock_parser
        assert orchestrator.project_manager is not None
        assert orchestrator.analysis_runner is not None
        assert orchestrator.github_client is not None


class TestRunAnalysis:
    """Tests for ReviewOrchestrator.run_analysis()."""

    @pytest.fixture
    def mock_branch_analyzer(self) -> MagicMock:
        """Create a mocked BranchAnalyzer for tests."""
        mock = MagicMock()
        mock.get_current_branch.return_value = "feature/test"
        mock.get_user_email.return_value = "user@example.com"
        return mock

    @pytest.fixture
    def mock_diff_parser(self) -> MagicMock:
        """Create a mocked DiffParser for tests."""
        mock = MagicMock()
        mock.get_changed_lines.return_value = {}
        mock.get_raw_diff.return_value = ""
        return mock

    @pytest.fixture
    def orchestrator(self, config: VibeHealConfig, mock_branch_analyzer, mock_diff_parser):
        """Create ReviewOrchestrator with mocked git dependencies."""
        from vibe_heal.review.orchestrator import ReviewOrchestrator

        mock_client = AsyncMock()
        return ReviewOrchestrator(config, mock_client, mock_branch_analyzer, mock_diff_parser)

    @pytest.mark.asyncio
    async def test_no_modified_files_returns_empty_result(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """When branch has no modified files, return empty result without creating temp project."""
        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[],
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                new_callable=AsyncMock,
            ) as mock_create,
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            result = await orchestrator.run_analysis(
                base_branch="origin/main",
                report_file=tmp_path / "review.json",
            )

        assert result.success is True
        assert result.total_issues == 0
        assert result.files == []
        # Should not create temp project
        mock_create.assert_not_called()
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_analysis_failure_returns_error(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """When analysis fails, return error result and cleanup temp project."""
        temp_project = MagicMock()
        temp_project.project_key = "temp-key"
        temp_project.project_name = "temp-name"

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature/test",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(
                    success=False,
                    error_message="Scanner not found",
                ),
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.run_analysis(
                base_branch="origin/main",
                report_file=tmp_path / "review.json",
            )

        assert result.success is False
        assert "Scanner not found" in (result.error_message or "")
        # Temp project should be cleaned up
        mock_delete.assert_called_once_with("temp-key")

    @pytest.mark.asyncio
    async def test_no_issues_on_changed_lines(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """When there are no issues on changed lines, return empty result."""
        temp_project = MagicMock()
        temp_project.project_key = "temp-key"
        temp_project.project_name = "temp-name"

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature/test",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.project_manager,
                "copy_exclusion_settings",
                return_value=([], 0),
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="task-1", dashboard_url="http://dash"),
            ),
            patch.object(
                orchestrator.client,
                "get_issues_for_file",
                return_value=[],
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.run_analysis(
                base_branch="origin/main",
                report_file=tmp_path / "review.json",
            )

        assert result.success is True
        assert result.total_issues == 0
        # Report should still be written
        mock_delete.assert_called_once_with("temp-key")

    @pytest.mark.asyncio
    async def test_full_happy_path(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """Full happy path: modified files, analysis succeeds, issues found on changed lines."""
        temp_project = MagicMock()
        temp_project.project_key = "temp-key"
        temp_project.project_name = "temp-name"

        # SonarQube returns issues; only line 10 is on a changed line
        sonar_issues = [
            _make_sonar_issue(10),  # on changed line
            _make_sonar_issue(50),  # NOT on changed line
            _make_sonar_issue(20),  # on changed line
        ]

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature/test",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.diff_parser,
                "get_changed_lines",
                return_value={"src/file.py": {10, 20}},
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.project_manager,
                "copy_exclusion_settings",
                return_value=([], 0),
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="task-1", dashboard_url="http://dash"),
            ),
            patch.object(
                orchestrator.client,
                "get_issues_for_file",
                return_value=sonar_issues,
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.run_analysis(
                base_branch="origin/main",
                report_file=tmp_path / "review.json",
            )

        assert result.success is True
        # Only issues on changed lines (10, 20) should be included
        assert result.total_issues == 2
        assert len(result.files) == 1
        assert result.files[0].file_path == "src/file.py"
        assert len(result.files[0].issues) == 2
        issue_lines = {i.line for i in result.files[0].issues}
        assert issue_lines == {10, 20}
        mock_delete.assert_called_once_with("temp-key")
        # Diagnostics should capture the pipeline state for the file
        assert len(result.diagnostics) == 1
        diag = result.diagnostics[0]
        assert diag.file_path == "src/file.py"
        assert diag.changed_lines == sorted({10, 20})
        assert diag.sonar_issue_count == 3
        assert diag.sonar_issue_lines == [10, 20, 50]

    @pytest.mark.asyncio
    async def test_file_patterns_filter_files(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """File patterns should filter which files are analyzed."""
        temp_project = MagicMock()
        temp_project.project_key = "temp-key"
        temp_project.project_name = "temp-name"

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file.py"), Path("docs/readme.md")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature/test",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.project_manager,
                "copy_exclusion_settings",
                return_value=([], 0),
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="task-1", dashboard_url="http://dash"),
            ),
            patch.object(
                orchestrator.client,
                "get_issues_for_file",
                return_value=[],
            ) as mock_get_issues,
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ),
        ):
            await orchestrator.run_analysis(
                base_branch="origin/main",
                file_patterns=["*.py"],
                report_file=tmp_path / "review.json",
            )

        # Should only fetch issues for .py file
        mock_get_issues.assert_called_once()
        call_args = mock_get_issues.call_args
        assert str(Path("src/file.py")) in call_args[0][0] or call_args[0][0] == "src/file.py"

    @pytest.mark.asyncio
    async def test_temp_project_cleanup_on_exception(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """Temp project is cleaned up even when an unexpected exception occurs."""
        temp_project = MagicMock()
        temp_project.project_key = "temp-key"
        temp_project.project_name = "temp-name"

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature/test",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                side_effect=RuntimeError("Unexpected error"),
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ) as mock_delete,
        ):
            result = await orchestrator.run_analysis(
                base_branch="origin/main",
                report_file=tmp_path / "review.json",
            )

        assert result.success is False
        assert "Unexpected error" in (result.error_message or "")
        mock_delete.assert_called_once_with("temp-key")

    @pytest.mark.asyncio
    async def test_writes_report_file(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """Successful analysis writes a valid report file that can be loaded."""
        temp_project = MagicMock()
        temp_project.project_key = "temp-key"
        temp_project.project_name = "temp-name"

        with (
            patch.object(
                orchestrator.branch_analyzer,
                "get_modified_files",
                return_value=[Path("src/file.py")],
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_current_branch",
                return_value="feature/test",
            ),
            patch.object(
                orchestrator.branch_analyzer,
                "get_user_email",
                return_value="user@example.com",
            ),
            patch.object(
                orchestrator.diff_parser,
                "get_changed_lines",
                return_value={"src/file.py": {10}},
            ),
            patch.object(
                orchestrator.project_manager,
                "create_temp_project",
                return_value=temp_project,
            ),
            patch.object(
                orchestrator.project_manager,
                "copy_exclusion_settings",
                return_value=([], 0),
            ),
            patch.object(
                orchestrator.analysis_runner,
                "run_analysis",
                return_value=AnalysisResult(success=True, task_id="task-1", dashboard_url="http://dash"),
            ),
            patch.object(
                orchestrator.client,
                "get_issues_for_file",
                return_value=[_make_sonar_issue(10)],
            ),
            patch.object(
                orchestrator.project_manager,
                "delete_project",
                new_callable=AsyncMock,
            ),
        ):
            report_path = tmp_path / "reports" / "review.json"
            result = await orchestrator.run_analysis(
                base_branch="origin/main",
                report_file=report_path,
            )

        assert result.success is True
        # Verify report was written and is loadable
        report_dir = report_path.parent
        assert (report_dir / "review.json").exists()
        loaded = load_report(report_dir)
        assert loaded.total_issues == 1
        assert loaded.branch == "feature/test"
        assert loaded.base_branch == "origin/main"
        # Diagnostics must be persisted in the JSON report
        assert len(loaded.diagnostics) == 1
        diag = loaded.diagnostics[0]
        assert diag.sonar_issue_count == 1
        assert diag.sonar_issue_lines == [10]
        assert diag.changed_lines == [10]


class TestRunPost:
    """Tests for ReviewOrchestrator.run_post()."""

    @pytest.fixture
    def orchestrator(self, config: VibeHealConfig):
        """Create ReviewOrchestrator with mocked dependencies."""
        from vibe_heal.review.orchestrator import ReviewOrchestrator

        mock_client = AsyncMock()
        mock_analyzer = MagicMock()
        mock_parser = MagicMock()
        return ReviewOrchestrator(config, mock_client, mock_analyzer, mock_parser)

    @pytest.mark.asyncio
    async def test_reads_saved_report_and_posts_review(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """run_post loads the saved report and posts review comments."""
        # Write a report to disk
        result = _make_review_result()
        report_dir = tmp_path / "reports"
        write_reports(result, report_dir)
        report_file = report_dir / "review.json"

        with (
            patch.object(
                orchestrator.github_client,
                "detect_pr",
                return_value=42,
            ) as mock_detect,
            patch.object(
                orchestrator.github_client,
                "post_review",
                new_callable=AsyncMock,
            ) as mock_post,
        ):
            await orchestrator.run_post(
                report_file=report_file,
                pr_number=None,
            )

        mock_detect.assert_called_once()
        mock_post.assert_called_once()
        # Verify the posted report matches what was saved
        posted_report = mock_post.call_args[0][1]
        assert posted_report.total_issues == 2
        assert posted_report.branch == "feature/test"

    @pytest.mark.asyncio
    async def test_explicit_pr_number_skips_detection(
        self,
        orchestrator,
        tmp_path: Path,
    ) -> None:
        """When pr_number is provided, detect_pr is not called."""
        result = _make_review_result()
        report_dir = tmp_path / "reports"
        write_reports(result, report_dir)
        report_file = report_dir / "review.json"

        with (
            patch.object(
                orchestrator.github_client,
                "detect_pr",
                return_value=42,
            ) as mock_detect,
            patch.object(
                orchestrator.github_client,
                "post_review",
                new_callable=AsyncMock,
            ) as mock_post,
        ):
            await orchestrator.run_post(
                report_file=report_file,
                pr_number=99,
            )

        mock_detect.assert_not_called()
        # post_review should be called with explicit PR number
        assert mock_post.call_count == 1
        posted_pr = mock_post.call_args[0][0]
        assert posted_pr == 99

    @pytest.mark.asyncio
    async def test_report_file_not_found_raises(self, orchestrator) -> None:
        """When the report file doesn't exist, raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await orchestrator.run_post(
                report_file=Path("/nonexistent/path/review.json"),
            )
