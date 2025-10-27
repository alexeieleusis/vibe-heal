"""Command-line interface for vibe-heal."""

import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.logging import RichHandler

from vibe_heal import __version__
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.factory import AIToolFactory
from vibe_heal.cleanup.orchestrator import CleanupOrchestrator, CleanupResult
from vibe_heal.config import ConfigurationError, VibeHealConfig
from vibe_heal.deduplication.orchestrator import DeduplicationOrchestrator
from vibe_heal.orchestrator import VibeHealOrchestrator
from vibe_heal.sonarqube.client import SonarQubeClient

app = typer.Typer(
    name="vibe-heal",
    help="AI-powered SonarQube issue remediation tool",
    add_completion=False,
)
console = Console()


def setup_logging(verbose: bool) -> None:
    """Setup logging configuration.

    Args:
        verbose: If True, enable debug logging
    """
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
        help="Preview fixes without committing",
    ),
    max_issues: int | None = typer.Option(
        None,
        "--max-issues",
        "-n",
        help="Maximum number of issues to fix",
    ),
    min_severity: str | None = typer.Option(
        None,
        "--min-severity",
        help="Minimum severity (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)",
    ),
    ai_tool: AIToolType | None = typer.Option(
        None,
        "--ai-tool",
        help="AI tool to use (overrides config)",
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help="Path to custom environment file (default: .env.vibeheal or .env)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Fix SonarQube issues in a file."""
    setup_logging(verbose)

    try:
        # Load configuration
        config = VibeHealConfig(env_file=env_file)

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
def dedupe(
    file_path: str = typer.Argument(..., help="Path to file to deduplicate"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview fixes without committing",
    ),
    max_duplications: int | None = typer.Option(
        None,
        "--max-duplications",
        "-n",
        help="Maximum number of duplication groups to fix",
    ),
    ai_tool: AIToolType | None = typer.Option(
        None,
        "--ai-tool",
        help="AI tool to use (overrides config)",
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help="Path to custom environment file (default: .env.vibeheal or .env)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Remove code duplications in a file."""
    setup_logging(verbose)

    try:
        # Load configuration
        config = VibeHealConfig(env_file=env_file)

        # Override AI tool if specified
        if ai_tool:
            config.ai_tool = ai_tool

        # Initialize AI tool
        if config.ai_tool:
            tool_type = config.ai_tool
            console.print(f"[blue]Using configured AI tool: {tool_type.display_name}[/blue]")
        else:
            detected_tool = AIToolFactory.detect_available()
            if not detected_tool:
                console.print("[red]No AI tool found. Please install Claude Code or Aider.[/red]")
                sys.exit(1)
            tool_type = detected_tool
            console.print(f"[blue]Auto-detected AI tool: {tool_type.display_name}[/blue]")

        ai_tool_instance = AIToolFactory.create(tool_type, config)

        # Check AI tool is available
        if not ai_tool_instance.is_available():
            console.print(f"[red]{tool_type.display_name} is not available[/red]")
            sys.exit(1)

        # Create orchestrator
        orchestrator = DeduplicationOrchestrator(
            config=config,
            ai_tool=ai_tool_instance,
            console=console,
        )

        # Run deduplication
        summary = asyncio.run(
            orchestrator.dedupe_file(
                file_path=file_path,
                dry_run=dry_run,
                max_duplications=max_duplications,
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


def _display_cleanup_results(result: CleanupResult) -> None:
    """Display cleanup results.

    Args:
        result: Cleanup result to display
    """
    console.print("\n[bold]Cleanup Summary:[/bold]")
    console.print(f"  Files processed: {len(result.files_processed)}")
    console.print(f"  [green]Total issues fixed: {result.total_issues_fixed}[/green]")

    if result.files_processed:
        console.print("\n[bold]Per-File Results:[/bold]")
        for file_result in result.files_processed:
            status = "[green]✓[/green]" if file_result.success else "[red]✗[/red]"
            console.print(f"  {status} {file_result.file_path}: {file_result.issues_fixed} issues fixed")
            if file_result.error_message:
                console.print(f"      [red]Error: {file_result.error_message}[/red]")

    if not result.success:
        if result.error_message:
            console.print(f"\n[red]Cleanup failed: {result.error_message}[/red]")
        sys.exit(1)

    console.print("\n[green]✨ Branch cleanup complete![/green]")


async def _run_cleanup(
    config: VibeHealConfig,
    ai_tool_instance: AITool,
    base_branch: str,
    max_iterations: int,
    file_patterns: list[str] | None,
    verbose: bool,
) -> None:
    """Run branch cleanup workflow.

    Args:
        config: Configuration object
        ai_tool_instance: AI tool instance to use for fixing
        base_branch: Base branch to compare against
        max_iterations: Maximum fix iterations per file
        file_patterns: Optional file patterns to filter
        verbose: Enable verbose output
    """
    async with SonarQubeClient(config) as client:
        orchestrator = CleanupOrchestrator(config, client, ai_tool_instance)

        result = await orchestrator.cleanup_branch(
            base_branch=base_branch,
            max_iterations=max_iterations,
            file_patterns=file_patterns,
            verbose=verbose,
        )

        _display_cleanup_results(result)


@app.command()
def cleanup(
    base_branch: str = typer.Option(
        "origin/main",
        "--base-branch",
        "-b",
        help="Base branch to compare against",
    ),
    max_iterations: int = typer.Option(
        10,
        "--max-iterations",
        "-i",
        help="Maximum fix iterations per file",
    ),
    file_patterns: list[str] | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help="File patterns to filter (e.g., '*.py', 'src/**/*.ts')",
    ),
    ai_tool: AIToolType | None = typer.Option(
        None,
        "--ai-tool",
        help="AI tool to use (overrides config)",
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help="Path to custom environment file (default: .env.vibeheal or .env)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """Clean up all modified files in current branch.

    Creates a temporary SonarQube project, analyzes all modified files,
    and fixes issues iteratively until the branch is clean.
    """
    setup_logging(verbose)

    try:
        # Load configuration
        config = VibeHealConfig(env_file=env_file)

        # Override AI tool if specified
        if ai_tool:
            config.ai_tool = ai_tool

        # Display what we're doing
        console.print("\n[bold cyan]Branch Cleanup[/bold cyan]")
        console.print(f"  Base branch: {base_branch}")
        console.print(f"  Max iterations per file: {max_iterations}")
        if file_patterns:
            console.print(f"  File patterns: {', '.join(file_patterns)}")
        console.print()

        # Initialize AI tool
        if config.ai_tool:
            tool_type = config.ai_tool
            console.print(f"[blue]Using configured AI tool: {tool_type.display_name}[/blue]")
        else:
            detected_tool = AIToolFactory.detect_available()
            if not detected_tool:
                console.print("[red]No AI tool found. Please install Claude Code or Aider.[/red]")
                sys.exit(1)
            tool_type = detected_tool
            console.print(f"[blue]Auto-detected AI tool: {tool_type.display_name}[/blue]")

        ai_tool_instance = AIToolFactory.create(tool_type, config)

        # Check AI tool is available
        if not ai_tool_instance.is_available():
            console.print(f"[red]{tool_type.display_name} is not available[/red]")
            sys.exit(1)

        # Run cleanup
        asyncio.run(
            _run_cleanup(
                config=config,
                ai_tool_instance=ai_tool_instance,
                base_branch=base_branch,
                max_iterations=max_iterations,
                file_patterns=file_patterns,
                verbose=verbose,
            )
        )

    except ConfigurationError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


@app.command()
def config(
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help="Path to custom environment file (default: .env.vibeheal or .env)",
    ),
) -> None:
    """Show current configuration."""
    try:
        cfg = VibeHealConfig(env_file=env_file)
        console.print("[bold]Current Configuration:[/bold]\n")
        console.print(f"  SonarQube URL: {cfg.sonarqube_url}")
        console.print(f"  Project Key: {cfg.sonarqube_project_key}")
        console.print(f"  Auth Method: {'Token' if cfg.use_token_auth else 'Basic'}")
        if cfg.ai_tool:
            console.print(f"  AI Tool: {cfg.ai_tool.display_name}")
        else:
            console.print("  AI Tool: Auto-detect")
        console.print("\n[bold]Context Enrichment:[/bold]")
        console.print(f"  Code Context Lines: {cfg.code_context_lines}")
        console.print(f"  Include Rule Description: {cfg.include_rule_description}")
    except ConfigurationError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"vibe-heal version {__version__}")


if __name__ == "__main__":
    app()
