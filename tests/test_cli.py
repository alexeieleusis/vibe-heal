"""Tests for CLI commands."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.cleanup.orchestrator import CleanupResult, FileCleanupResult
from vibe_heal.cli import app
from vibe_heal.config import VibeHealConfig
from vibe_heal.models import FixSummary

runner = CliRunner()


class TestFixCommand:
    """Tests for fix command."""

    @patch("vibe_heal.cli.initialize_ai_tool")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.VibeHealOrchestrator")
    def test_fix_basic(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_init_ai_tool: MagicMock,
    ) -> None:
        """Test basic fix command."""
        # Setup mocks
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config_class.return_value = mock_config

        mock_ai_tool = MagicMock()
        mock_init_ai_tool.return_value = mock_ai_tool

        mock_orchestrator = MagicMock()
        mock_orchestrator.fix_file = AsyncMock(
            return_value=FixSummary(
                total_issues=5,
                fixed=3,
                failed=0,
                skipped=2,
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command
        result = runner.invoke(app, ["fix", "test.py"])

        # Assertions
        assert result.exit_code == 0
        mock_init_ai_tool.assert_called_once_with(mock_config)
        mock_orchestrator_class.assert_called_once_with(mock_config, mock_ai_tool)
        mock_orchestrator.fix_file.assert_called_once()
        call_kwargs = mock_orchestrator.fix_file.call_args.kwargs
        assert call_kwargs["file_path"] == "test.py"
        assert call_kwargs["dry_run"] is False

    @patch("vibe_heal.cli.initialize_ai_tool")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.VibeHealOrchestrator")
    def test_fix_with_options(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_init_ai_tool: MagicMock,
    ) -> None:
        """Test fix command with all options."""
        # Setup mocks
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config_class.return_value = mock_config

        mock_ai_tool = MagicMock()
        mock_init_ai_tool.return_value = mock_ai_tool

        mock_orchestrator = MagicMock()
        mock_orchestrator.fix_file = AsyncMock(return_value=FixSummary(total_issues=1, fixed=1))
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command with options
        result = runner.invoke(
            app,
            [
                "fix",
                "test.py",
                "--dry-run",
                "--max-issues",
                "5",
                "--min-severity",
                "MAJOR",
                "--ai-tool",
                "claude-code",
                "--verbose",
            ],
        )

        # Assertions
        assert result.exit_code == 0
        call_kwargs = mock_orchestrator.fix_file.call_args.kwargs
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["max_issues"] == 5
        assert call_kwargs["min_severity"] == "MAJOR"
        assert mock_config.ai_tool == AIToolType.CLAUDE_CODE

    @patch("vibe_heal.cli.initialize_ai_tool")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.VibeHealOrchestrator")
    def test_fix_with_failures(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_init_ai_tool: MagicMock,
    ) -> None:
        """Test fix command exits with error when there are failures."""
        # Setup mocks
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config_class.return_value = mock_config

        mock_ai_tool = MagicMock()
        mock_init_ai_tool.return_value = mock_ai_tool

        mock_orchestrator = MagicMock()
        mock_orchestrator.fix_file = AsyncMock(
            return_value=FixSummary(
                total_issues=5,
                fixed=2,
                failed=3,
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command
        result = runner.invoke(app, ["fix", "test.py"])

        # Should exit with error code 1
        assert result.exit_code == 1


class TestCleanupCommand:
    """Tests for cleanup command."""

    @patch("vibe_heal.cli.SonarQubeClient")
    @patch("vibe_heal.cli.AIToolFactory")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.CleanupOrchestrator")
    def test_cleanup_basic(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_ai_factory: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """Test basic cleanup command."""
        # Setup config mock
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config.ai_tool = None
        mock_config_class.return_value = mock_config

        # Setup AI tool mock
        mock_ai_tool = MagicMock()
        mock_ai_tool.is_available.return_value = True
        mock_ai_factory.detect_available.return_value = AIToolType.CLAUDE_CODE
        mock_ai_factory.create.return_value = mock_ai_tool

        # Setup client mock
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Setup orchestrator mock
        mock_orchestrator = MagicMock()
        mock_orchestrator.cleanup_branch = AsyncMock(
            return_value=CleanupResult(
                success=True,
                files_processed=[
                    FileCleanupResult(
                        file_path=Path("src/file1.py"),
                        issues_fixed=3,
                        success=True,
                    ),
                ],
                total_issues_fixed=3,
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command
        result = runner.invoke(app, ["cleanup"])

        # Assertions
        assert result.exit_code == 0
        assert "Branch cleanup complete" in result.stdout
        mock_orchestrator.cleanup_branch.assert_called_once()
        call_kwargs = mock_orchestrator.cleanup_branch.call_args.kwargs
        assert call_kwargs["base_branch"] == "origin/main"
        assert call_kwargs["max_iterations"] == 10
        assert call_kwargs["file_patterns"] is None

    @patch("vibe_heal.cli.SonarQubeClient")
    @patch("vibe_heal.cli.AIToolFactory")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.CleanupOrchestrator")
    def test_cleanup_with_options(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_ai_factory: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """Test cleanup command with all options."""
        # Setup config mock
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config.ai_tool = None
        mock_config_class.return_value = mock_config

        # Setup AI tool mock
        mock_ai_tool = MagicMock()
        mock_ai_tool.is_available.return_value = True
        mock_ai_factory.detect_available.return_value = AIToolType.CLAUDE_CODE
        mock_ai_factory.create.return_value = mock_ai_tool

        # Setup client mock
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Setup orchestrator mock
        mock_orchestrator = MagicMock()
        mock_orchestrator.cleanup_branch = AsyncMock(
            return_value=CleanupResult(
                success=True,
                files_processed=[],
                total_issues_fixed=0,
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command with options
        result = runner.invoke(
            app,
            [
                "cleanup",
                "--base-branch",
                "develop",
                "--max-iterations",
                "5",
                "--pattern",
                "*.py",
                "--pattern",
                "*.ts",
                "--ai-tool",
                "claude-code",
                "--verbose",
            ],
        )

        # Assertions
        assert result.exit_code == 0
        call_kwargs = mock_orchestrator.cleanup_branch.call_args.kwargs
        assert call_kwargs["base_branch"] == "develop"
        assert call_kwargs["max_iterations"] == 5
        assert call_kwargs["file_patterns"] == ["*.py", "*.ts"]
        assert mock_config.ai_tool == AIToolType.CLAUDE_CODE

    @patch("vibe_heal.cli.SonarQubeClient")
    @patch("vibe_heal.cli.AIToolFactory")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.CleanupOrchestrator")
    def test_cleanup_with_failures(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_ai_factory: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """Test cleanup command exits with error when cleanup fails."""
        # Setup config mock
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config.ai_tool = None
        mock_config_class.return_value = mock_config

        # Setup AI tool mock
        mock_ai_tool = MagicMock()
        mock_ai_tool.is_available.return_value = True
        mock_ai_factory.detect_available.return_value = AIToolType.CLAUDE_CODE
        mock_ai_factory.create.return_value = mock_ai_tool

        # Setup client mock
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Setup orchestrator mock
        mock_orchestrator = MagicMock()
        mock_orchestrator.cleanup_branch = AsyncMock(
            return_value=CleanupResult(
                success=False,
                files_processed=[],
                error_message="Analysis failed",
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command
        result = runner.invoke(app, ["cleanup"])

        # Should exit with error code 1
        assert result.exit_code == 1
        assert "Cleanup failed" in result.stdout

    @patch("vibe_heal.cli.SonarQubeClient")
    @patch("vibe_heal.cli.AIToolFactory")
    @patch("vibe_heal.cli.VibeHealConfig")
    def test_cleanup_no_ai_tool_available(
        self,
        mock_config_class: MagicMock,
        mock_ai_factory: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """Test cleanup command fails when no AI tool is available."""
        # Setup config mock
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config.ai_tool = None
        mock_config_class.return_value = mock_config

        # Setup AI tool mock - no tool detected
        mock_ai_factory.detect_available.return_value = None

        # Run command
        result = runner.invoke(app, ["cleanup"])

        # Should exit with error code 1
        assert result.exit_code == 1
        assert "No AI tool found" in result.stdout

    @patch("vibe_heal.cli.SonarQubeClient")
    @patch("vibe_heal.cli.AIToolFactory")
    @patch("vibe_heal.cli.VibeHealConfig")
    @patch("vibe_heal.cli.CleanupOrchestrator")
    def test_cleanup_displays_file_results(
        self,
        mock_orchestrator_class: MagicMock,
        mock_config_class: MagicMock,
        mock_ai_factory: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """Test cleanup command displays per-file results."""
        # Setup config mock
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config.ai_tool = AIToolType.CLAUDE_CODE
        mock_config_class.return_value = mock_config

        # Setup AI tool mock
        mock_ai_tool = MagicMock()
        mock_ai_tool.is_available.return_value = True
        mock_ai_factory.create.return_value = mock_ai_tool

        # Setup client mock
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Setup orchestrator mock with multiple files
        mock_orchestrator = MagicMock()
        mock_orchestrator.cleanup_branch = AsyncMock(
            return_value=CleanupResult(
                success=True,
                files_processed=[
                    FileCleanupResult(
                        file_path=Path("src/file1.py"),
                        issues_fixed=3,
                        success=True,
                    ),
                    FileCleanupResult(
                        file_path=Path("src/file2.py"),
                        issues_fixed=0,
                        success=True,
                    ),
                    FileCleanupResult(
                        file_path=Path("src/file3.py"),
                        issues_fixed=5,
                        success=False,
                        error_message="Fix failed",
                    ),
                ],
                total_issues_fixed=8,
            )
        )
        mock_orchestrator_class.return_value = mock_orchestrator

        # Run command
        result = runner.invoke(app, ["cleanup"])

        # Assertions
        assert result.exit_code == 0
        assert "Files processed: 3" in result.stdout
        assert "Total issues fixed: 8" in result.stdout
        assert "src/file1.py: 3 issues fixed" in result.stdout
        assert "src/file2.py: 0 issues fixed" in result.stdout
        assert "src/file3.py: 5 issues fixed" in result.stdout
        assert "Error: Fix failed" in result.stdout


class TestConfigCommand:
    """Tests for config command."""

    @patch("vibe_heal.cli.VibeHealConfig")
    def test_config_display(self, mock_config_class: MagicMock) -> None:
        """Test config command displays configuration."""
        mock_config = MagicMock(spec=VibeHealConfig)
        mock_config.sonarqube_url = "https://sonar.example.com"
        mock_config.sonarqube_project_key = "test-project"
        mock_config.use_token_auth = True
        mock_config.ai_tool = AIToolType.CLAUDE_CODE
        mock_config.code_context_lines = 5
        mock_config.include_rule_description = True
        mock_config_class.return_value = mock_config

        result = runner.invoke(app, ["config"])

        assert result.exit_code == 0
        assert "https://sonar.example.com" in result.stdout
        assert "test-project" in result.stdout
        assert "Token" in result.stdout
        assert "Claude Code" in result.stdout


class TestVersionCommand:
    """Tests for version command."""

    def test_version_display(self) -> None:
        """Test version command displays version."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "vibe-heal version" in result.stdout
