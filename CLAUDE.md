# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**vibe-heal** is an AI-powered SonarQube issue remediation tool that automatically fixes code quality problems. The project is initialized from the cookiecutter-uv template and uses modern Python tooling.

## Development Environment

This project uses **uv** as the package manager (not pip or poetry). All Python commands should be run via `uv run`.

### Initial Setup

```bash
make install  # Sets up environment and pre-commit hooks
```

This command:
- Creates virtual environment with `uv sync`
- Installs pre-commit hooks

## Common Commands

### Testing

```bash
# Run all tests with coverage
make test

# Run tests manually
uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

# Run tests across multiple Python versions (requires multiple Python installations)
tox
```

Test files are located in `tests/` directory. When writing tests, remember that `tests/*` files have S101 (assert usage) ignored in ruff configuration.

### Code Quality

```bash
# Run all quality checks (recommended before committing)
make check

# Run pre-commit hooks manually
uv run pre-commit run -a

# Type checking with mypy
uv run mypy

# Check for obsolete dependencies
uv run deptry src
```

### Linting & Formatting

The project uses **ruff** for linting and formatting (not black or flake8). Configuration is in `pyproject.toml`:
- Line length: 120 characters
- Target Python version: 3.11+
- Auto-fix enabled

Pre-commit hooks will automatically run ruff-check and ruff-format on commits.

### Documentation

```bash
# Build and serve docs locally
make docs

# Test documentation build
make docs-test
```

Documentation uses MkDocs with Material theme. Configuration is in `mkdocs.yml`.

### Building

```bash
# Build wheel file
make build

# Clean build artifacts
make clean-build
```

Build uses hatchling as the backend. Package source is in `src/vibe_heal/`.

## Project Structure

- **`src/vibe_heal/`**: Main package source code
- **`tests/`**: Test files (pytest)
- **`docs/`**: MkDocs documentation source
- **`pyproject.toml`**: Project configuration, dependencies, and tool settings
- **`Makefile`**: Common development commands
- **`tox.ini`**: Multi-version Python testing configuration

## Type Checking

mypy is configured with strict settings:
- `disallow_untyped_defs = true`
- `disallow_any_unimported = true`
- Only checks files in `src/`

All functions should have type annotations.

## Testing Philosophy

- Tests should have coverage (`pytest-cov` is configured)
- Coverage reports are generated as XML for codecov integration
- Test discovery uses `testpaths = ["tests"]` in pytest configuration

## Dependencies

Development dependencies are defined in `[dependency-groups]` in `pyproject.toml`. To add dependencies:

```bash
# Add a runtime dependency
uv add <package>

# Add a dev dependency
uv add --dev <package>
```

## CI/CD

The project has GitHub Actions workflows for:
- Main workflow on pull requests and pushes to main
- Release workflow when creating releases
- Codecov validation

Workflows use `uv` and are configured in `.github/workflows/`.

## Python Version Support

Supports Python 3.11 through 3.13. The `tox.ini` configuration tests against all these versions.

---

## vibe-heal Specific Architecture

### What is vibe-heal?

vibe-heal is an AI-powered SonarQube issue remediation tool that automatically fixes code quality problems using AI coding assistants (Claude Code or Aider).

**Core Workflow**:
1. Fetch SonarQube issues for a file
2. Sort issues in reverse line order (high to low - prevents line number shifts)
3. For each issue: invoke AI tool → if successful, create git commit
4. Display summary report

**Current Status**: Phases 0-6 complete (141 tests, 82% coverage). Core workflow is working end-to-end!

### High-Level Architecture

```
CLI Layer (cli.py)
    ↓
Orchestrator (orchestrator.py) - coordinates entire workflow
    ↓
├─ Config (config/) - loads .env.vibeheal
├─ SonarQubeClient (sonarqube/) - fetches issues via API
├─ IssueProcessor (processor/) - sorts/filters issues
├─ AITool (ai_tools/) - fixes issues (ClaudeCodeTool implemented)
└─ GitManager (git/) - creates commits
```

### Module Responsibilities

**`config/`**: Pydantic-based configuration from `.env.vibeheal` or `.env`
- `VibeHealConfig` model with validation
- Supports token auth (preferred) or basic auth
- AI tool auto-detection if not specified
- Supports custom env file via `env_file` parameter in constructor
- CLI commands accept `--env-file` option to override default config file

