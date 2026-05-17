"""Tests for ReviewOrchestrator class."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from vibe_heal.config import VibeHealConfig
    from vibe_heal.review.orchestrator import ReviewOrchestrator

from vibe_heal.git.diff_parser import DiffLines
from vibe_heal.review.models import (
    FileDiagnostics,
    FileReview,
    ReviewIssue,
    ReviewResult,
)
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
        mock.get_diff_lines.return_value = DiffLines(new_lines={}, old_lines={})
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
                "get_diff_lines",
                return_value=DiffLines(new_lines={"src/file.py": {10, 20}}, old_lines={}),
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
            patch.object(orchestrator, "_get_active_duplications", new_callable=AsyncMock, return_value=[]),
            patch.object(orchestrator, "_get_resolved_duplications", new_callable=AsyncMock, return_value=[]),
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
                "get_diff_lines",
                return_value=DiffLines(new_lines={"src/file.py": {10}}, old_lines={}),
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
            patch.object(orchestrator, "_get_active_duplications", new_callable=AsyncMock, return_value=[]),
            patch.object(orchestrator, "_get_resolved_duplications", new_callable=AsyncMock, return_value=[]),
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


class TestGetActiveDuplications:
    """Tests for ReviewOrchestrator._get_active_duplications()."""

    @pytest.fixture
    def orchestrator(self) -> ReviewOrchestrator:
        from vibe_heal.config import VibeHealConfig
        from vibe_heal.review.orchestrator import ReviewOrchestrator

        config = VibeHealConfig(
            sonarqube_url="https://sonar.test.com",
            sonarqube_token="test-token",
            sonarqube_project_key="temp-project",
        )
        mock_client = AsyncMock()
        mock_analyzer = MagicMock()
        mock_analyzer.repo.working_dir = "/repo"
        mock_parser = MagicMock()
        return ReviewOrchestrator(config, mock_client, mock_analyzer, mock_parser)

    def _make_response(self, from_line: int, size: int, other_file: str = "src/other.py") -> MagicMock:
        """Build a mock DuplicationsResponse with one group."""
        from vibe_heal.deduplication.models import DuplicationBlock, DuplicationGroup, DuplicationsResponse

        target_block = DuplicationBlock(**{"from": from_line, "size": size, "_ref": "1"})
        other_block = DuplicationBlock(**{"from": 50, "size": 10, "_ref": "2"})
        group = DuplicationGroup(blocks=[target_block, other_block])

        file_info_target = MagicMock()
        file_info_target.key = "temp-project:src/file.py"

        file_info_other = MagicMock()
        file_info_other.key = f"temp-project:{other_file}"

        response = MagicMock(spec=DuplicationsResponse)
        response.duplications = [group]
        response.get_target_file_ref.return_value = "1"
        response.get_file_info.side_effect = lambda ref: (file_info_target if ref == "1" else file_info_other)
        return response

    def _make_diag(self, file_path: str = "src/file.py") -> FileDiagnostics:
        return FileDiagnostics(file_path=file_path, lookup_key=file_path)

    @pytest.mark.asyncio
    async def test_block_intersecting_changed_lines_is_reported(self, orchestrator) -> None:
        """A duplication block overlapping changed lines produces a ReviewDuplication."""
        response = self._make_response(from_line=10, size=15)  # block lines 10-24

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.return_value = response

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_active_duplications(
                Path("src/file.py"),
                {"src/file.py": {12, 15}},  # lines inside the block
                diag,
            )

        assert len(result) == 1
        assert result[0].from_line == 10
        assert result[0].to_line == 24
        assert len(result[0].other_locations) == 1
        assert result[0].other_locations[0].file_path == "src/other.py"
        assert diag.active_dup_api_status == "ok"
        assert diag.active_dup_groups_found == 1
        assert diag.active_dup_target_ref_found is True
        assert diag.active_dup_blocks_intersecting == 1

    @pytest.mark.asyncio
    async def test_non_intersecting_block_is_skipped(self, orchestrator) -> None:
        """A duplication block not overlapping changed lines produces nothing."""
        response = self._make_response(from_line=100, size=10)  # block lines 100-109

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.return_value = response

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_active_duplications(
                Path("src/file.py"),
                {"src/file.py": {5, 6, 7}},  # lines outside the block
                diag,
            )

        assert result == []
        assert diag.active_dup_api_status == "ok"
        assert diag.active_dup_groups_found == 1
        assert diag.active_dup_blocks_intersecting == 0

    @pytest.mark.asyncio
    async def test_no_changed_lines_returns_empty(self, orchestrator) -> None:
        """When file has no changed lines, returns empty without calling API."""
        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            diag = self._make_diag()
            result = await orchestrator._get_active_duplications(
                Path("src/file.py"),
                {},  # no entry for this file
                diag,
            )

        MockDupClient.assert_not_called()
        assert result == []
        assert diag.active_dup_api_status == "skipped_no_changed_lines"

    @pytest.mark.asyncio
    async def test_component_not_found_returns_empty(self, orchestrator) -> None:
        """ComponentNotFoundError from the API is recorded in diagnostics."""
        from vibe_heal.sonarqube.exceptions import ComponentNotFoundError

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.side_effect = ComponentNotFoundError("not found")

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_active_duplications(
                Path("src/file.py"),
                {"src/file.py": {10}},
                diag,
            )

        assert result == []
        assert diag.active_dup_api_status == "component_not_found"

    @pytest.mark.asyncio
    async def test_unexpected_exception_recorded_in_diagnostics(self, orchestrator) -> None:
        """Any unexpected exception is recorded in diagnostics rather than propagating."""
        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.side_effect = ValueError("bad response")

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_active_duplications(
                Path("src/file.py"),
                {"src/file.py": {10}},
                diag,
            )

        assert result == []
        assert diag.active_dup_api_status.startswith("error:ValueError:")


class TestGetResolvedDuplications:
    """Tests for ReviewOrchestrator._get_resolved_duplications()."""

    @pytest.fixture
    def orchestrator(self) -> ReviewOrchestrator:
        from vibe_heal.config import VibeHealConfig
        from vibe_heal.review.orchestrator import ReviewOrchestrator

        config = VibeHealConfig(
            sonarqube_url="https://sonar.test.com",
            sonarqube_token="test-token",
            sonarqube_project_key="temp-project",
        )
        mock_client = AsyncMock()
        mock_client.config = config
        mock_analyzer = MagicMock()
        mock_analyzer.repo.working_dir = "/repo"
        mock_parser = MagicMock()
        return ReviewOrchestrator(config, mock_client, mock_analyzer, mock_parser)

    def _make_diag(self, file_path: str = "src/file.py") -> FileDiagnostics:
        return FileDiagnostics(file_path=file_path, lookup_key=file_path)

    def _make_response(self, from_line: int, size: int) -> MagicMock:
        from vibe_heal.deduplication.models import DuplicationBlock, DuplicationGroup, DuplicationsResponse

        target_block = DuplicationBlock(**{"from": from_line, "size": size, "_ref": "1"})
        other_block = DuplicationBlock(**{"from": 100, "size": 10, "_ref": "2"})
        group = DuplicationGroup(blocks=[target_block, other_block])

        file_info_other = MagicMock()
        file_info_other.key = "main-project:src/old.py"

        response = MagicMock(spec=DuplicationsResponse)
        response.duplications = [group]
        response.get_target_file_ref.return_value = "1"
        response.get_file_info.return_value = file_info_other
        return response

    @pytest.mark.asyncio
    async def test_resolved_duplication_detected(self, orchestrator) -> None:
        """A main-project block overlapping old changed lines and not in active ranges produces a warning."""
        response = self._make_response(from_line=45, size=16)  # main block lines 45-60

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.return_value = response

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_resolved_duplications(
                Path("src/file.py"),
                changed_lines_map={"src/file.py": {50}},  # new changed lines (anchor)
                old_changed_lines_map={"src/file.py": {50}},  # old lines inside the block
                active_dup_ranges=set(),  # no active dups
                original_project_key="main-project",
                diag=diag,
            )

        assert len(result) == 1
        assert result[0].main_from_line == 45
        assert result[0].main_to_line == 60
        assert result[0].anchor_new_line == 50
        assert result[0].other_locations[0].file_path == "src/old.py"
        assert diag.resolved_dup_api_status == "ok"
        assert diag.resolved_dup_groups_found == 1

    @pytest.mark.asyncio
    async def test_skipped_when_covered_by_active_dup(self, orchestrator) -> None:
        """A resolved duplication block is skipped if Feature 1 already found it active."""
        response = self._make_response(from_line=45, size=16)

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.return_value = response

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_resolved_duplications(
                Path("src/file.py"),
                changed_lines_map={"src/file.py": {50}},
                old_changed_lines_map={"src/file.py": {50}},
                active_dup_ranges={(45, 60)},  # covered by Feature 1
                original_project_key="main-project",
                diag=diag,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_no_old_changed_lines_returns_empty(self, orchestrator) -> None:
        """When file has no old changed lines, returns empty without API call."""
        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            diag = self._make_diag()
            result = await orchestrator._get_resolved_duplications(
                Path("src/file.py"),
                changed_lines_map={},
                old_changed_lines_map={},
                active_dup_ranges=set(),
                original_project_key="main-project",
                diag=diag,
            )

        MockDupClient.assert_not_called()
        assert result == []
        assert diag.resolved_dup_api_status == "skipped_no_changed_lines"

    @pytest.mark.asyncio
    async def test_silent_skip_on_component_not_found(self, orchestrator) -> None:
        """ComponentNotFoundError on main project query is recorded in diagnostics."""
        from vibe_heal.sonarqube.exceptions import ComponentNotFoundError

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.side_effect = ComponentNotFoundError("not found")

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            diag = self._make_diag()
            result = await orchestrator._get_resolved_duplications(
                Path("src/file.py"),
                changed_lines_map={"src/file.py": {50}},
                old_changed_lines_map={"src/file.py": {50}},
                active_dup_ranges=set(),
                original_project_key="main-project",
                diag=diag,
            )

        assert result == []
        assert diag.resolved_dup_api_status == "component_not_found"

    @pytest.mark.asyncio
    async def test_project_key_restored_after_query(self, orchestrator) -> None:
        """Config is restored to temp project key after querying main project."""
        orchestrator.config.sonarqube_project_key = "temp-project"

        response = MagicMock()
        response.duplications = []

        mock_dup_instance = AsyncMock()
        mock_dup_instance.get_duplications_for_file.return_value = response

        with patch("vibe_heal.review.orchestrator.DuplicationClient") as MockDupClient:
            MockDupClient.return_value.__aenter__ = AsyncMock(return_value=mock_dup_instance)
            MockDupClient.return_value.__aexit__ = AsyncMock(return_value=None)

            await orchestrator._get_resolved_duplications(
                Path("src/file.py"),
                changed_lines_map={"src/file.py": {50}},
                old_changed_lines_map={"src/file.py": {50}},
                active_dup_ranges=set(),
                original_project_key="main-project",
                diag=self._make_diag(),
            )

        assert orchestrator.config.sonarqube_project_key == "temp-project"
