"""Command-line interface for vibe-heal."""

import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.logging import RichHandler

from vibe_heal import __version__
from vibe_heal.ai_tools.base import AIToolType
from vibe_heal.config import ConfigurationError, VibeHealConfig
from vibe_heal.orchestrator import VibeHealOrchestrator

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
        config = VibeHealConfig()  # type: ignore[call-arg]

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
        cfg = VibeHealConfig()  # type: ignore[call-arg]
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
