# Design Spec: `vibe-heal review` Command

**Date:** 2026-05-11
**Status:** Approved

## Overview

A new `vibe-heal review` command that runs a fresh SonarQube analysis on the current branch, filters findings to only lines changed in the PR, and saves a structured report. A separate `--post` flag submits the report as inline GitHub PR review comments via the `gh` CLI.

This is a read-only workflow — no code is modified.

## Problem Statement

The existing `cleanup` and `dedupe-branch` commands fix code in place. When reviewing someone else's PR (or reviewing before fixing), users need to:

1. Analyze what SonarQube issues exist on changed lines only (not pre-existing issues on untouched code)
2. Save the findings in a reusable format
3. Optionally submit findings to the PR author as inline code review comments

## User Workflow

```
# Step 1: Analyze and generate report
vibe-heal review

# Step 2: Inspect the report, then post to GitHub
vibe-heal review --post

# Variations
vibe-heal review --base-branch origin/dev
vibe-heal review --post --pr 42
```

## Architecture

### Data Flow

```
vibe-heal review
    ├─ BranchAnalyzer       → modified files + current branch name
    ├─ DiffParser           → {file: set[int]} changed line numbers
    ├─ ProjectManager       → create_temp_project()
    ├─ AnalysisRunner       → run_analysis() + poll for completion
    ├─ SonarQubeClient      → get_issues_for_file() per modified file
    ├─ IssueLineFilter      → keep only issues on changed lines
    ├─ Reporter             → write review.json + review.md
    └─ ProjectManager       → delete_project() (always, in finally block)

vibe-heal review --post
    ├─ GitHubReviewClient   → detect_pr() via `gh pr view`
    └─ GitHubReviewClient   → post_review_comments() via `gh api`
```

The two steps are fully decoupled. `--post` reads the saved JSON report and does not re-run analysis.

### Changed-Line Detection

Changed lines are determined by **git diff** (primary source of truth), cross-checked against SonarQube's `isNew` flag. The filter uses the git diff result; discrepancies with `isNew` are logged at DEBUG level for observability but do not affect filtering.

`DiffParser` lives in `src/vibe_heal/git/diff_parser.py` (git module, not review-specific) and returns `dict[str, set[int]]` mapping repo-relative file paths to changed line numbers.

### Temporary Project

Like `cleanup` and `dedupe-branch`, `review` creates a temporary SonarQube project for the branch, runs a fresh `sonar-scanner` analysis, fetches results, then deletes the project. This ensures findings reflect the exact state of the branch. Cleanup always runs in a `finally` block.

### Report Storage

Reports are saved to `~/.vibe-heal/reviews/<project-key>/<branch-name>/` — outside the repository to avoid polluting the working tree or accidentally committing analysis artifacts.

- `review.json` — full `ReviewResult` serialized
- `review.md` — human-readable table per file

An optional `--report-file` flag overrides the output path.

## New Modules

### `src/vibe_heal/review/`

| File | Responsibility |
|------|---------------|
| `orchestrator.py` | `ReviewOrchestrator` — drives the analyze and post phases |
| `diff_parser.py` | *(moved to `git/`)* |
| `line_filter.py` | `IssueLineFilter` — filters issues to changed lines |
| `reporter.py` | `Reporter` — serializes `ReviewResult` to JSON and markdown |
| `github.py` | `GitHubReviewClient` — wraps `gh` CLI for PR detection and posting |
| `models.py` | `ReviewIssue`, `FileReview`, `ReviewResult` |
| `__init__.py` | Public exports |

### `src/vibe_heal/git/diff_parser.py` (new file in existing module)

`DiffParser` class: runs `git diff <base>...HEAD` via GitPython and parses unified diff into `dict[str, set[int]]`.

### No changes to existing modules

`cleanup/`, `deduplication/`, `orchestrator.py`, `sonarqube/`, and `git/manager.py` are untouched.

## Models

```python
# review/models.py

class ReviewIssue(BaseModel):
    rule: str
    message: str
    line: int
    severity: str
    doc_url: str          # pre-resolved SonarQubeRule.public_doc_url
    is_new_in_sonar: bool # SonarQube isNew cross-check value

class FileReview(BaseModel):
    file_path: str
    issues: list[ReviewIssue]

class ReviewResult(BaseModel):
    project_key: str
    branch: str
    base_branch: str
    generated_at: datetime
    files: list[FileReview]

    @property
    def total_issues(self) -> int: ...
```

## GitHub Posting

`GitHubReviewClient` wraps the `gh` CLI — no GitHub token management needed.

**PR detection order:**
1. `gh pr view --json number,baseRefName` on the current branch
2. If unavailable (no open PR, `gh` not logged in): warn and exit cleanly; don't fail

**Posting mechanism:**
All inline comments are submitted as a single GitHub PR review (one `gh api` call to `POST /repos/{owner}/{repo}/pulls/{pr}/reviews`) rather than N separate API calls. This produces one review event in the PR timeline.

**Inline comment body:**
```
**[python:S1481]** Variable 'foo' is declared but never used.

📖 [Rule documentation](https://next.sonarqube.com/sonarqube/coding_rules?open=python:S1481&rule_key=python:S1481)
```

**Line outside diff context:**
GitHub rejects inline comments on lines not present in the PR diff. These issues are collected and posted as a single top-level fallback comment listing them. The review is not aborted.

## CLI Interface

```
vibe-heal review [OPTIONS]

Options:
  --post                    Post saved report to GitHub PR as inline comments
  --pr INTEGER              GitHub PR number (overrides auto-detection)
  --base-branch TEXT        Base branch to compare against [default: origin/main]
  --pattern TEXT            File patterns to filter (repeatable, e.g. '*.py')
  --report-file PATH        Override default report output path
  --env-file TEXT           Path to custom environment file
  --verbose / -v            Verbose output
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `sonar-scanner` not installed | Clear error with install link (same as `AnalysisRunner`) |
| Temp project cleanup fails | Logged as warning; never silently swallowed |
| `gh` not installed | Distinct error with install instructions |
| `gh` not authenticated | Distinct error: "Run `gh auth login`" |
| GitHub rejects inline comment (line outside diff) | Collected; posted as fallback top-level comment |
| No issues found on changed lines | Clean exit: "No issues found on changed lines" |
| No open PR for current branch | Print report path, warn, exit cleanly |

## Testing

Mirrors existing test patterns (pytest + unittest.mock):

| Test file | Covers |
|-----------|--------|
| `tests/git/test_diff_parser.py` | `DiffParser` with fixture diff strings |
| `tests/review/test_line_filter.py` | Filter logic; `isNew` discrepancy logging |
| `tests/review/test_reporter.py` | JSON and markdown output shape |
| `tests/review/test_github.py` | PR detection fallback; fallback comment path; mocked `gh` calls |
| `tests/review/test_orchestrator.py` | Integration-style with mocked client, runner, project manager |

No new test infrastructure required.

## Out of Scope

- AI-generated fix suggestions in review comments (no AI tool calls in review mode)
- Severity filtering (all issues on changed lines are included)
- Modifying any code
- Posting to non-GitHub forges (GitLab, Bitbucket)
