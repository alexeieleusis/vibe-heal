"""Command-line interface for vibe-heal."""

import asyncio
import json
import logging
import sys
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.markup import escape as rich_escape
from rich.table import Table

from vibe_heal import __version__
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.factory import AIToolFactory
from vibe_heal.cleanup.orchestrator import CleanupOrchestrator, CleanupResult
from vibe_heal.config import ConfigurationError, VibeHealConfig
from vibe_heal.converters.oxlint import convert_oxlint_to_eslint
from vibe_heal.deduplication.orchestrator import (
    DedupeBranchOrchestrator,
    DedupeBranchResult,
    DeduplicationOrchestrator,
)
from vibe_heal.orchestrator import VibeHealOrchestrator
from vibe_heal.output import bold, bold_cyan, console, cyan, dim, error, info, success, warn
from vibe_heal.review import NoOpenPrError, ReviewOrchestrator
from vibe_heal.review.models import ReviewIssue
from vibe_heal.review.orchestrator import BaselineScanResult, ReviewAnalysisResult
from vibe_heal.review.reporter import default_report_dir
from vibe_heal.sonarqube.client import SonarQubeClient

app = typer.Typer(
    name="vibe-heal",
    help="AI-powered SonarQube issue remediation tool\n\nGitHub: https://github.com/alexeieleusis/vibe-heal",
    add_completion=False,
)

# Default values
DEFAULT_BASE_BRANCH = "origin/main"

# Help text constants
VERBOSE_OUTPUT_HELP = "Verbose output"
ENV_FILE_HELP = "Path to custom environment file (default: .env.vibeheal or .env)"
AI_TOOL_OVERRIDE_HELP = "AI tool to use (overrides config)"
FILE_PATTERN_HELP = "File patterns to filter (e.g., '*.py', 'src/**/*.ts')"
BASE_BRANCH_HELP = "Base branch to compare against"


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

    # Suppress httpx logs unless in verbose mode
    # These INFO-level HTTP request logs break the progress display
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)


