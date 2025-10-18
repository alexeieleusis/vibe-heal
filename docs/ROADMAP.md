# vibe-heal Development Roadmap

## Product Vision

vibe-heal is an AI-powered SonarQube issue remediation tool that automatically fixes code quality problems by integrating with AI coding assistants like Claude Code and Aider.

## V1 Scope: Single File Issue Remediation

### Core User Flow

1. User runs: `vibe-heal fix <file_path>`
2. Tool fetches all SonarQube issues for that file
3. Issues are sorted in reverse line number order
4. For each issue:
   - AI tool is invoked with issue context
   - If fix succeeds, create a git commit
   - Continue to next issue
5. Summary report shown at end

## Development Phases

### Phase 0: Project Setup ✅ COMPLETE

- [x] Initialize project with cookiecutter-uv
- [x] Create CLAUDE.md
- [x] Add core dependencies
- [x] Set up project structure

**Status**: Complete - All dependencies installed, project structure created, documentation in place.

### Phase 1: Configuration Management ✅ COMPLETE

**Goal**: Support flexible configuration via environment variables and config files

**Tasks**:
- [x] Add dependencies: `python-dotenv`, `pydantic`, `pydantic-settings`
- [x] Create `VibeHealConfig` class using pydantic-settings
- [x] Support `.env` and `.env.vibeheal` files
- [x] Define configuration schema:
  - `SONARQUBE_URL` (required)
  - `SONARQUBE_TOKEN` (optional, preferred)
  - `SONARQUBE_USERNAME` + `SONARQUBE_PASSWORD` (optional, alternative)
  - `SONARQUBE_PROJECT_KEY` (required)
  - `AI_TOOL` (optional, default: auto-detect)
- [x] Configuration validation on load
- [x] Unit tests for config loading and validation (28 tests, 97% coverage)

**Deliverable**: ✅ Configuration can be loaded and validated from environment

### Phase 2: SonarQube API Integration ✅ COMPLETE

**Goal**: Retrieve issues for a specific file from SonarQube

**Tasks**:
- [x] Add dependency: `httpx` (async HTTP client)
- [x] Create `SonarQubeClient` class
- [x] Implement authentication (token-based and basic auth)
- [x] Implement `get_issues_for_file(file_path)` method
- [x] Create Pydantic models for SonarQube responses:
  - `SonarQubeIssue` (key, rule, message, severity, line, component)
  - `IssuesResponse`
- [x] Handle pagination
- [x] Error handling for API failures
- [x] Unit tests with mocked API responses (29 tests, 92% coverage)
- [x] Validated with real SonarQube API response
- [x] Support both old and new SonarQube API formats

**Deliverable**: ✅ Can fetch and parse issues from SonarQube API

### Phase 3: Issue Processing Engine

**Goal**: Sort and prepare issues for fixing

**Tasks**:
- [ ] Create `IssueProcessor` class
- [ ] Implement reverse line number sorting
- [ ] Implement issue filtering logic:
  - Skip issues without line numbers
  - Skip issues marked as won't fix/false positive
  - (Future) Filter by severity
- [ ] Create `FixableIssue` model with all context needed for AI
- [ ] Unit tests for sorting and filtering

**Deliverable**: Issues can be sorted and filtered for processing

### Phase 4: AI Tool Integration (Abstract + Claude Code)

**Goal**: Abstract interface for AI tools + first implementation

**Tasks**:
- [ ] Create abstract base class `AITool` with interface:
  - `is_available() -> bool` (check if tool is installed)
  - `fix_issue(issue: FixableIssue, file_path: str) -> FixResult`
- [ ] Create `FixResult` model (success, error_message, changes_made)
- [ ] Implement `ClaudeCodeTool`:
  - Detect if Claude Code is available
  - Format prompt with issue context
  - Invoke Claude Code via CLI
  - Parse result
- [ ] Create prompt template for issue fixing
- [ ] Unit tests for tool detection
- [ ] Integration tests (require Claude Code installed)

**Deliverable**: Can invoke Claude Code to fix an issue

### Phase 5: Git Integration

**Goal**: Create commits after each successful fix

