"""Tests for output.py safe print helpers."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _mock_console():
    """Patch the shared console for all tests in this module."""
    with patch("vibe_heal.output.console") as mock:
        yield mock


def test_dim_escapes_brackets(_mock_console):
    from vibe_heal.output import dim

    dim("File [bad]")
    _mock_console.print.assert_called_once_with("[dim]File \\[bad][/dim]")


def test_success_escapes_brackets(_mock_console):
    from vibe_heal.output import success

    success("[green]spoofed[/green]")
    _mock_console.print.assert_called_once_with("[green]\\[green]spoofed\\[/green][/green]")


def test_warn_escapes_brackets(_mock_console):
    from vibe_heal.output import warn

    warn("Could not delete [project-key]")
    _mock_console.print.assert_called_once_with("[yellow]Could not delete \\[project-key][/yellow]")


def test_error_escapes_brackets(_mock_console):
    from vibe_heal.output import error

    error("Failed: [/path/to/file]")
    _mock_console.print.assert_called_once_with("[red]Failed: \\[/path/to/file][/red]")


def test_info_escapes_brackets(_mock_console):
    from vibe_heal.output import info

    info("AI tool: [claude-code]")
    _mock_console.print.assert_called_once_with("[blue]AI tool: \\[claude-code][/blue]")


def test_cyan_escapes_brackets(_mock_console):
    from vibe_heal.output import cyan

    cyan("Found [3] items")
    _mock_console.print.assert_called_once_with("[cyan]Found \\[3] items[/cyan]")


def test_bold_cyan_escapes_brackets(_mock_console):
    from vibe_heal.output import bold_cyan

    bold_cyan("Processing [file]")
    _mock_console.print.assert_called_once_with("[bold cyan]Processing \\[file][/bold cyan]")


def test_bold_escapes_brackets(_mock_console):
    from vibe_heal.output import bold

    bold("Header [1]")
    _mock_console.print.assert_called_once_with("[bold]Header \\[1][/bold]")


def test_plain_strings_pass_through(_mock_console):
    from vibe_heal.output import dim

    dim("No special chars here")
    _mock_console.print.assert_called_once_with("[dim]No special chars here[/dim]")
