# Phase 7: Safety and Polish

## Objective

Add safety features, improve error handling, and polish the user experience.

## Dependencies

- Phase 6 must be complete
- End-to-end workflow functional

## Files to Modify

```
src/vibe_heal/
├── cli.py                       # Add safety prompts
├── orchestrator.py              # Improve error handling
└── utils/
    ├── validators.py            # File and path validation
    └── logging.py               # Better logging setup
tests/
└── utils/
    └── test_validators.py       # Validator tests
```

## Tasks

### 1. Create Validation Utilities

**File**: `src/vibe_heal/utils/validators.py`

```python
from pathlib import Path


class FileValidator:
    """Validates file paths and related checks."""

    @staticmethod
    def validate_file_exists(file_path: str | Path) -> Path:
        """Validate that file exists.

        Args:
            file_path: Path to file

        Returns:
            Validated Path object

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")
        return path

    @staticmethod
    def validate_file_in_project(
        file_path: str | Path,
        project_root: str | Path
    ) -> bool:
        """Check if file is within project directory.

        Args:
            file_path: Path to file
            project_root: Project root directory

        Returns:
            True if file is in project

        Raises:
            ValueError: If file is outside project
        """
        file_abs = Path(file_path).resolve()
        root_abs = Path(project_root).resolve()

        try:
            file_abs.relative_to(root_abs)
            return True
        except ValueError as e:
            raise ValueError(
                f"File {file_path} is outside project root {project_root}"
            ) from e

    @staticmethod
    def is_supported_file_type(file_path: str | Path) -> bool:
        """Check if file type is likely to be fixable.

        Args:
            file_path: Path to file

        Returns:
            True if file type is supported
        """
        # For now, accept any text file
        # Later can restrict to specific extensions
        path = Path(file_path)

        # Exclude binary/generated files
        excluded_extensions = {
            '.pyc', '.pyo', '.so', '.dylib', '.dll',
            '.class', '.jar', '.war',
            '.exe', '.bin',
            '.jpg', '.jpeg', '.png', '.gif', '.pdf',
            '.zip', '.tar', '.gz',
        }

        return path.suffix.lower() not in excluded_extensions
```

### 2. Improve Logging

**File**: `src/vibe_heal/utils/logging.py`

```python
import logging
import sys
from pathlib import Path

from rich.logging import RichHandler


def setup_logging(
    verbose: bool = False,
    log_file: str | Path | None = None
) -> None:
    """Setup logging configuration.

    Args:
        verbose: Enable debug logging
        log_file: Optional log file path
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    handlers: list[logging.Handler] = [
        RichHandler(
            rich_tracebacks=True,
            show_time=verbose,
            show_path=verbose,
        )
    ]

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=handlers,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("git").setLevel(logging.WARNING)
```

### 3. Enhance Orchestrator with Safety Features

**File**: `src/vibe_heal/orchestrator.py` (additions)

Add these improvements to the existing orchestrator:

```python
# Add to imports
from vibe_heal.utils.validators import FileValidator

# Add to _validate_preconditions method
def _validate_preconditions(self, file_path: str, dry_run: bool) -> None:
    """Validate preconditions before fixing."""
    # ... existing checks ...

    # Validate file
    file_path_obj = FileValidator.validate_file_exists(file_path)

    # Check file type
    if not FileValidator.is_supported_file_type(file_path_obj):
        self.console.print(
            f"[yellow]Warning: {file_path} may not be a supported file type[/yellow]"
        )

    # Check file is in project (prevent accidental fixes outside repo)
    try:
        FileValidator.validate_file_in_project(
            file_path_obj,
            self.git_manager.repo.working_dir
        )
    except ValueError as e:
        raise RuntimeError(str(e)) from e

# Add method for rollback guidance
def _show_rollback_instructions(self, commits: list[str]) -> None:
    """Show how to rollback changes.

    Args:
        commits: List of commit SHAs
    """
    if not commits:
        return

    self.console.print("\n[bold yellow]Rollback Instructions:[/bold yellow]")
    self.console.print(
        f"  To undo all {len(commits)} fix commit(s), run:"
    )
    self.console.print(f"    git reset --hard HEAD~{len(commits)}")
    self.console.print("\n  To undo specific commits:")
    for sha in commits[:5]:  # Show first 5
        self.console.print(f"    git revert {sha[:8]}")
    if len(commits) > 5:
        self.console.print(f"    ... and {len(commits) - 5} more")
```

### 4. Enhance CLI with Safety Features

**File**: `src/vibe_heal/cli.py` (additions)