**Tasks**:
- [ ] Add dependency: `GitPython`
- [ ] Create `GitManager` class
- [ ] Implement `is_repo() -> bool`
- [ ] Implement `is_clean() -> bool` (no uncommitted changes)
- [ ] Implement `create_commit(message: str, files: list[str])`
- [ ] Define commit message template:
  ```
  fix: [SQ-{issue_key}] {rule_name}

  Fixes SonarQube issue on line {line}
  Rule: {rule}
  Message: {message}

  Fixed by vibe-heal using {ai_tool}
  ```
- [ ] Safety check: refuse to run if working directory is dirty
- [ ] Unit tests with temporary git repos

**Deliverable**: Can create commits after fixes

### Phase 6: Main CLI & Orchestration

**Goal**: Wire everything together into a working CLI

**Tasks**:
- [ ] Add dependency: `typer` (CLI framework), `rich` (beautiful output)
- [ ] Create main CLI with `fix` command
- [ ] Implement orchestration in `VibeHealOrchestrator`:
  1. Load configuration
  2. Validate git repo is clean
  3. Initialize SonarQube client
  4. Fetch issues for file
  5. Sort and filter issues
  6. For each issue:
     - Invoke AI tool
     - If successful, commit
     - Show progress
  7. Display summary report
- [ ] Add progress indicators (rich.progress)
- [ ] Add summary report (fixed/skipped/failed)
- [ ] Basic error handling

**Deliverable**: Working end-to-end `vibe-heal fix <file>` command

### Phase 7: Safety & Error Handling

**Goal**: Make the tool safe and robust

**Tasks**:
- [ ] Implement `--dry-run` mode (show what would be fixed, no commits)
- [ ] Add confirmation prompt before starting (show issue count)
- [ ] File path validation (exists, in project)
- [ ] Rollback mechanism if AI tool fails
- [ ] Add `--max-issues N` flag to limit fixes per run
- [ ] Better error messages
- [ ] Add `--verbose` flag for debug logging
- [ ] Set up logging with `structlog` or standard logging

**Deliverable**: Tool is safe to use in production repos

### Phase 8: Aider Integration

**Goal**: Support second AI tool

**Tasks**:
- [ ] Implement `AiderTool` class
- [ ] Auto-detection logic (try Claude Code first, fall back to Aider)
- [ ] Allow explicit tool selection via config
- [ ] Tests for Aider integration

**Deliverable**: Can use Aider as alternative to Claude Code

### Phase 9: Validation & Testing

**Goal**: Ensure fixes actually work

**Tasks**:
- [ ] Optional: Run tests after each fix (`--run-tests` flag)
- [ ] Optional: Syntax validation before committing
- [ ] Optional: Re-check SonarQube to verify issue is resolved
- [ ] Comprehensive integration tests
- [ ] Update documentation

**Deliverable**: High confidence that fixes work correctly

## Future Enhancements (Post-V1)

### V2: Multi-File Support
- Process all files in project
- Parallel processing
- Better filtering options

### V3: Advanced Features
- Issue filtering by severity/type
- Custom commit message templates
- Branch management (auto-create feature branch)
- Integration with CI/CD
- Web UI for monitoring
- Support for more AI tools

## Success Metrics

- Can fix at least 80% of auto-fixable SonarQube issues
- No commits that break tests
- Clear, informative commit messages
- Works with both Claude Code and Aider
- Easy to configure and use

## Dependencies Overview

**Core**:
- `python-dotenv` - Environment variable loading
- `pydantic` + `pydantic-settings` - Configuration management
- `httpx` - SonarQube API client
- `typer` - CLI framework
- `rich` - Beautiful terminal output
- `GitPython` - Git operations

**Development**:
- Already have: pytest, mypy, ruff, pre-commit
- May add: `pytest-mock`, `responses` (HTTP mocking)

## Risk Mitigation

1. **AI fixes break code**: Require clean git state, create commits per fix (easy rollback)
2. **SonarQube API changes**: Use API versioning, add integration tests
3. **Line number shifts**: Fix in reverse order (high to low line numbers)
4. **Tool not available**: Check availability before starting, clear error messages
5. **Authentication issues**: Support multiple auth methods, validate early
