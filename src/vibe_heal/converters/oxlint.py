"""Converter from oxlint JSON report format to ESLint JSON format."""

from __future__ import annotations

from typing import Any


def convert_oxlint_to_eslint(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert an oxlint JSON report dict to ESLint JSON format."""
    raise NotImplementedError
