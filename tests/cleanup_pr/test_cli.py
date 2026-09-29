"""Tests for the cleanup-pr CLI command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.cleanup_pr.orchestrator import CleanupPrResult, FileCleanupPrResult
from vibe_heal.cli import app
from vibe_heal.config import ConfigurationError, VibeHealConfig

runner = CliRunner()


def _ok_result() -> CleanupPrResult:
    return CleanupPrResult(
        success=True,
        files_processed=[
            FileCleanupPrResult(
                file_path=Path("src/file1.py"),
                issues_fixed=3,
                issues_out_of_scope=2,
                duplications_fixed=1,
                duplications_out_of_scope=4,
                success=True,
            ),
        ],
        total_issues_fixed=3,
        total_duplications_fixed=1,
    )


@pytest.fixture
def mocks() -> object:
    """Patch the collaborators of the cleanup-pr command; yield (orchestrator, config_class)."""
    with (
        patch("vibe_heal.cli.SonarQubeClient") as client_class,
        patch("vibe_heal.cli.AIToolFactory") as ai_factory,
        patch("vibe_heal.cli.VibeHealConfig") as config_class,
        patch("vibe_heal.cli.CleanupPrOrchestrator") as orchestrator_class,
    ):
        config = MagicMock(spec=VibeHealConfig)
        config.ai_tool = None
        config_class.return_value = config

        ai_tool = MagicMock()
        ai_tool.is_available.return_value = True
        ai_factory.detect_available.return_value = AIToolType.CLAUDE_CODE
        ai_factory.create.return_value = ai_tool

        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client_class.return_value = client

        orchestrator = MagicMock()
        orchestrator.cleanup_pr = AsyncMock(return_value=_ok_result())
        orchestrator_class.return_value = orchestrator
        yield orchestrator, config_class


class TestCleanupPrCommand:
    def test_defaults_and_summary(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        orchestrator, _ = mocks
        result = runner.invoke(app, ["cleanup-pr"])

        assert result.exit_code == 0
        assert "Branch cleanup (PR scope) complete" in result.stdout
        assert "Total issues fixed: 3" in result.stdout
        assert "Total duplications fixed: 1" in result.stdout
        assert "2 out of scope" in result.stdout
        assert "4 out of scope" in result.stdout
        kwargs = orchestrator.cleanup_pr.call_args.kwargs
        assert kwargs["base_branch"] == "origin/main"
        assert kwargs["max_iterations"] == 10
        assert kwargs["file_patterns"] is None
        assert kwargs["min_severity"] is None
        assert kwargs["dry_run"] is False
        assert kwargs["include_main_duplications"] is False

    def test_all_options(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        orchestrator, config_class = mocks
        result = runner.invoke(
            app,
            [
                "cleanup-pr",
                "-b",
                "origin/develop",
                "-i",
                "3",
                "-p",
                "*.py",
                "-p",
                "src/**/*.ts",
                "--min-severity",
                "MAJOR",
                "--dry-run",
                "--ai-tool",
                "aider",
                "--env-file",
                ".env.x",
            ],
        )

        assert result.exit_code == 0
        config_class.assert_called_once_with(env_file=".env.x")
        kwargs = orchestrator.cleanup_pr.call_args.kwargs
        assert kwargs["base_branch"] == "origin/develop"
        assert kwargs["max_iterations"] == 3
        assert kwargs["file_patterns"] == ["*.py", "src/**/*.ts"]
        assert kwargs["min_severity"] == "MAJOR"
        assert kwargs["dry_run"] is True
        assert "Dry run" in result.stdout

    def test_configuration_error_exits_1(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        _, config_class = mocks
        config_class.side_effect = ConfigurationError("bad config")

        result = runner.invoke(app, ["cleanup-pr"])

        assert result.exit_code == 1
        assert "Configuration error: bad config" in result.stdout

    def test_generic_error_exits_1(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        orchestrator, _ = mocks
        orchestrator.cleanup_pr.side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["cleanup-pr"])

        assert result.exit_code == 1
        assert "Error: boom" in result.stdout
        assert "Traceback" not in result.stdout

    def test_generic_error_verbose_prints_traceback(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        orchestrator, _ = mocks
        orchestrator.cleanup_pr.side_effect = RuntimeError("boom")

        result = runner.invoke(app, ["cleanup-pr", "--verbose"])

        assert result.exit_code == 1
        assert "Error: boom" in result.stdout
        assert "Traceback" in result.stdout

    def test_failed_result_exits_1_after_table(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        orchestrator, _ = mocks
        orchestrator.cleanup_pr.return_value = CleanupPrResult(
            success=False,
            files_processed=[
                FileCleanupPrResult(
                    file_path=Path("src/bad.py"),
                    success=False,
                    error_message="fix blew up",
                ),
            ],
            error_message="Analysis failed at iteration 2: nope",
        )

        result = runner.invoke(app, ["cleanup-pr"])

        assert result.exit_code == 1
        assert "src/bad.py" in result.stdout
        assert "fix blew up" in result.stdout
        assert "Cleanup failed: Analysis failed at iteration 2: nope" in result.stdout
        assert "complete!" not in result.stdout

    def test_include_main_duplications_rejected(self, mocks: tuple[MagicMock, MagicMock]) -> None:
        orchestrator, _ = mocks
        result = runner.invoke(app, ["cleanup-pr", "--include-main-duplications"])

        assert result.exit_code == 2
        orchestrator.cleanup_pr.assert_not_called()
