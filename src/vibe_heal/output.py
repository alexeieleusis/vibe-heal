"""Safe terminal output helpers for vibe-heal.

This module is the single place in vibe_heal where Rich markup strings are
constructed at runtime. All dynamic values are escaped before insertion so that
user data containing brackets (file paths, exception messages, scanner output)
can never trigger a Rich MarkupError.

Usage:
    from vibe_heal.output import console, dim, success, warn, error, info, cyan, bold_cyan

Do NOT call console.print(f"[markup]{dynamic}[/markup]") anywhere else in the
codebase. Use these helpers instead — they handle escaping internally.
"""

from rich.console import Console

console = Console()


def _esc(msg: str) -> str:
    """Escape all opening brackets so Rich never interprets user data as markup."""
    return msg.replace("[", "\\[")


def dim(msg: str) -> None:
    """Print msg in muted/dim style. msg is auto-escaped."""
    console.print(f"[dim]{_esc(msg)}[/dim]")


def success(msg: str) -> None:
    """Print msg in green."""
    console.print(f"[green]{_esc(msg)}[/green]")


def warn(msg: str) -> None:
    """Print msg in yellow."""
    console.print(f"[yellow]{_esc(msg)}[/yellow]")


def error(msg: str) -> None:
    """Print msg in red."""
    console.print(f"[red]{_esc(msg)}[/red]")


def info(msg: str) -> None:
    """Print msg in blue."""
    console.print(f"[blue]{_esc(msg)}[/blue]")


def cyan(msg: str) -> None:
    """Print msg in cyan."""
    console.print(f"[cyan]{_esc(msg)}[/cyan]")


def bold(msg: str) -> None:
    """Print msg in bold."""
    console.print(f"[bold]{_esc(msg)}[/bold]")


def bold_cyan(msg: str) -> None:
    """Print msg in bold cyan."""
    console.print(f"[bold cyan]{_esc(msg)}[/bold cyan]")
