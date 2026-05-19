# `vibe-heal review` Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a `vibe-heal review` command that analyzes SonarQube issues on changed lines only, saves structured reports, and optionally posts them as GitHub PR review comments.

**Architecture:** New `review/` module with models, line filter, reporter, GitHub client, and orchestrator. New `DiffParser` in `git/`. Two-phase CLI: analyze (default) and `--post` (reads saved report, posts to GitHub).

**Tech Stack:** Python, Pydantic, GitPython, subprocess (for `gh` CLI), typer, rich, pytest + unittest.mock

**Convention Reference:**
- Mocking: patch at the importing module, e.g., `patch("vibe_heal.git.diff_parser.Repo")`
- Subprocess: `stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL` when output not consumed
- Async: `asyncio.create_subprocess_exec` for non-blocking execution
- Retry loops: collect `last_error`, `break`, then `assert last_error is not None; raise last_error`
- Tests: pytest + `@pytest.mark.asyncio` for async tests, `AsyncMock` for async methods
- Type annotations: required on all functions (mypy strict mode)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/vibe_heal/review/__init__.py` | Public exports |
| Create | `src/vibe_heal/review/models.py` | ReviewIssue, FileReview, ReviewResult |
| Create | `src/vibe_heal/git/diff_parser.py` | DiffParser — git diff to {file: set[int]} |
| Create | `src/vibe_heal/review/line_filter.py` | IssueLineFilter — filter issues to changed lines |
| Create | `src/vibe_heal/review/reporter.py` | Reporter — writes review.json + review.md |
| Create | `src/vibe_heal/review/github.py` | GitHubReviewClient — wraps gh CLI |
| Create | `src/vibe_heal/review/orchestrator.py` | ReviewOrchestrator — drives analyze/post |
| Modify | `src/vibe_heal/git/__init__.py` | Export DiffParser |
| Modify | `src/vibe_heal/cli.py` | Add review command |
| Create | `tests/review/__init__.py` | Test package |
| Create | `tests/review/test_models.py` | Model tests |
| Create | `tests/git/test_diff_parser.py` | DiffParser tests |
| Create | `tests/review/test_line_filter.py` | Line filter tests |
| Create | `tests/review/test_reporter.py` | Reporter tests |
| Create | `tests/review/test_github.py` | GitHub client tests |
| Create | `tests/review/test_orchestrator.py` | Orchestrator tests |

---

### Task 1: Review Models

**Files:**
- Create: `src/vibe_heal/review/models.py`
- Create: `src/vibe_heal/review/__init__.py`
- Create: `tests/review/__init__.py`
- Create: `tests/review/test_models.py`

- [ ] **Step 1:** Write `tests/review/__init__.py` (empty docstring)
- [ ] **Step 2:** Write `tests/review/test_models.py` — tests for all three models including serialization round-trip
- [ ] **Step 3:** Run `uv run pytest tests/review/test_models.py -v` — expect FAIL (import error)
- [ ] **Step 4:** Write `src/vibe_heal/review/models.py` with `ReviewIssue`, `FileReview`, `ReviewResult`
- [ ] **Step 5:** Write `src/vibe_heal/review/__init__.py` exporting the three models
- [ ] **Step 6:** Run tests — expect PASS, run `uv run ruff check` and `uv run mypy` on new files
- [ ] **Step 7:** Commit: `feat: add review command models`

Key model details:
- `ReviewIssue`: rule, message, line, severity, doc_url, is_new_in_sonar
- `FileReview`: file_path, issues list
- `ReviewResult`: project_key, branch, base_branch, generated_at (datetime), files list, total_issues property

---

### Task 2: DiffParser

**Files:**
- Create: `src/vibe_heal/git/diff_parser.py`
- Modify: `src/vibe_heal/git/__init__.py` — add DiffParser, DiffParserError to exports
- Create: `tests/git/test_diff_parser.py`

- [ ] **Step 1:** Write `tests/git/test_diff_parser.py` with fixture diff strings covering: simple addition, pure deletion, modification (del+add), multiple hunks, multiple files, empty diff, binary file ignored
- [ ] **Step 2:** Run tests — expect FAIL (import error)
- [ ] **Step 3:** Write `src/vibe_heal/git/diff_parser.py`
- [ ] **Step 4:** Update `src/vibe_heal/git/__init__.py`
- [ ] **Step 5:** Run tests — expect PASS, run linter/type checker
- [ ] **Step 6:** Commit: `feat: add DiffParser for changed-line detection`

DiffParser details:
- Uses `git diff --unified=0 <base>...HEAD` (three-dot, no context lines)
- Parses unified diff: extracts filenames from `diff --git` lines, line numbers from `@@` headers
- Tracks `new_line` counter per hunk: increments on `+` and ` ` (context) lines, not on `-` lines
- Returns `dict[str, set[int]]` — file paths to sets of added/modified line numbers in HEAD
- Pure deletions produce empty sets for that hunk

---

### Task 3: IssueLineFilter

**Files:**
- Create: `src/vibe_heal/review/line_filter.py`
- Create: `tests/review/test_line_filter.py`

- [ ] **Step 1:** Write tests covering: filter keeps issues on changed lines, discards issues on unchanged lines, empty changed lines returns empty, multiple issues same line, is_new_in_sonar flag population, isNew discrepancy logging at DEBUG level
- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Write `src/vibe_heal/review/line_filter.py`
- [ ] **Step 4:** Run tests — expect PASS, run linter/type checker
- [ ] **Step 5:** Commit: `feat: add IssueLineFilter for changed-line filtering`

LineFilter details:
- `filter_issues(issues, changed_lines, source_is_new_map)` method
- Takes SonarQubeIssue list, changed line set, and optional is_new lookup
- Returns list[ReviewIssue] — only issues where line is in changed_lines
- Populates is_new_in_sonar from source line data when available
- Logs DEBUG discrepancy when git diff says changed but SonarQube isNew disagrees

---

### Task 4: Reporter

**Files:**
- Create: `src/vibe_heal/review/reporter.py`
- Create: `tests/review/test_reporter.py`

- [ ] **Step 1:** Write tests covering: JSON write/read round-trip, markdown table format, default report path construction, custom report path override, empty result produces valid files
- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Write `src/vibe_heal/review/reporter.py`
- [ ] **Step 4:** Run tests — expect PASS, run linter/type checker
- [ ] **Step 5:** Commit: `feat: add Reporter for JSON/markdown report generation`

Reporter details:
- `default_report_dir(project_key, branch)` returns `~/.vibe-heal/reviews/<project-key>/<branch>/`
- `write_reports(result, report_dir)` creates directory, writes review.json and review.md
- `load_report(report_dir)` reads review.json, returns ReviewResult
- Markdown: summary header with totals, per-file markdown tables with rule/message/line/severity columns

---

### Task 5: GitHubReviewClient

**Files:**
- Create: `src/vibe_heal/review/github.py`
- Create: `tests/review/test_github.py`

- [ ] **Step 1:** Write tests covering: gh_not_installed error, gh_not_authenticated error, pr_auto_detection, pr_explicit_number, post_review_single_api_call, inline_comment_format, fallback_comment_for_rejected_lines
- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Write `src/vibe_heal/review/github.py`
- [ ] **Step 4:** Run tests — expect PASS, run linter/type checker
- [ ] **Step 5:** Commit: `feat: add GitHubReviewClient for PR posting`

GitHubReviewClient details:
- All methods use `asyncio.create_subprocess_exec` with `gh` CLI
- `validate_installed()` — runs `gh --version`, raises OSError with install instructions
- `detect_pr(pr_number)` — if pr_number given, return it; else `gh pr view --json number` on current branch
- `post_review(pr_number, report)` — builds payload, single `gh api POST /repos/{owner}/{repo}/pulls/{pr}/reviews` call
- Inline comment body format: `[bold rule] message\n\nRule documentation link`
- Collects rejected lines (GitHub API 404/422 for line outside diff), posts as fallback top-level comment
- Parses owner/repo from `gh repo view owner,name` or git remote URL

---

### Task 6: ReviewOrchestrator

**Files:**
- Create: `src/vibe_heal/review/orchestrator.py`
- Create: `tests/review/test_orchestrator.py`

- [ ] **Step 1:** Write tests covering: analyze phase (no modified files, analysis fails, no issues on changed lines, full happy path), post phase (reads saved report, delegates to GitHub client), temp project cleanup in finally block
- [ ] **Step 2:** Run tests — expect FAIL
- [ ] **Step 3:** Write `src/vibe_heal/review/orchestrator.py`
- [ ] **Step 4:** Update `src/vibe_heal/review/__init__.py` to export ReviewOrchestrator and ReviewResult
- [ ] **Step 5:** Run tests — expect PASS, run linter/type checker
- [ ] **Step 6:** Commit: `feat: add ReviewOrchestrator`

Orchestrator details:
- Dependencies: BranchAnalyzer, DiffParser, ProjectManager, AnalysisRunner, SonarQubeClient, IssueLineFilter, Reporter, GitHubReviewClient
- `run_analysis(base_branch, file_patterns, report_file, verbose)` — analyze phase:
  1. Get modified files from BranchAnalyzer
  2. Filter by patterns if specified
  3. Get changed lines from DiffParser
  4. Create temp project, copy exclusion settings
  5. Run analysis (sonar-scanner)
  6. For each modified file: fetch issues, filter to changed lines
  7. Build ReviewResult, write reports via Reporter
  8. Delete temp project in finally block
- `run_post(report_file, pr_number, verbose)` — post phase:
  1. Load report from JSON
  2. Detect or use explicit PR number
  3. Post review comments via GitHubReviewClient
- No AI tool calls — this is read-only

---

### Task 7: CLI Command

**Files:**
- Modify: `src/vibe_heal/cli.py`

- [ ] **Step 1:** Add `review` command to `cli.py` following the existing `cleanup` command pattern
- [ ] **Step 2:** Add imports for ReviewOrchestrator, ReviewResult, and report models
- [ ] **Step 3:** Implement `review` CLI function with options: --post, --pr, --base-branch, --pattern, --report-file, --env-file, --verbose
- [ ] **Step 4:** Implement display helper for review results (summary table)
- [ ] **Step 5:** Add tests to `tests/test_cli.py` for the new command
- [ ] **Step 6:** Run all tests, run linter/type checker
- [ ] **Step 7:** Commit: `feat: add vibe-heal review CLI command`

CLI interface (matching spec exactly):
```
vibe-heal review [OPTIONS]
  --post              Post saved report to GitHub PR
  --pr INTEGER        GitHub PR number (override auto-detection)
  --base-branch TEXT  Base branch [default: origin/main]
  --pattern TEXT      File patterns (repeatable)
  --report-file PATH  Override report output path
  --env-file TEXT     Custom environment file
  --verbose / -v      Verbose output
