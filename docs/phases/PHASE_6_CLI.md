# Phase 6: CLI and Orchestration ✅ COMPLETE

## Objective

Build the command-line interface and orchestrator to wire all components together into a working end-to-end system.

## Status: ✅ COMPLETE

All CLI and orchestration features implemented and tested:
- [x] `FixSummary` model with success rate calculation
- [x] `VibeHealOrchestrator` with complete workflow orchestration
- [x] CLI with `fix`, `config`, and `version` commands
- [x] Entry point for `python -m vibe_heal` and `vibe-heal` command
- [x] Rich progress indicators and beautiful output
- [x] User confirmation prompts for safety
- [x] Dry-run mode for testing without committing
- [x] Comprehensive error handling and display
- [x] Logging setup with Rich integration
- [x] AI tool auto-detection and configuration
- [x] Full workflow integration: fetch → process → fix → commit
- [x] Test coverage: 20 tests for orchestrator and models

**Test Results**: 20 tests for CLI/orchestrator modules
**Overall Progress**: 141 tests passing, 82% code coverage

**Implementation Notes**:
- Rich library provides colorful, user-friendly CLI output
- Typer simplifies CLI development with type hints
- Orchestrator validates all preconditions before processing
- User must confirm before fixes are applied (unless dry-run)
- Each fix creates its own Git commit for easy rollback
- Progress indicators show real-time status during fixing
- Comprehensive error handling with helpful messages

## Dependencies

- Phases 0-5 must be complete
- `typer` and `rich` installed
- All core components available

## Files to Create/Modify

```
src/vibe_heal/
├── __main__.py                  # Entry point for `python -m vibe_heal`
├── cli.py                       # CLI commands
├── orchestrator.py              # Main workflow orchestration
└── models.py                    # Top-level models (FixSummary)
tests/
├── test_orchestrator.py         # Orchestrator tests
└── test_cli.py                  # CLI tests (optional, can be manual)
```

## Tasks

### 1. Create Top-Level Models

**File**: `src/vibe_heal/models.py`

```python
from pydantic import BaseModel, Field


class FixSummary(BaseModel):
    """Summary of fix operation."""

    total_issues: int = Field(description="Total issues found")
    fixed: int = Field(default=0, description="Number of issues fixed")
    failed: int = Field(default=0, description="Number of fixes that failed")
    skipped: int = Field(default=0, description="Number of issues skipped")
    commits: list[str] = Field(default_factory=list, description="List of commit SHAs")

    @property
    def success_rate(self) -> float:
        """Calculate success rate (fixed / attempted)."""
        attempted = self.fixed + self.failed
        if attempted == 0:
            return 0.0
        return (self.fixed / attempted) * 100

    @property
    def has_failures(self) -> bool:
        """Check if any fixes failed."""
        return self.failed > 0
```

### 2. Create Orchestrator

**File**: `src/vibe_heal/orchestrator.py`

