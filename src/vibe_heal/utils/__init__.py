"""Shared utilities for vibe-heal."""

from vibe_heal.models import FixSummary
from vibe_heal.output import bold, console, error, success, warn


def display_fix_summary(
    summary: FixSummary,
    dry_run: bool,
    total_label: str = "Total issues",
) -> None:
    """Display a fix summary to the console.

    Args:
        summary: Fix summary to display
        dry_run: Whether in dry-run mode
        total_label: Label for the total count line
    """
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  {total_label}: {summary.total_issues}")
    if summary.fixed:
        success(f"  Fixed: {summary.fixed}")
    else:
        console.print(f"  Fixed: {summary.fixed}")
    if summary.failed:
        error(f"  Failed: {summary.failed}")
    else:
        console.print(f"  Failed: {summary.failed}")
    if summary.skipped:
        warn(f"  Skipped: {summary.skipped}")
    else:
        console.print(f"  Skipped: {summary.skipped}")

    if summary.fixed > 0:
        console.print(f"  Success rate: {summary.success_rate:.1f}%")

    if not dry_run and summary.commits:
        bold(f"\nCreated {len(summary.commits)} commit(s)")

    if dry_run:
        console.print("\n[yellow]Dry-run mode: no changes committed[/yellow]")

    console.print("\n[dim]GitHub: https://github.com/alexeieleusis/vibe-heal[/dim]")