```

When `--post`: skip analysis, load saved report, post to GitHub
Without `--post`: run analysis, save report, print summary

---

### Task 8: Final Verification

- [ ] **Step 1:** Run full test suite: `make test`
- [ ] **Step 2:** Run full check: `make check`
- [ ] **Step 3:** Verify CLI help: `uv run vibe-heal review --help`
- [ ] **Step 4:** Commit any final fixes: `fix: address lint/typecheck issues from review command`

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] DiffParser in `git/` module — Task 2
- [x] IssueLineFilter with isNew cross-check — Task 3
- [x] Review models (ReviewIssue, FileReview, ReviewResult) — Task 1
- [x] Reporter with JSON + markdown output — Task 4
- [x] GitHubReviewClient with gh CLI wrapping — Task 5
- [x] ReviewOrchestrator with analyze and post phases — Task 6
- [x] CLI command with all spec options — Task 7
- [x] Report storage outside repo (~/.vibe-heal/reviews/) — Task 4
- [x] --post reads saved JSON, does not re-run analysis — Task 6, 7
- [x] Temporary project lifecycle with finally cleanup — Task 6
- [x] No code modifications (read-only) — Task 6
- [x] Single API call for review posting — Task 5
- [x] Fallback top-level comment for rejected lines — Task 5
- [x] Error handling table scenarios — Tasks 5, 6

**2. Placeholder scan:** `FileDiagnostics` in `models.py` is retained as intentional scaffolding for debugging the diff/SonarQube path mapping pipeline.

**3. Type consistency:**
- DiffParser returns `dict[str, set[int]]` — used by IssueLineFilter
- IssueLineFilter returns `list[ReviewIssue]` — used by orchestrator to build FileReview
- ReviewResult model used by Reporter for serialization and deserialization
- ReviewOrchestrator.run_analysis returns ReviewAnalysisResult
- ReviewOrchestrator.run_post takes ReviewResult, delegates to GitHubReviewClient
