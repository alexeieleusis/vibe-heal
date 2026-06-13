"""Converter from oxlint JSON report format to ESLint JSON format."""

from __future__ import annotations

import re
from typing import Any

_PLUGIN_RULE_RE = re.compile(r"^(.*?)\(([^()]*)\)$")
_ESLINT_PLUGIN_PREFIX = "eslint-plugin-"


def _transform_rule_id(code: str) -> str:
    match = _PLUGIN_RULE_RE.match(code)
    if not match:
        return code
    x, y = match.group(1), match.group(2)
    return x.removeprefix(_ESLINT_PLUGIN_PREFIX) + "/" + y


def _map_severity(severity: str) -> int:
    return 2 if severity == "error" else 1


def _extract_position(diagnostic: dict[str, Any]) -> tuple[int, int, int, int]:
    try:
        span = diagnostic["labels"][0]["span"]
        line: int = span["line"]
        col: int = span["column"] + 1  # oxlint 0-indexed → ESLint 1-indexed
        end_col: int = col + span["length"]
        return line, col, line, end_col
    except (KeyError, TypeError, IndexError):
        return 1, 1, 1, 1


def convert_oxlint_to_eslint(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert an oxlint JSON report dict to ESLint JSON format.

    Args:
        data: Parsed oxlint report with a "diagnostics" list.
              Caller must validate shape before calling.

    Returns:
        ESLint-format list of file objects.
    """
    diagnostics: list[dict[str, Any]] = data["diagnostics"]

    files: dict[str, list[dict[str, Any]]] = {}
    for diag in diagnostics:
        filename: str = diag["filename"]
        if filename not in files:
            files[filename] = []
        line, col, end_line, end_col = _extract_position(diag)
        files[filename].append({
            "ruleId": _transform_rule_id(diag.get("code", "")),
            "severity": _map_severity(diag.get("severity", "")),
            "message": diag["message"],
            "line": line,
            "column": col,
            "endLine": end_line,
            "endColumn": end_col,
        })

    result = []
    for filepath, messages in files.items():
        result.append({
            "filePath": filepath,
            "messages": messages,
            "errorCount": sum(1 for m in messages if m["severity"] == 2),
            "warningCount": sum(1 for m in messages if m["severity"] == 1),
            "fixableErrorCount": 0,
            "fixableWarningCount": 0,
            "source": None,
        })
    return result
