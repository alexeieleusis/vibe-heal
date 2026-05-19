"""Shared utilities for vibe-heal."""

from rich.console import Console

from vibe_heal.models import FixSummary


def display_fix_summary(
    console: Console,
    summary: FixSummary,
    dry_run: bool,
    total_label: str = "Total issues",
) -> None:
    """Display a fix summary to the console.

    Args:
        console: Rich console for output
        summary: Fix summary to display
        dry_run: Whether in dry-run mode
        total_label: Label for the total count line
    """
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  {total_label}: {summary.total_issues}")
    console.print(f"  [green]Fixed: {summary.fixed}[/green]")
    console.print(f"  [red]Failed: {summary.failed}[/red]")
    console.print(f"  [yellow]Skipped: {summary.skipped}[/yellow]")

    if summary.fixed > 0:
        console.print(f"  Success rate: {summary.success_rate:.1f}%")

    if not dry_run and summary.commits:
        console.print(f"\n[bold]Created {len(summary.commits)} commit(s)[/bold]")

    if dry_run:
        console.print("\n[yellow]Dry-run mode: no changes committed[/yellow]")

    console.print("\n[dim]GitHub: https://github.com/alexeieleusis/vibe-heal[/dim]")