**`sonarqube/`**: Async HTTP client for SonarQube Web API
- `SonarQubeClient.get_issues_for_file(file_path)` - uses `components` parameter for file-specific queries
- `SonarQubeClient.create_project(key, name)` - creates new SonarQube project
- `SonarQubeClient.delete_project(key)` - deletes SonarQube project
- `SonarQubeClient.project_exists(key)` - checks if project exists
- `SonarQubeIssue` model - supports both old and new SonarQube API formats
- Uses `httpx` for async requests
- `ProjectManager` - manages temporary project lifecycle for branch cleanup
  - `create_temp_project(base_key, branch_name, user_email)` - creates uniquely named temp project
  - Project key format: `{base_key}_{sanitized_email}_{sanitized_branch}_{timestamp}`
  - Timestamp format: `yymmdd-hhmm` (e.g., `251024-1630`)
  - Example: `my-project_user_example_com_feature_api_251024-1630`
  - `delete_project(project_key)` - deletes temporary project
  - `project_exists(project_key)` - checks project existence
  - `_sanitize_identifier(value)` - sanitizes strings for project keys (alphanumeric + underscore, lowercase)
  - `TempProjectMetadata` model - tracks created projects for cleanup
- `AnalysisRunner` - executes SonarQube analysis via sonar-scanner CLI
  - `run_analysis(project_key, project_name, project_dir, sources)` - runs scanner and waits for completion
  - Uses `asyncio.create_subprocess_exec` for non-blocking execution
  - Polls `/api/ce/task?id={taskId}` to wait for server-side analysis completion
  - `validate_scanner_available()` - checks if sonar-scanner is installed
  - `AnalysisResult` model - returns success status, task_id, dashboard_url, error details
  - Supports both token and basic auth
  - Optional sources parameter for partial analysis optimization
  - **Requirement**: `sonar-scanner` CLI must be installed (https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/)

**`processor/`**: Business logic for issue handling
- Sorts issues by line number descending (fixes high line numbers first)
- Filters by fixability (`is_fixable` property checks for line number, non-resolved status)
- Supports severity filtering and max issue limits

**`ai_tools/`**: Abstract interface + implementations
- `AITool` ABC with `fix_issue()` method
- `AIToolType` enum (CLAUDE_CODE, AIDER)
- `ClaudeCodeTool` - invokes `claude` CLI with `--print --output-format json`
- `AIToolFactory` with auto-detection (tries Claude Code first)
- `FixResult` model for fix outcomes

**`git/`**: Git operations via GitPython
- `GitManager.commit_fix()` - creates conventional commits
- Commit format: `fix: [SQ-RULE] message` with full issue details in body
- Validates file has no uncommitted changes before processing
- Each fix gets its own commit (easy rollback)
- `BranchAnalyzer` - analyzes branch differences for branch cleanup feature
  - `get_modified_files(base_branch='origin/main')` - returns files modified vs base branch
  - Uses git three-dot diff syntax to compare from merge base
  - Filters out deleted files, returns only existing files
  - `get_current_branch()` - returns active branch name
  - `validate_branch_exists(branch)` - checks local and remote branches
  - `get_user_email()` - retrieves git user email for project naming

**`orchestrator.py`**: Main workflow coordination
- `VibeHealOrchestrator.fix_file()` - end-to-end flow for fixing a single file
- Validates preconditions (git state, file exists, AI tool available)
- Progress indicators with rich library
- User confirmation before processing (unless dry-run)

**`cleanup/`**: Branch cleanup workflow
- `CleanupOrchestrator` - orchestrates branch cleanup workflow
  - `cleanup_branch(base_branch, max_iterations, file_patterns)` - cleans up all modified files
  - Workflow: analyze branch → create temp project → run analysis → fix files iteratively → delete temp project
  - `_cleanup_file(file_path, project_key, project_name, max_iterations)` - fixes single file until no issues remain
  - Reuses `VibeHealOrchestrator.fix_file()` for actual fixing
  - `_filter_files(files, patterns)` - filters files by glob patterns
  - `CleanupResult` model - tracks overall cleanup results
  - `FileCleanupResult` model - tracks per-file cleanup results
  - Always cleans up temporary project in finally block
  - Supports file pattern filtering (e.g., `["*.py", "src/**/*.ts"]`)

**`cli.py`**: Command-line interface with typer
- `vibe-heal fix <file>` - fix issues in a single file
  - Flags: `--dry-run`, `--max-issues`, `--min-severity`, `--ai-tool`, `--env-file`, `--verbose`
