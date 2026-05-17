"""Reporter: writes review results as JSON and markdown."""

from __future__ import annotations

from pathlib import Path

from vibe_heal.review.models import ReviewResult


def default_report_dir(project_key: str, branch: str) -> Path:
    """Return the default report directory for a project and branch.

    Path format: ~/.vibe-heal/reviews/<project-key>/<branch>/
    """
    return Path.home() / ".vibe-heal" / "reviews" / project_key / branch


def write_reports(result: ReviewResult, report_dir: Path) -> None:
    """Write review.json and review.md to the given directory.

    Creates the directory (and parents) if it doesn't exist.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_json(result, report_dir / "review.json")
    _write_markdown(result, report_dir / "review.md")


def load_report(report_dir: Path) -> ReviewResult:
    """Load a ReviewResult from review.json in the given directory."""
    json_path = report_dir / "review.json"
    try:
        data = json_path.read_text(encoding="utf-8")
    except OSError as e:
        raise FileNotFoundError(f"Cannot read report file: {json_path}") from e
    try:
        return ReviewResult.model_validate_json(data)
    except Exception as e:
        raise ValueError(f"Malformed report file: {json_path}") from e


def load_report_from_path(json_path: Path) -> ReviewResult:
    """Load a ReviewResult from a specific JSON file path."""
    try:
        data = json_path.read_text(encoding="utf-8")
    except OSError as e:
        raise FileNotFoundError(f"Cannot read report file: {json_path}") from e
    try:
        return ReviewResult.model_validate_json(data)
    except Exception as e:
        raise ValueError(f"Malformed report file: {json_path}") from e


def _write_json(result: ReviewResult, path: Path) -> None:
    """Serialize ReviewResult to JSON."""
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")


def _write_markdown(result: ReviewResult, path: Path) -> None:
    """Write a human-readable markdown report."""
    lines: list[str] = []
    lines.append(f"# Review: {result.project_key} ({result.branch})")
    lines.append(f"Base: `{result.base_branch}`")
    lines.append("")
    lines.append(
        f"**Total issues: {result.total_issues}** | "
        f"**Duplication findings: {result.total_duplications}** | "
        f"**Files checked: {len(result.files)}**"
    )
    lines.append("")

    for fr in result.files:
        lines.append(f"## `{fr.file_path}`")
        lines.append("")

        if fr.issues:
            lines.append("| Rule | Message | Line | Severity |")
            lines.append("|------|---------|------|----------|")
            for issue in fr.issues:
                rule_display = issue.rule
                if issue.doc_url:
                    rule_display = f"[{issue.rule}]({issue.doc_url})"
                msg = issue.message.replace("|", "\\|").replace("\n", " ").replace("\r", "")
                lines.append(f"| {rule_display} | {msg} | {issue.line} | {issue.severity} |")
            lines.append("")

        if fr.duplications:
            lines.append("### Active Duplications")
            lines.append("")
            lines.append("| Block (this file) | Duplicated in |")
            lines.append("|---|---|")
            for dup in fr.duplications:
                locations = ", ".join(
                    f"`{loc.file_path}` lines {loc.from_line}-{loc.to_line}" for loc in dup.other_locations
                )
                lines.append(f"| lines {dup.from_line}-{dup.to_line} | {locations} |")
            lines.append("")

        if fr.resolved_duplications:
            lines.append("### Resolved Duplications - check other instances")
            lines.append("")
            lines.append(
                "> You modified lines that were part of a duplicated block in main. "
                "The duplication is no longer detected in this branch, but other instances may need updating."
            )
            lines.append("")
            lines.append("| Block in main | Other instances |")
            lines.append("|---|---|")
            for res in fr.resolved_duplications:
                locations = ", ".join(
                    f"`{loc.file_path}` lines {loc.from_line}-{loc.to_line}" for loc in res.other_locations
                )
                lines.append(f"| lines {res.main_from_line}-{res.main_to_line} | {locations} |")
            lines.append("")

        if not fr.issues and not fr.duplications and not fr.resolved_duplications:
            lines.append("No issues.")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
