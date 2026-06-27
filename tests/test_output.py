"""Tests for output.py safe print helpers."""

from unittest.mock import patch

import pytest

from vibe_heal.output import bold, bold_cyan, cyan, dim, error, info, success, warn


@pytest.fixture(autouse=True)
def _mock_console():
    """Patch the shared console for all tests in this module."""
    with patch("vibe_heal.output.console") as mock:
        yield mock


def test_dim_escapes_brackets(_mock_console):
    dim("File [bad]")
    _mock_console.print.assert_called_once_with("[dim]File \\[bad][/dim]")


def test_success_escapes_brackets(_mock_console):
    success("[green]spoofed[/green]")
    _mock_console.print.assert_called_once_with("[green]\\[green]spoofed\\[/green][/green]")


def test_warn_escapes_brackets(_mock_console):
    warn("Could not delete [project-key]")
    _mock_console.print.assert_called_once_with("[yellow]Could not delete \\[project-key][/yellow]")


def test_error_escapes_brackets(_mock_console):
    error("Failed: [/path/to/file]")
    _mock_console.print.assert_called_once_with("[red]Failed: \\[/path/to/file][/red]")


def test_info_escapes_brackets(_mock_console):
    info("AI tool: [claude-code]")
    _mock_console.print.assert_called_once_with("[blue]AI tool: \\[claude-code][/blue]")


def test_cyan_escapes_markup_brackets(_mock_console):
    cyan("Found [3] items")
    # [3] is not a markup tag so rich.markup.escape leaves it alone
    _mock_console.print.assert_called_once_with("[cyan]Found [3] items[/cyan]")


def test_bold_cyan_escapes_brackets(_mock_console):
    bold_cyan("Processing [file]")
    _mock_console.print.assert_called_once_with("[bold cyan]Processing \\[file][/bold cyan]")


def test_bold_escapes_markup_brackets(_mock_console):
    bold("Header [1]")
    # [1] is not a markup tag so rich.markup.escape leaves it alone
    _mock_console.print.assert_called_once_with("[bold]Header [1][/bold]")


def test_plain_strings_pass_through(_mock_console):
    dim("No special chars here")
    _mock_console.print.assert_called_once_with("[dim]No special chars here[/dim]")