- `vibe-heal cleanup` - clean up all modified files in current branch
  - Flags: `--base-branch` (default: origin/main), `--max-iterations` (default: 10), `--pattern` (file filters), `--ai-tool`, `--env-file`, `--verbose`
  - Creates temporary SonarQube project, runs analysis, fixes issues iteratively
  - Displays per-file results with issues fixed counts
- `vibe-heal config` - shows current configuration
  - Flags: `--env-file`
- `vibe-heal version` - shows version information
- Uses rich for beautiful terminal output with colors and formatting

### Critical Implementation Details

**Reverse Line Order**: Issues are fixed from highest line number to lowest. This prevents line number shifts from earlier fixes affecting later fixes.

**Component Path Construction**: SonarQube API queries use `components=projectkey:filepath` (lowercase project key). The old approach of querying with `componentKeys` and filtering client-side was incorrect.

**Issue Status Filtering**: Use `issueStatuses=OPEN,CONFIRMED` instead of `resolved=false` for more precise filtering.

**Git Safety**: Only checks that the specific file being fixed has no uncommitted changes. Other files can have changes (requirement was relaxed from "clean working directory").

**Async/Await**: SonarQube client and AI tool operations use async/await pattern. CLI wraps with `asyncio.run()`.

**AI Tool Integration**: Claude Code is invoked with permission mode `acceptEdits` and tool restriction to `Edit,Read` only for security. Uses `--print` and `--output-format json` flags.

### Configuration (.env.vibeheal)

By default, configuration is loaded from `.env.vibeheal` or `.env` in the current directory.

```bash
SONARQUBE_URL=https://sonar.example.com
SONARQUBE_TOKEN=your_token  # Preferred
# OR: SONARQUBE_USERNAME + SONARQUBE_PASSWORD
SONARQUBE_PROJECT_KEY=your_project
# AI_TOOL=claude-code  # Optional, auto-detects if not set

# Context enrichment (optional, enhances AI fix quality)
# CODE_CONTEXT_LINES=5  # Lines before/after issue to show AI (default: 5)
# INCLUDE_RULE_DESCRIPTION=true  # Include full rule docs in prompts (default: true)
```

**Custom environment files**: All CLI commands support `--env-file` to specify a custom configuration file:

```bash
vibe-heal fix src/file.py --env-file .env.production
vibe-heal cleanup --env-file ~/configs/project-a.env
vibe-heal config --env-file .env.staging
```

### Development Workflow

**Running vibe-heal locally**:
```bash
# Install in development mode
uv pip install -e .

# Test with actual SonarQube (requires .env.vibeheal)
vibe-heal config  # Verify configuration
vibe-heal fix src/file.py --dry-run  # Preview
vibe-heal fix src/file.py --max-issues 1  # Fix one issue
```

**Testing specific modules**:
```bash
# Run specific test file
uv run pytest tests/sonarqube/test_client.py -v

# Run with one test function
uv run pytest tests/sonarqube/test_client.py::TestSonarQubeClient::test_get_issues_for_file -v

# Run tests for one module with coverage
uv run pytest tests/processor/ -v --cov=src/vibe_heal/processor
```

### Common Development Patterns

**Adding a new AI tool**:
1. Create `src/vibe_heal/ai_tools/new_tool.py` implementing `AITool` ABC
2. Add to `AIToolType` enum in `base.py`
3. Update `AIToolFactory._tool_map`
4. Add tests in `tests/ai_tools/test_new_tool.py`

**Modifying SonarQube API queries**:
- Client is in `src/vibe_heal/sonarqube/client.py`
- Models support both old and new API formats (use `model_config = {"extra": "ignore"}`)
- Test fixtures are in `tests/sonarqube/fixtures/api_responses.json`

**Changing commit message format**:
- Logic is in `GitManager._create_commit_message()` in `src/vibe_heal/git/manager.py`
- Tests verify format in `tests/git/test_manager.py`

### Next Planned Features

Phase 7 (Safety Features):
- Backup/rollback mechanisms
- Enhanced validation

Phase 8 (Aider Integration):
- Implement `AiderTool` class
- Update auto-detection to try both tools

Future enhancements:
- Fetch issue documentation from SonarQube API and include in AI prompt
- Multi-file processing
- Custom commit message templates