```python
import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from vibe_heal.ai_tools import AIToolFactory
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.config import VibeHealConfig
from vibe_heal.git import GitManager
from vibe_heal.models import FixSummary
from vibe_heal.processor import IssueProcessor
from vibe_heal.sonarqube import SonarQubeClient

logger = logging.getLogger(__name__)


class VibeHealOrchestrator:
    """Orchestrates the fix workflow."""

    def __init__(self, config: VibeHealConfig):
        """Initialize orchestrator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.console = Console()
        self.git_manager = GitManager()
        self.ai_tool = self._initialize_ai_tool()

    def _initialize_ai_tool(self) -> AITool:
        """Initialize AI tool based on config or auto-detect.

        Returns:
            Initialized AI tool

        Raises:
            RuntimeError: If no AI tool is available
        """
        if self.config.ai_tool:
            tool_type = self.config.ai_tool
            self.console.print(
                f"[blue]Using configured AI tool: {tool_type.display_name}[/blue]"
            )
        else:
            tool_type = AIToolFactory.detect_available()
            if not tool_type:
                raise RuntimeError(
                    "No AI tool found. Please install Claude Code or Aider."
                )
            self.console.print(
                f"[blue]Auto-detected AI tool: {tool_type.display_name}[/blue]"
            )

        return AIToolFactory.create(tool_type)

    async def fix_file(
        self,
        file_path: str,
        dry_run: bool = False,
        max_issues: int | None = None,
        min_severity: str | None = None,
    ) -> FixSummary:
        """Fix SonarQube issues in a file.

        Args:
            file_path: Path to file to fix
            dry_run: If True, don't commit changes
            max_issues: Maximum number of issues to fix
            min_severity: Minimum severity to process

        Returns:
            Summary of fixes

        Raises:
            Various exceptions for validation errors
        """
        # Step 1: Validate preconditions
        self._validate_preconditions(file_path, dry_run)

        # Step 2: Fetch issues from SonarQube
        self.console.print(f"\n[yellow]Fetching issues for {file_path}...[/yellow]")
        async with SonarQubeClient(self.config) as sonar_client:
            issues = await sonar_client.get_issues_for_file(file_path)

        if not issues:
            self.console.print("[green]No issues found![/green]")
            return FixSummary(total_issues=0)

        # Step 3: Process issues (filter and sort)
        processor = IssueProcessor(
            min_severity=min_severity,
            max_issues=max_issues,
        )
        result = processor.process(issues)

        self.console.print(
            f"[cyan]Found {result.total_issues} total issues, "
            f"{result.fixable_issues} fixable, "
            f"processing {len(result.issues_to_fix)}[/cyan]\n"
        )

        if not result.has_issues:
            self.console.print("[yellow]No fixable issues to process[/yellow]")
            return FixSummary(
                total_issues=result.total_issues,
                skipped=result.skipped_issues,
            )

        # Step 4: Confirm with user
        if not dry_run:
            if not self._confirm_processing(len(result.issues_to_fix)):
                self.console.print("[yellow]Cancelled by user[/yellow]")
                return FixSummary(
                    total_issues=result.total_issues,
                    skipped=len(result.issues_to_fix),
                )

        # Step 5: Process each issue
        summary = await self._process_issues(
            result.issues_to_fix,
            file_path,
            dry_run,
        )
        summary.total_issues = result.total_issues
        summary.skipped = result.skipped_issues

        # Step 6: Display summary
        self._display_summary(summary, dry_run)

        return summary

    def _validate_preconditions(self, file_path: str, dry_run: bool) -> None:
        """Validate preconditions before fixing.

        Args:
            file_path: Path to file
            dry_run: Whether in dry-run mode

        Raises:
            Various exceptions for validation failures
        """
        # Check Git repository
        if not self.git_manager.is_repository():
            raise RuntimeError("Not a Git repository")

        # Check clean working directory (unless dry-run)
        if not dry_run:
            self.git_manager.require_clean_working_directory()

        # Check file exists
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check AI tool is available
        if not self.ai_tool.is_available():
            raise RuntimeError(
                f"{self.ai_tool.tool_type.display_name} is not available"
            )

    def _confirm_processing(self, issue_count: int) -> bool:
        """Ask user to confirm processing.

        Args:
            issue_count: Number of issues to process

        Returns:
            True if user confirms
        """
        self.console.print(
            f"\n[bold yellow]About to process {issue_count} issue(s).[/bold yellow]"
        )
        self.console.print(
            "[yellow]Each fix will be committed separately.[/yellow]"
        )

        response = input("Continue? [y/N]: ").strip().lower()
        return response in ["y", "yes"]

    async def _process_issues(
        self,
        issues: list,
        file_path: str,
        dry_run: bool,
    ) -> FixSummary:
        """Process each issue.

        Args:
            issues: List of issues to process
            file_path: Path to file
            dry_run: Whether in dry-run mode

        Returns:
            Fix summary
        """
        summary = FixSummary(total_issues=0)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:

            for idx, issue in enumerate(issues, 1):
                task = progress.add_task(
                    f"[cyan]Fixing issue {idx}/{len(issues)} "
                    f"(line {issue.line}): {issue.message[:50]}...",
                    total=None,
                )

                # Attempt to fix
                fix_result = await self.ai_tool.fix_issue(issue, file_path)

                if fix_result.success:
                    # Commit if not dry-run
                    if not dry_run:
                        try:
                            sha = self.git_manager.commit_fix(
                                issue,
                                fix_result.files_modified,
                                self.ai_tool.tool_type,
                            )
                            summary.commits.append(sha)
                            summary.fixed += 1
                            progress.update(
                                task,
                                description=f"[green]✓ Fixed line {issue.line}[/green]",
                            )
                        except Exception as e:
                            logger.error(f"Failed to commit: {e}")
                            summary.failed += 1
                            progress.update(
                                task,
                                description=f"[red]✗ Commit failed: {e}[/red]",
                            )
                    else:
                        summary.fixed += 1
                        progress.update(
                            task,
                            description=f"[green]✓ Would fix line {issue.line} "
                            f"(dry-run)[/green]",
                        )
                else:
                    summary.failed += 1
                    error = fix_result.error_message or "Unknown error"
                    progress.update(
                        task,
                        description=f"[red]✗ Failed: {error[:50]}[/red]",
                    )
                    logger.error(
                        f"Failed to fix issue {issue.key}: {fix_result.error_message}"
                    )

        return summary

    def _display_summary(self, summary: FixSummary, dry_run: bool) -> None:
        """Display fix summary.

        Args:
            summary: Fix summary
            dry_run: Whether in dry-run mode
        """
        self.console.print("\n[bold]Summary:[/bold]")
        self.console.print(f"  Total issues: {summary.total_issues}")
        self.console.print(f"  [green]Fixed: {summary.fixed}[/green]")
        self.console.print(f"  [red]Failed: {summary.failed}[/red]")
        self.console.print(f"  [yellow]Skipped: {summary.skipped}[/yellow]")

        if summary.fixed > 0:
            self.console.print(
                f"  Success rate: {summary.success_rate:.1f}%"
            )

        if not dry_run and summary.commits:
            self.console.print(f"\n[bold]Created {len(summary.commits)} commit(s)[/bold]")

        if dry_run:
            self.console.print("\n[yellow]Dry-run mode: no changes committed[/yellow]")
```