def initialize_ai_tool(config: VibeHealConfig) -> AITool:
    """Initialize and validate AI tool.

    Args:
        config: Configuration object with optional ai_tool setting

    Returns:
        Initialized AI tool instance

    Raises:
        SystemExit: If no AI tool is found or tool is not available
    """
    # Determine which AI tool to use
    if config.ai_tool:
        tool_type = config.ai_tool
        info(f"Using configured AI tool: {tool_type.display_name}")
    else:
        detected_tool = AIToolFactory.detect_available()
        if not detected_tool:
            error("No AI tool found. Please install Claude Code or Aider.")
            sys.exit(1)
        tool_type = detected_tool
        info(f"Auto-detected AI tool: {tool_type.display_name}")

    # Create AI tool instance
    ai_tool_instance = AIToolFactory.create(tool_type, config)

    # Validate AI tool is available
    if not ai_tool_instance.is_available():
        error(f"{tool_type.display_name} is not available")
        sys.exit(1)

    return ai_tool_instance


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
        help=AI_TOOL_OVERRIDE_HELP,
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help=VERBOSE_OUTPUT_HELP,
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

        # Initialize AI tool
        ai_tool_instance = initialize_ai_tool(config)

        # Create orchestrator
        orchestrator = VibeHealOrchestrator(config, ai_tool_instance)

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
        error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
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
        help=AI_TOOL_OVERRIDE_HELP,
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help=VERBOSE_OUTPUT_HELP,
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
        ai_tool_instance = initialize_ai_tool(config)

        # Create orchestrator
        orchestrator = DeduplicationOrchestrator(
            config=config,
            ai_tool=ai_tool_instance,
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
        error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


def _display_branch_operation_header(
    operation_name: str,
    base_branch: str,
    max_iterations: int,
    file_patterns: list[str] | None,
) -> None:
    """Display header for branch operations.

    Args:
        operation_name: Name of the operation (e.g., "Branch Cleanup")
        base_branch: Base branch being compared against
        max_iterations: Maximum iterations per file
        file_patterns: Optional file patterns to filter
    """
    bold_cyan(f"\n{operation_name}")
    console.print(f"  Base branch: {base_branch}")
    console.print(f"  Max iterations per file: {max_iterations}")
    if file_patterns:
        console.print(f"  File patterns: {', '.join(file_patterns)}")
    console.print()


def _display_cleanup_results(result: CleanupResult) -> None:
    """Display cleanup results.

    Args:
        result: Cleanup result to display
    """
    console.print("\n[bold]Cleanup Summary:[/bold]")
    console.print(f"  Files processed: {len(result.files_processed)}")
    success(f"  Total issues fixed: {result.total_issues_fixed}")

    if result.files_processed:
        console.print("\n[bold]Per-File Results:[/bold]")
        for file_result in result.files_processed:
            status = "[green]✓[/green]" if file_result.success else "[red]✗[/red]"
            console.print(
                f"  {status} {rich_escape(str(file_result.file_path))}: {file_result.issues_fixed} issues fixed"
            )
            if file_result.error_message:
                error(f"      Error: {file_result.error_message}")

    if not result.success:
        if result.error_message:
            error(f"\nCleanup failed: {result.error_message}")
        sys.exit(1)

    console.print("\n[green]✨ Branch cleanup complete![/green]")
    console.print("\n[dim]GitHub: https://github.com/alexeieleusis/vibe-heal[/dim]")


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
        DEFAULT_BASE_BRANCH,
        "--base-branch",
        "-b",
        help=BASE_BRANCH_HELP,
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
        help=FILE_PATTERN_HELP,
    ),
    ai_tool: AIToolType | None = typer.Option(
        None,
        "--ai-tool",
        help=AI_TOOL_OVERRIDE_HELP,
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help=VERBOSE_OUTPUT_HELP,
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
        _display_branch_operation_header(
            operation_name="Branch Cleanup",
            base_branch=base_branch,
            max_iterations=max_iterations,
            file_patterns=file_patterns,
        )

        # Initialize AI tool
        ai_tool_instance = initialize_ai_tool(config)

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
        error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


def _display_dedupe_branch_results(result: DedupeBranchResult) -> None:
    """Display dedupe-branch results.

    Args:
        result: Dedupe-branch result to display
    """
    console.print("\n[bold]Deduplication Summary:[/bold]")
    console.print(f"  Files processed: {len(result.files_processed)}")
    success(f"  Total duplications fixed: {result.total_duplications_fixed}")

    if result.files_processed:
        console.print("\n[bold]Per-File Results:[/bold]")
        for file_result in result.files_processed:
            status = "[green]✓[/green]" if file_result.success else "[red]✗[/red]"
            console.print(
                f"  {status} {rich_escape(str(file_result.file_path))}: {file_result.duplications_fixed} duplications fixed"
            )
            if file_result.error_message:
                error(f"      Error: {file_result.error_message}")

    if not result.success:
        if result.error_message:
            error(f"\nDeduplication failed: {result.error_message}")
        sys.exit(1)

    console.print("\n[green]✨ Branch deduplication complete![/green]")
    console.print("\n[dim]GitHub: https://github.com/alexeieleusis/vibe-heal[/dim]")


async def _run_dedupe_branch(
    config: VibeHealConfig,
    ai_tool_instance: AITool,
    base_branch: str,
    max_iterations: int,
    file_patterns: list[str] | None,
    verbose: bool,
) -> None:
    """Run branch deduplication workflow.

    Args:
        config: Configuration object
        ai_tool_instance: AI tool instance to use for fixing
        base_branch: Base branch to compare against
        max_iterations: Maximum dedup iterations per file
        file_patterns: Optional file patterns to filter
        verbose: Enable verbose output
    """
    async with SonarQubeClient(config) as client:
        orchestrator = DedupeBranchOrchestrator(config, client, ai_tool_instance)

        result = await orchestrator.dedupe_branch(
            base_branch=base_branch,
            max_iterations=max_iterations,
            file_patterns=file_patterns,
            verbose=verbose,
        )

        _display_dedupe_branch_results(result)


@app.command()
def dedupe_branch(
    base_branch: str = typer.Option(
        DEFAULT_BASE_BRANCH,
        "--base-branch",
        "-b",
        help=BASE_BRANCH_HELP,
    ),
    max_iterations: int = typer.Option(
        10,
        "--max-iterations",
        "-i",
        help="Maximum dedup iterations per file",
    ),
    file_patterns: list[str] | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help=FILE_PATTERN_HELP,
    ),
    ai_tool: AIToolType | None = typer.Option(
        None,
        "--ai-tool",
        help=AI_TOOL_OVERRIDE_HELP,
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help=VERBOSE_OUTPUT_HELP,
    ),
) -> None:
    """Remove code duplications from all modified files in current branch.

    Creates a temporary SonarQube project, analyzes all modified files,
    and removes duplications iteratively until the branch is clean.
    """
    setup_logging(verbose)

    try:
        # Load configuration
        config = VibeHealConfig(env_file=env_file)

        # Override AI tool if specified
        if ai_tool:
            config.ai_tool = ai_tool

        # Display what we're doing
        _display_branch_operation_header(
            operation_name="Branch Deduplication",
            base_branch=base_branch,
            max_iterations=max_iterations,
            file_patterns=file_patterns,
        )

        # Initialize AI tool
        ai_tool_instance = initialize_ai_tool(config)

        # Run deduplication
        asyncio.run(
            _run_dedupe_branch(
                config=config,
                ai_tool_instance=ai_tool_instance,
                base_branch=base_branch,
                max_iterations=max_iterations,
                file_patterns=file_patterns,
                verbose=verbose,
            )
        )

    except ConfigurationError as e:
        error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