```python
# Add to fix command
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
    log_file: str | None = typer.Option(
        None,
        "--log-file",
        help="Write logs to file"
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompts"
    ),
) -> None:
    """Fix SonarQube issues in a file."""
    from vibe_heal.utils.logging import setup_logging

    setup_logging(verbose, log_file)

    try:
        # ... existing code ...

        # Pass yes flag to orchestrator
        orchestrator._skip_confirmation = yes

        # ... rest of existing code ...

        # Show rollback instructions if commits were made
        if summary.commits and not dry_run:
            orchestrator._show_rollback_instructions(summary.commits)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    # ... rest of existing error handling ...
```

Update `_confirm_processing` in orchestrator to respect skip flag:

```python
def _confirm_processing(self, issue_count: int) -> bool:
    """Ask user to confirm processing."""
    if getattr(self, '_skip_confirmation', False):
        return True

    # ... existing confirmation code ...
```

### 5. Add Configuration Validation Command

**File**: `src/vibe_heal/cli.py` (add new command)

```python
@app.command()
def validate() -> None:
    """Validate configuration and environment."""
    from vibe_heal.config import VibeHealConfig, ConfigurationError
    from vibe_heal.git import GitManager
    from vibe_heal.ai_tools import AIToolFactory

    console.print("[bold]Validating vibe-heal environment...[/bold]\n")

    # Check configuration
    try:
        config = VibeHealConfig()
        console.print("[green]✓[/green] Configuration loaded")
        console.print(f"  SonarQube URL: {config.sonarqube_url}")
        console.print(f"  Project Key: {config.sonarqube_project_key}")
    except ConfigurationError as e:
        console.print(f"[red]✗ Configuration error: {e}[/red]")
        sys.exit(1)

    # Check Git repository
    try:
        git_manager = GitManager()
        if git_manager.is_repository():
            console.print("[green]✓[/green] Git repository found")
            console.print(f"  Branch: {git_manager.get_current_branch()}")
            console.print(f"  Clean: {git_manager.is_clean()}")
        else:
            console.print("[yellow]⚠[/yellow] Not in a Git repository")
    except Exception as e:
        console.print(f"[red]✗ Git error: {e}[/red]")

    # Check AI tools
    tool_type = AIToolFactory.detect_available()
    if tool_type:
        console.print(f"[green]✓[/green] AI tool available: {tool_type.display_name}")
    else:
        console.print("[red]✗ No AI tool found (Claude Code or Aider)[/red]")
        sys.exit(1)

    # Try connecting to SonarQube
    console.print("\n[cyan]Testing SonarQube connection...[/cyan]")
    try:
        import asyncio
        from vibe_heal.sonarqube import SonarQubeClient

        async def test_connection():
            async with SonarQubeClient(config) as client:
                # Simple API call to verify auth
                await client._request("GET", "/api/system/status")

        asyncio.run(test_connection())
        console.print("[green]✓[/green] SonarQube connection successful")
    except Exception as e:
        console.print(f"[red]✗ SonarQube connection failed: {e}[/red]")
        sys.exit(1)

    console.print("\n[bold green]All checks passed![/bold green]")
```

### 6. Write Tests

**File**: `tests/utils/test_validators.py`
- Test file existence validation
- Test file in project validation
- Test supported file type checking

## Additional Safety Features

### Maximum Issues Limit

Already implemented via `--max-issues` flag.

### Better Error Messages

Update exception messages throughout to be more helpful:
- Include suggestions for fixes
- Show relevant documentation links
- Provide examples

### Signal Handling

Add graceful shutdown on Ctrl+C (already in CLI with `KeyboardInterrupt`).

## Verification Steps

1. Run validator tests:
   ```bash
   uv run pytest tests/utils/ -v
   ```

2. Test validation command:
   ```bash
   vibe-heal validate
   ```

3. Test file validation:
   ```bash
   # Should fail
   vibe-heal fix /etc/passwd

   # Should warn
   vibe-heal fix image.png
   ```

4. Test interruption handling:
   ```bash
   vibe-heal fix large_file.py
   # Press Ctrl+C during execution
   ```

5. Test with log file:
   ```bash
   vibe-heal fix src/main.py --log-file vibe-heal.log --verbose
   cat vibe-heal.log
   ```

## Definition of Done

- ✅ File path validation (exists, in project, supported type)
- ✅ Improved logging with file output option
- ✅ Rollback instructions displayed after fixes
- ✅ `--yes` flag to skip confirmations
- ✅ `validate` command to check environment
- ✅ Graceful Ctrl+C handling
- ✅ Better error messages throughout
- ✅ Comprehensive tests for validators
- ✅ All safety features documented

## Notes

- Safety is paramount - better to refuse than to break things
- File validation prevents common mistakes
- Rollback instructions give users confidence
- The `validate` command helps troubleshoot setup issues
- Consider adding `--backup` flag in future to create safety backups
- Log files are useful for debugging issues later