### 3. Create CLI

**File**: `src/vibe_heal/cli.py`

```python
import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.logging import RichHandler

from vibe_heal import __version__
from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.config import VibeHealConfig, ConfigurationError
from vibe_heal.orchestrator import VibeHealOrchestrator

app = typer.Typer(
    name="vibe-heal",
    help="AI-powered SonarQube issue remediation tool",
    add_completion=False,
)
console = Console()


def setup_logging(verbose: bool) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@app.command()
def fix(
    file_path: str = typer.Argument(..., help="Path to file to fix"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview fixes without committing"
    ),
    max_issues: int | None = typer.Option(
        None,
        "--max-issues",
        "-n",
        help="Maximum number of issues to fix"
    ),
    min_severity: str | None = typer.Option(
        None,
        "--min-severity",
        help="Minimum severity (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)"
    ),
    ai_tool: AIToolType | None = typer.Option(
        None,
        "--ai-tool",
        help="AI tool to use (overrides config)"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output"
    ),
) -> None:
    """Fix SonarQube issues in a file."""
    setup_logging(verbose)

    try:
        # Load configuration
        config = VibeHealConfig()

        # Override AI tool if specified
        if ai_tool:
            config.ai_tool = ai_tool

        # Create orchestrator
        orchestrator = VibeHealOrchestrator(config)

        # Run fix
        summary = asyncio.run(
            orchestrator.fix_file(
                file_path=file_path,
                dry_run=dry_run,
                max_issues=max_issues,
                min_severity=min_severity,
            )
        )

        # Exit with error if there were failures
        if summary.has_failures:
            sys.exit(1)

    except ConfigurationError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


@app.command()
def config() -> None:
    """Show current configuration."""
    try:
        cfg = VibeHealConfig()
        console.print("[bold]Current Configuration:[/bold]\n")
        console.print(f"  SonarQube URL: {cfg.sonarqube_url}")
        console.print(f"  Project Key: {cfg.sonarqube_project_key}")
        console.print(f"  Auth Method: {'Token' if cfg.use_token_auth else 'Basic'}")
        if cfg.ai_tool:
            console.print(f"  AI Tool: {cfg.ai_tool.display_name}")
        else:
            console.print("  AI Tool: Auto-detect")
    except ConfigurationError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"vibe-heal version {__version__}")


if __name__ == "__main__":
    app()
```

### 4. Create Entry Point

**File**: `src/vibe_heal/__main__.py`

```python
"""Entry point for python -m vibe_heal."""
from vibe_heal.cli import app

if __name__ == "__main__":
    app()
```

**Update** `src/vibe_heal/__init__.py`:
```python
"""vibe-heal: AI-powered SonarQube issue remediation."""

__version__ = "0.0.1"

__all__ = ["__version__"]
```

### 5. Update pyproject.toml

Add CLI entry point to `pyproject.toml`:

```toml
[project.scripts]
vibe-heal = "vibe_heal.cli:app"
```

### 6. Write Tests

**File**: `tests/test_orchestrator.py`
- Test `_initialize_ai_tool` (with config, with auto-detect)
- Test `_validate_preconditions` (various error cases)
- Test `fix_file` end-to-end (mocked components)

**Note**: CLI testing can be manual for Phase 6.

## Example Usage

```bash
# Show configuration
vibe-heal config

# Fix a file (dry-run)
vibe-heal fix src/main.py --dry-run

# Fix a file (with confirmation)
vibe-heal fix src/main.py

# Fix with limits
vibe-heal fix src/main.py --max-issues 5 --min-severity MAJOR

# Force specific AI tool
vibe-heal fix src/main.py --ai-tool claude-code

# Verbose output
vibe-heal fix src/main.py --verbose
```

## Verification Steps

1. Install in development mode:
   ```bash
   uv pip install -e .
   ```

2. Test CLI commands:
   ```bash
   vibe-heal --help
   vibe-heal version
   vibe-heal config
   ```

3. End-to-end test (requires SonarQube setup):
   ```bash
   # Create .env.vibeheal with config
   vibe-heal fix path/to/file.py --dry-run
   ```

4. Run tests:
   ```bash
   uv run pytest tests/test_orchestrator.py -v
   ```

## Definition of Done

- ✅ `FixSummary` model
- ✅ `VibeHealOrchestrator` with full workflow
- ✅ CLI with `fix`, `config`, and `version` commands
- ✅ Entry point configured
- ✅ Progress indicators with rich
- ✅ User confirmation prompt
- ✅ Dry-run mode
- ✅ Error handling and display
- ✅ Logging setup
- ✅ Can run end-to-end: fetch → process → fix → commit
- ✅ Tests for orchestrator

## Notes

- Rich library provides beautiful CLI output
- Typer makes CLI development simple
- The orchestrator coordinates all components
- User confirmation prevents accidental mass-changes
- Dry-run mode is essential for testing
- Each phase of the workflow is validated before proceeding
- Verbose mode helps with debugging