_SEVERITY_ORDER = ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]


def _get_highest_severity(
    issues: list[ReviewIssue],
    severity_order: list[str] | None = None,
) -> str:
    """Return the highest severity string for a list of issues."""
    if not issues:
        return "N/A"
    order = _SEVERITY_ORDER if severity_order is None else severity_order
    return min(
        (issue.severity for issue in issues),
        key=lambda s: order.index(s) if s in order else len(order),
    )


def _build_review_table(result: ReviewAnalysisResult) -> None:
    """Build and print the per-file breakdown table for review results."""
    if not result.files:
        return

    console.print("\n[bold]Per-File Breakdown:[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("File", style="cyan")
    table.add_column("Issues", justify="right")
    table.add_column("Highest Severity", justify="right")
    table.add_column("Duplications", justify="right")
    show_coverage = any(f.coverage_pct is not None for f in result.files)
    if show_coverage:
        table.add_column("Coverage", justify="right")

    for file_review in result.files:
        issue_count = len(file_review.issues)
        dup_count = len(file_review.duplications) + len(file_review.resolved_duplications)
        highest_severity = _get_highest_severity(file_review.issues)
        row: list[str] = [file_review.file_path, str(issue_count), highest_severity, str(dup_count)]
        if show_coverage:
            cov_str = f"{file_review.coverage_pct}%" if file_review.coverage_pct is not None else "—"
            row.append(cov_str)
        table.add_row(*row)

    console.print(table)


def _display_review_results(result: ReviewAnalysisResult) -> None:
    """Display review analysis results.

    Args:
        result: ReviewAnalysisResult from the orchestrator.
    """
    total_issues = result.total_issues
    total_duplications = result.total_duplications
    files_checked = result.files_analyzed

    console.print("\n[bold]Review Summary:[/bold]")
    console.print(f"  Branch: {rich_escape(result.branch)} (base: {rich_escape(result.base_branch)})")
    console.print(f"  Files checked: {files_checked}")
    console.print(f"  Total issues: {total_issues}")
    console.print(f"  Duplication findings: {total_duplications}")

    if result.files:
        _build_review_table(result)
    elif total_issues == 0 and total_duplications == 0:
        console.print("\n[green]No issues found on changed lines.[/green]")

    if result.report_file:
        dim(f"\nReport saved to {result.report_file}")


async def _run_review(
    config: VibeHealConfig,
    base_branch: str,
    file_patterns: list[str] | None,
    report_file: Path | None,
    verbose: bool,
    coverage: bool = False,
) -> None:
    """Run review analysis workflow.

    Args:
        config: Configuration object.
        base_branch: Base branch to compare against.
        file_patterns: Optional file patterns to filter.
        report_file: Optional path override for the report; None uses the default.
        verbose: Enable verbose output.
        coverage: When True, fetch and display line coverage for changed lines.
    """
    async with SonarQubeClient(config) as client:
        orchestrator = ReviewOrchestrator(config, client)
        result = await orchestrator.run_analysis(
            base_branch=base_branch,
            file_patterns=file_patterns,
            report_file=report_file,
            verbose=verbose,
            coverage=coverage,
        )
        _display_review_results(result)
        if not result.success:
            if result.error_message:
                error(result.error_message or "")
            sys.exit(1)


async def _run_review_post(
    report_file: Path,
    pr_number: int | None,
    verbose: bool,
    dry_run: bool = False,
) -> None:
    """Run review post workflow (no SonarQube config needed).

    Loads a previously saved report and posts it to GitHub PR.

    Args:
        report_file: Path to the saved review.json file.
        pr_number: Optional explicit PR number.
        verbose: Enable verbose output.
        dry_run: Preview what would be posted without making GitHub API calls.
    """
    from vibe_heal.review.github import GitHubReviewClient
    from vibe_heal.review.reporter import load_report_from_path

    github_client = GitHubReviewClient()
    report = load_report_from_path(report_file)
    if verbose:
        dim(f"  Report: branch={report.branch}, {report.total_issues} issue(s), {len(report.files)} file(s)")

    if pr_number is not None:
        pr = pr_number
        if verbose:
            dim(f"  Using explicit PR #{pr}")
    else:
        pr = await github_client.detect_pr()
        if verbose:
            dim(f"  Auto-detected PR #{pr}")

    if dry_run:
        payload = github_client.build_payload(report)
        comments = payload["comments"]
        warn(f"[dry-run] Would post {len(comments)} inline comment(s) to PR #{pr}:")
        dim(f"Review body: {payload['body']}")
        for comment in comments:
            dim(f"\n  {comment['path']}:{comment['line']}")
            console.print(comment["body"])
        return

    await github_client.post_review(pr, report)
    success(
        f"Posted {report.total_issues} issue(s) and "
        f"{report.total_duplications} duplication finding(s) "
        f"as review comments on PR #{pr}."
    )


def _review_post_mode(
    report_file: Path | None,
    pr_number: int | None,
    env_file: str | None,
    verbose: bool,
    dry_run: bool = False,
) -> None:
    """Handle the --post branch of the review command.

    Loads a previously saved report and posts it to a GitHub PR.
    SonarQube config is only required to determine the default report path;
    pass ``--report-file`` to skip the config lookup entirely.

    Args:
        report_file: Path to the saved report. If None, derive from config.
        pr_number: Explicit PR number (None = auto-detect).
        env_file: Optional path to a custom env file (for config loading).
        verbose: Enable verbose output.
        dry_run: Preview what would be posted without making GitHub API calls.
    """
    try:
        if report_file is None:
            from vibe_heal.git.branch_analyzer import BranchAnalyzer

            branch = BranchAnalyzer(Path.cwd()).get_current_branch()
            try:
                _cfg = VibeHealConfig(env_file=env_file)
                report_file = default_report_dir(_cfg.sonarqube_project_key, branch) / "review.json"
            except Exception:
                error(
                    "Cannot determine default report path: no SonarQube config found. "
                    "Pass --report-file to specify the report location."
                )
                sys.exit(1)

        asyncio.run(
            _run_review_post(
                report_file=report_file,
                pr_number=pr_number,
                verbose=verbose,
                dry_run=dry_run,
            )
        )
    except NoOpenPrError as e:
        warn(str(e))
        console.print("[dim]Report saved; use --post later when a PR is available.[/dim]")
    except FileNotFoundError as e:
        error(str(e))
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


def _display_baseline_results(result: BaselineScanResult) -> None:
    """Display baseline scan results.

    Args:
        result: BaselineScanResult from the orchestrator.
    """
    if result.success:
        success(f"Baseline scan complete: project {result.project_key} re-analyzed.")
        if result.dashboard_url:
            dim(f"Dashboard: {result.dashboard_url}")
    else:
        error(f"Baseline scan failed: {result.error_message}")


async def _run_baseline(config: VibeHealConfig) -> None:
    """Run the baseline scan workflow.

    Args:
        config: Configuration object.
    """
    async with SonarQubeClient(config) as client:
        orchestrator = ReviewOrchestrator(config, client)
        result = await orchestrator.run_baseline_scan()
        _display_baseline_results(result)
        if not result.success:
            sys.exit(1)


def _review_baseline_mode(env_file: str | None, verbose: bool) -> None:
    """Handle the --baseline branch of the review command.

    Args:
        env_file: Optional path to a custom env file (for config loading).
        verbose: Enable verbose output.
    """
    try:
        config = VibeHealConfig(env_file=env_file)
        asyncio.run(_run_baseline(config=config))
    except ConfigurationError as e:
        error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


@app.command()
def review(
    post: bool = typer.Option(
        False,
        "--post",
        help="Post saved report to GitHub PR",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be posted to GitHub without making API calls (only applies with --post)",
    ),
    pr_number: int | None = typer.Option(
        None,
        "--pr",
        help="GitHub PR number (override auto-detection)",
    ),
    base_branch: str = typer.Option(
        DEFAULT_BASE_BRANCH,
        "--base-branch",
        "-b",
        help=BASE_BRANCH_HELP,
    ),
    file_patterns: list[str] | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help=FILE_PATTERN_HELP,
    ),
    report_file: Path | None = typer.Option(
        None,
        "--report-file",
        help="Override report output path",
    ),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help=VERBOSE_OUTPUT_HELP,
    ),
    coverage: bool = typer.Option(False, "--coverage", help="Report test coverage for changed lines."),
    baseline: bool = typer.Option(
        False,
        "--baseline",
        help="Run a full SonarQube scan against the real project to refresh its baseline (no diff, no report).",
    ),
) -> None:
    """Analyze SonarQube issues on changed lines.

    Creates a temporary SonarQube project, analyzes modified files,
    and reports issues found on changed lines only.
    """
    setup_logging(verbose)

    if post:
        _review_post_mode(
            report_file=report_file, pr_number=pr_number, env_file=env_file, verbose=verbose, dry_run=dry_run
        )
        return

    if baseline:
        _review_baseline_mode(env_file=env_file, verbose=verbose)
        return

    try:
        config = VibeHealConfig(env_file=env_file)

        asyncio.run(
            _run_review(
                config=config,
                base_branch=base_branch,
                file_patterns=file_patterns,
                report_file=report_file,
                verbose=verbose,
                coverage=coverage,
            )
        )

    except ConfigurationError as e:
        error(f"Configuration error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        error(str(e))
        sys.exit(1)
    except NoOpenPrError as e:
        warn(str(e))
        console.print("[dim]Report saved; use --post later when a PR is available.[/dim]")
    except Exception as e:
        error(f"Error: {e}")
        if verbose:
            console.print_exception()
        sys.exit(1)


@app.command()
def config(
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
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
        error(f"Configuration error: {e}")
        sys.exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"vibe-heal version {__version__}")


@app.command()
def debug_issues(
    file_path: str | None = typer.Argument(None, help="Optional file path to check"),
    env_file: str | None = typer.Option(
        None,
        "--env-file",
        help=ENV_FILE_HELP,
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="Maximum number of issues to show",
    ),
) -> None:
    """Debug: show raw issues from SonarQube (with or without file filter)."""
    setup_logging(True)  # Always verbose for debug command

    try:
        config = VibeHealConfig(env_file=env_file)

        async def _debug() -> None:
            async with SonarQubeClient(config) as client:
                if file_path:
                    warn(f"Fetching issues for file: {file_path}")
                    console.print()
                    issues = await client.get_issues_for_file(file_path)
                else:
                    console.print("[yellow]Fetching ALL project issues (no file filter)[/yellow]\n")
                    # Fetch all project issues without file filter
                    issues = await client.get_issues(component=None, page_size=limit)

                bold(f"Found {len(issues)} issues\n")

                for idx, issue in enumerate(issues[:limit], 1):
                    cyan(f"Issue {idx}:")
                    console.print(f"  Key: {issue.key}")
                    console.print(f"  Rule: {issue.rule}")
                    console.print(f"  Component: {issue.component}")
                    console.print(f"  Line: {issue.line}")
                    console.print(f"  Status: {issue.status!r}")
                    console.print(f"  Issue Status: {issue.issue_status!r}")
                    console.print(f"  Severity: {issue.severity}")
                    console.print(f"  Message: {issue.message}")
                    console.print(f"  Is Fixable: {issue.is_fixable}")
                    console.print()

        asyncio.run(_debug())

    except ConfigurationError as e:
        error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        error(f"Error: {e}")
        console.print_exception()
        sys.exit(1)


@app.command()
def convert_report(
    input_file: str = typer.Argument(..., help="Path to the oxlint JSON report"),
    output_file: str | None = typer.Argument(
        None,
        help="Output path (default: <stem>.eslint.json in same directory)",
    ),
) -> None:
    """Convert an oxlint JSON report to ESLint format for SonarQube import."""
    input_path = Path(input_file)

    if not input_path.exists():
        error(f"Error: File not found: {input_file}")
        sys.exit(1)

    try:
        data = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        error(f"Error: Invalid JSON in {input_file}: {e}")
        sys.exit(1)
    except OSError as e:
        error(f"Error: Cannot read {input_file}: {e}")
        sys.exit(1)

    if not isinstance(data, dict):
        error(f"Error: Expected a JSON object, got {type(data).__name__}")
        sys.exit(1)

    if "diagnostics" not in data:
        error(f"Error: Missing 'diagnostics' key in {input_file}")
        sys.exit(1)

    if not isinstance(data["diagnostics"], list):
        error(f"Error: 'diagnostics' must be a list, got {type(data['diagnostics']).__name__}")
        sys.exit(1)

    output_path = (
        Path(output_file) if output_file is not None else input_path.with_name(input_path.stem + ".eslint.json")
    )

    try:
        eslint_data = convert_oxlint_to_eslint(data)
    except KeyError as e:
        error(f"Error: Malformed diagnostic — missing field {e}")
        sys.exit(1)

    try:
        output_path.write_text(json.dumps(eslint_data, indent=2))
    except OSError as e:
        error(f"Error: Cannot write to {output_path}: {e}")
        sys.exit(1)

    n_diagnostics = sum(len(f["messages"]) for f in eslint_data)
    n_files = len(eslint_data)
    console.print(f"Converted {n_diagnostics} diagnostics across {n_files} files → {rich_escape(str(output_path))}")


if __name__ == "__main__":
    app()
