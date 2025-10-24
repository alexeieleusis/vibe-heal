# Feature Request: Branch Cleanup Command

## Overview

Add a new command to vibe-heal that automatically cleans up all SonarQube issues in modified files of a feature branch before code review. This ensures pull requests have no new code quality issues.

## Motivation

**Problem**: Developers want to ensure their branches are clean of SonarQube issues before submitting for code review, but manually running fixes on each modified file is tedious.

**Solution**: A single command that:
1. Identifies all files modified in a branch vs. base branch
2. Creates a temporary SonarQube project for analysis
3. Iteratively analyzes and fixes issues until the branch is clean
4. Cleans up temporary resources

## Command Name Options

Please choose your preferred name:

1. **`vibe-heal cleanup`** (RECOMMENDED) - Clear, concise, matches existing `fix` command
2. **`vibe-heal branch-cleanup`** - More explicit about scope
3. **`vibe-heal review-prep`** - Emphasizes the use case
4. **`vibe-heal polish`** - Shorter, more casual
5. **`vibe-heal sweep`** - Implies comprehensive cleanup

**Recommendation**: `cleanup` - familiar to developers, pairs well with `fix`, short and memorable.

## User Experience

### Basic Usage

```bash
# Clean up all modified files in current branch vs. main
vibe-heal cleanup --base-branch main

# Dry run to see what would be fixed
vibe-heal cleanup --base-branch main --dry-run

# Limit iterations to prevent infinite loops
vibe-heal cleanup --base-branch main --max-iterations 5

# Auto-commit each fix (vs. letting user review)
vibe-heal cleanup --base-branch main --auto-commit
```

### Workflow

```
$ vibe-heal cleanup --base-branch main

🔍 Comparing current branch 'feature/new-api' with 'main'...
   Found 8 modified files

🏗️  Creating temporary SonarQube project: myproject_user_example_com_feature_new_api

📊 Running analysis iteration 1...
   Found 23 issues across 6 files

🔧 Fixing issues in src/api/endpoints.py (5 issues)...
   ✓ Fixed 4 issues, 1 unfixable

🔧 Fixing issues in src/models/user.py (8 issues)...
   ✓ Fixed 7 issues, 1 unfixable

[... continues for all files ...]

📊 Running analysis iteration 2...
   Found 3 new issues (some fixes introduced new problems)

🔧 Fixing issues in src/api/endpoints.py (2 issues)...
   ✓ Fixed 2 issues

🔧 Fixing issues in tests/test_api.py (1 issue)...
   ✓ Fixed 1 issue

📊 Running analysis iteration 3...
   ✅ No issues found! Branch is clean.

🧹 Cleaning up temporary project...

✨ Summary:
   Files processed: 6
   Total issues fixed: 14
   Unfixable issues: 2
   Iterations: 3
   Commits created: 6
```

## High-Level Requirements

### Functional Requirements

1. **Branch Comparison**
   - Accept base branch name as parameter
   - Query git for files modified between current branch and base branch
   - Handle various file states (added, modified, renamed)

2. **Temporary Project Management**
   - Create unique SonarQube project per branch/user combination
   - Project naming: `{base_key}_{sanitized_email}_{sanitized_branch}`
   - Store project metadata for cleanup
   - Delete project when cleanup completes (or fails)

3. **Iterative Analysis & Fixing**
   - Run SonarQube analysis on temporary project
   - Fetch issues for all modified files
   - Fix issues using existing `fix` workflow
   - Re-analyze to catch issues introduced by fixes
   - Stop when: no issues remain, max iterations reached, or no progress made

4. **Safety & Robustness**
   - Require clean git state (no uncommitted changes to modified files)
   - Handle analysis failures gracefully
   - Ensure temporary project cleanup even on errors
   - Provide dry-run mode
   - Prevent infinite loops with max iteration limit

5. **User Control**
   - Confirmation prompt before starting (unless `--yes` flag)
   - Progress indicators for long-running operations
   - Detailed summary report
   - Options for auto-commit vs. manual review

### Non-Functional Requirements

- **Performance**: Analyze all files in single analysis run (not per-file)
- **Reliability**: Cleanup temporary projects even on crashes (store metadata)
- **Usability**: Clear progress indicators, helpful error messages
- **Maintainability**: Reuse existing components where possible

## Architecture Design

### New Components

#### 1. BranchAnalyzer (`src/vibe_heal/git/branch_analyzer.py`)

**Responsibility**: Git operations for branch comparison

```python
from pathlib import Path
from typing import List
from git import Repo

class BranchAnalyzer:
    """Analyzes differences between git branches."""

    def __init__(self, repo_path: Path):
        self.repo = Repo(repo_path)

    def get_modified_files(self, base_branch: str) -> List[Path]:
        """Get list of files modified in current branch vs. base branch.

        Returns only files that exist in working tree (excludes deleted files).
        Returns paths relative to repo root.
        """
        pass

    def get_current_branch(self) -> str:
        """Get name of current branch."""
        pass

    def validate_branch_exists(self, branch: str) -> bool:
        """Check if a branch exists in the repository."""
        pass

    def get_user_email(self) -> str:
        """Get configured git user email for project naming."""
        pass
```

**Key Methods**:
- `get_modified_files()`: Uses `git diff --name-only base_branch...HEAD`
- Filters for existing files only (excludes deletions)
- Returns `Path` objects relative to repo root

#### 2. ProjectManager (`src/vibe_heal/sonarqube/project_manager.py`)

**Responsibility**: SonarQube project lifecycle management

```python
from typing import Optional
from pydantic import BaseModel

class TempProjectMetadata(BaseModel):
    """Metadata for temporary SonarQube projects."""
    project_key: str
    project_name: str
    created_at: str  # ISO timestamp
    base_project_key: str
    branch_name: str
    user_email: str

class ProjectManager:
    """Manages temporary SonarQube project lifecycle."""

    def __init__(self, client: SonarQubeClient):
        self.client = client

    async def create_temp_project(
        self,
        base_key: str,
        branch_name: str,
        user_email: str
    ) -> TempProjectMetadata:
        """Create temporary project for branch analysis.

        Project key/name format: {base_key}_{sanitized_email}_{sanitized_branch}
        Sanitization: replace non-alphanumeric with underscore, lowercase.

        Returns metadata for later cleanup.
        """
        pass

    async def delete_project(self, project_key: str) -> None:
        """Delete a SonarQube project."""
        pass

    async def project_exists(self, project_key: str) -> bool:
        """Check if a project exists."""
        pass

    def _sanitize_identifier(self, value: str) -> str:
        """Sanitize string for use in project key (alphanumeric + underscore)."""
        pass
```

**SonarQube API Endpoints**:
- `POST /api/projects/create` - Create project
- `POST /api/projects/delete` - Delete project
- `GET /api/projects/search` - Check existence

#### 3. AnalysisRunner (`src/vibe_heal/sonarqube/analysis_runner.py`)

**Responsibility**: Execute SonarQube analysis via scanner CLI

```python
from pathlib import Path
from typing import Dict, Optional

class AnalysisResult(BaseModel):
    """Result of a SonarQube analysis run."""
    success: bool
    task_id: Optional[str]
    dashboard_url: Optional[str]
    error_message: Optional[str]

class AnalysisRunner:
    """Executes SonarQube analysis using sonar-scanner CLI."""

    def __init__(self, config: VibeHealConfig):
        self.config = config

    async def run_analysis(
        self,
        project_key: str,
        project_name: str,
        project_dir: Path,
        sources: Optional[List[Path]] = None
    ) -> AnalysisResult:
        """Run SonarQube analysis on project.

        Args:
            project_key: SonarQube project key
            project_name: SonarQube project name
            project_dir: Root directory to analyze
            sources: Optional list of specific files/dirs to analyze

        Executes: sonar-scanner with appropriate parameters
        Waits for analysis to complete on server
        """
        pass

    def _get_scanner_command(self, **params) -> List[str]:
        """Build sonar-scanner command with parameters."""
        pass

    async def _wait_for_analysis(self, task_id: str, timeout: int = 300) -> bool:
        """Poll SonarQube for analysis completion."""
        pass

    def validate_scanner_available(self) -> bool:
        """Check if sonar-scanner is installed and available."""
        pass
```

**Implementation Notes**:
- Uses `subprocess` to invoke `sonar-scanner` CLI
- Passes SonarQube URL, token, project key, project name
- If `sources` provided, only analyzes those files (optimization)
- Polls `/api/ce/task?id={taskId}` to wait for completion
- Returns dashboard URL for user reference

#### 4. CleanupOrchestrator (`src/vibe_heal/orchestrator/cleanup_orchestrator.py`)

**Responsibility**: Main workflow coordination for branch cleanup

```python
from typing import List, Optional
from pathlib import Path

class CleanupOptions(BaseModel):
    """Options for cleanup command."""
    base_branch: str
    dry_run: bool = False
    max_iterations: int = 10
    max_issues_per_file: Optional[int] = None
    min_severity: Optional[str] = None
    ai_tool: Optional[str] = None
    auto_commit: bool = True
    verbose: bool = False

class CleanupResult(BaseModel):
    """Result of cleanup operation."""
    files_processed: int
    total_issues_fixed: int
    unfixable_issues: int
    iterations: int
    commits_created: int
    temp_project_key: str
    success: bool
    error_message: Optional[str] = None

class CleanupOrchestrator:
    """Orchestrates branch cleanup workflow."""

    def __init__(
        self,
        config: VibeHealConfig,
        branch_analyzer: BranchAnalyzer,
        project_manager: ProjectManager,
        analysis_runner: AnalysisRunner,
        sonarqube_client: SonarQubeClient,
        orchestrator: VibeHealOrchestrator,  # Reuse existing fix logic
        git_manager: GitManager
    ):
        # ... store dependencies
        pass

    async def cleanup_branch(self, options: CleanupOptions) -> CleanupResult:
        """Execute complete branch cleanup workflow.

        Workflow:
        1. Validate preconditions (git state, base branch exists, scanner available)
        2. Get list of modified files
        3. Create temporary SonarQube project
        4. Enter fix loop:
           a. Run analysis
           b. Fetch issues for modified files
           c. If no issues, exit loop
           d. Fix issues in each file (using VibeHealOrchestrator.fix_file)
           e. Increment iteration counter
           f. If max iterations reached, exit loop
        5. Delete temporary project
        6. Return summary

        Ensures cleanup happens even on errors (try/finally).
        """
        pass

    async def _validate_preconditions(self, options: CleanupOptions) -> None:
        """Validate git state, branches, scanner availability."""
        pass

    async def _fix_iteration(
        self,
        files: List[Path],
        project_key: str,
        options: CleanupOptions
    ) -> int:
        """Run one iteration of analysis + fixing.

        Returns number of issues fixed in this iteration.
        """
        pass
```

**Key Workflow Details**:
- Uses `try/finally` to ensure temp project cleanup
- Reuses `VibeHealOrchestrator.fix_file()` for actual fixing
- Tracks progress: iterations, issues fixed, files processed
- Stops on: no issues, max iterations, or no progress (same issue count twice)

### Modified Components

#### SonarQubeClient (`src/vibe_heal/sonarqube/client.py`)

**New Methods**:

```python
async def create_project(self, key: str, name: str) -> None:
    """Create a new SonarQube project.

    POST /api/projects/create
    Params: project (key), name
    """
    pass

async def delete_project(self, key: str) -> None:
    """Delete a SonarQube project.

    POST /api/projects/delete
    Params: project (key)
    """
    pass

async def get_issues_for_project(
    self,
    project_key: str,
    statuses: Optional[List[str]] = None
) -> List[SonarQubeIssue]:
    """Get all issues for a project.

    GET /api/issues/search
    Params: componentKeys (project key), issueStatuses
    Used to get all issues across all files in temp project.
    """
    pass
```

#### CLI (`src/vibe_heal/cli.py`)

**New Command**:

```python
@app.command()
def cleanup(
    base_branch: str = typer.Option(
        ..., "--base-branch", "-b",
        help="Base branch to compare against (e.g., 'main', 'develop')"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show what would be fixed without making changes"
    ),
    max_iterations: int = typer.Option(
        10, "--max-iterations",
        help="Maximum analysis+fix iterations to prevent infinite loops"
    ),
    max_issues_per_file: Optional[int] = typer.Option(
        None, "--max-issues",
        help="Maximum issues to fix per file (None = all)"
    ),
    min_severity: Optional[str] = typer.Option(
        None, "--min-severity",
        help="Minimum severity to fix (INFO, MINOR, MAJOR, CRITICAL, BLOCKER)"
    ),
    ai_tool: Optional[str] = typer.Option(
        None, "--ai-tool",
        help="AI tool to use (claude-code, aider). Auto-detects if not specified."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip confirmation prompt"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose output"
    ),
) -> None:
    """Clean up SonarQube issues in all modified files of current branch.

    Compares current branch with base branch, creates temporary SonarQube
    project, and iteratively fixes issues until branch is clean.
    """
    pass
```

## Implementation Plan

### Phase 1: Git Branch Analysis (Foundation)

**Goal**: Implement branch cleanup functionality

**Status**: ✅ Complete

**Tasks**:
1. ✅ Create `BranchAnalyzer` class in `src/vibe_heal/git/branch_analyzer.py`
2. ✅ Implement git diff logic to get modified files
3. ✅ Add file existence filtering (exclude deletions)
4. ✅ Add user email retrieval for project naming
5. ✅ Write comprehensive tests in `tests/git/test_branch_analyzer.py`
   - Test with mock git repos
   - Test various file states (added, modified, renamed, deleted)
   - Test branch validation
6. ✅ **Update this document**: Mark phase as complete, update status
7. ✅ **Update CLAUDE.md**: Add `BranchAnalyzer` to architecture section

**Acceptance Criteria**:
- ✅ `get_modified_files()` returns accurate list vs. base branch (defaults to `origin/main`)
- ✅ Handles edge cases (no changes, branch doesn't exist)
- ✅ 100% test coverage (28 tests, all passing)
- ✅ Documentation updated

**Actual Effort**: ~3 hours

**Implementation Notes**:
- Base branch defaults to `origin/main` (can be customized)
- Uses git three-dot diff syntax (`base...HEAD`) to compare from merge base
- Validates branch existence for both local and remote branches
- Filters out deleted files and directories, returns only existing files
- All methods have comprehensive error handling with custom exceptions

### Phase 2: SonarQube Project Management

**Goal**: Add project creation/deletion to SonarQube client

**Status**: ✅ Complete

**Tasks**:
1. ✅ Add API methods to `SonarQubeClient`:
   - `create_project()` - Creates new SonarQube project
   - `delete_project()` - Deletes existing project
   - `project_exists()` - Checks if project exists
2. ✅ Create `ProjectManager` class in `src/vibe_heal/sonarqube/project_manager.py`
3. ✅ Implement project key sanitization logic
4. ✅ Add `TempProjectMetadata` model
5. ✅ Write tests in `tests/sonarqube/test_project_manager.py`
   - Mock API responses for create/delete/exists
   - Test key sanitization (special chars, emails, branch names)
   - Test error handling (project already exists, deletion fails)
6. ✅ **Update this document**: Mark phase as complete, update status
7. ✅ **Update CLAUDE.md**: Add `ProjectManager` and SonarQube API updates to architecture

**Acceptance Criteria**:
- ✅ Can create uniquely named temporary projects
- ✅ Can delete projects
- ✅ Can check project existence
- ✅ Project keys are valid SonarQube identifiers (sanitization working)
- ✅ Graceful error handling
- ✅ Documentation updated

**Actual Effort**: ~4 hours

**Implementation Notes**:
- Removed `get_issues_for_project()` - will reuse existing `fix_file()` workflow
- Project key format: `{base_key}_{sanitized_email}_{sanitized_branch}`
- Sanitization replaces non-alphanumeric (except `_`) with `_`, converts to lowercase
- Added 18 comprehensive tests for ProjectManager (all passing)
- Added 7 tests for new SonarQubeClient methods
- Note: Pre-existing circular import in test_client.py (not caused by our changes)

### Phase 3: Analysis Runner Integration

**Goal**: Integrate sonar-scanner CLI execution

**Status**: ✅ Complete

**Tasks**:
1. ✅ Create `AnalysisRunner` class in `src/vibe_heal/sonarqube/analysis_runner.py`
2. ✅ Implement `run_analysis()` with subprocess management
3. ✅ Add analysis task polling (`_wait_for_analysis()`)
4. ✅ Implement scanner availability check
5. ✅ Add `AnalysisResult` model
6. ✅ Write tests in `tests/sonarqube/test_analysis_runner.py`
   - Mock subprocess calls
   - Test analysis success/failure scenarios
   - Test timeout handling
   - Test scanner not available
7. ✅ **Update this document**: Mark phase as complete, update status
8. ✅ **Update CLAUDE.md**: Add `AnalysisRunner` to architecture, document sonar-scanner requirement

**Dependencies**:
- Requires `sonar-scanner` CLI in development environment
- Setup instructions documented in CLAUDE.md

**Acceptance Criteria**:
- ✅ Successfully triggers analysis via sonar-scanner subprocess
- ✅ Waits for completion with timeout (default 300s, polls every 2s)
- ✅ Returns useful error messages (scanner not found, execution failed, timeout, etc.)
- ✅ Validates scanner presence (shutil.which check)
- ✅ Documentation updated with setup instructions

**Actual Effort**: ~5 hours

**Implementation Notes**:
- Uses `asyncio.create_subprocess_exec` for non-blocking scanner execution
- Polls `/api/ce/task?id={taskId}` endpoint for analysis completion
- Extracts task ID from scanner stdout (looks for "api/ce/task?id=" pattern)
- Supports both token auth and basic auth
- Allows specifying sources for partial analysis optimization
- Returns `AnalysisResult` with success status, task_id, dashboard_url, and error details
- 20+ comprehensive tests covering all scenarios
- Note: Tests have pre-existing circular import issue (not caused by Phase 3)

### Phase 4: Cleanup Orchestrator (Core Logic)

**Goal**: Implement main cleanup workflow

**Status**: Not Started

**Tasks**:
1. Create `CleanupOrchestrator` class in `src/vibe_heal/orchestrator/cleanup_orchestrator.py`
2. Implement `cleanup_branch()` with complete workflow:
   - Precondition validation
   - Temp project creation
   - Iterative fix loop
   - Cleanup (try/finally)
3. Add progress tracking and reporting
4. Implement stopping conditions (no issues, max iterations, no progress)
5. Integrate with existing `VibeHealOrchestrator.fix_file()`
6. Add `CleanupOptions` and `CleanupResult` models
7. Write tests in `tests/orchestrator/test_cleanup_orchestrator.py`
   - Test complete workflow with mocks
   - Test iteration limit
   - Test cleanup on errors
   - Test no-progress detection
8. **Update this document**: Mark phase as complete, update status
9. **Update CLAUDE.md**: Add `CleanupOrchestrator` workflow to architecture section

**Acceptance Criteria**:
- End-to-end workflow executes correctly
- Temp project always cleaned up (even on errors)
- Progress clearly reported
- Handles all edge cases
- Documentation updated

**Estimated Effort**: 10-12 hours

### Phase 5: CLI Integration

**Goal**: Add `cleanup` command to CLI

**Status**: Not Started

**Tasks**:
1. Add `cleanup()` command to `src/vibe_heal/cli.py`
2. Wire up all components (dependency injection)
3. Add user confirmation prompt
4. Implement rich progress output
5. Add verbose mode support
6. Write CLI tests in `tests/test_cli.py`
   - Test command parsing
   - Test dry-run mode
   - Test confirmation prompt (use `typer.testing.CliRunner`)
7. **Update this document**: Mark phase as complete, update status
8. **Update CLAUDE.md**: Add CLI command documentation

**Acceptance Criteria**:
- `vibe-heal cleanup --base-branch main` works end-to-end
- All CLI flags work correctly
- Beautiful, informative output
- Documentation updated

**Estimated Effort**: 6-8 hours

### Phase 6: Documentation & Polish

**Goal**: Document feature and add user guides

**Status**: Not Started

**Tasks**:
1. Update `README.md` with cleanup command
2. Add user guide to `docs/` (with examples, troubleshooting)
3. Review and finalize `CLAUDE.md` cleanup architecture updates from previous phases
4. Add configuration examples for `.env.vibeheal`
5. Add CI/CD considerations (running cleanup in pipelines)
6. Update changelog
7. **Update this document**: Mark phase as complete, update status

**Acceptance Criteria**:
- Clear documentation for users and developers
- Examples cover common use cases
- Troubleshooting guide for common errors
- All documentation is consistent and complete

**Estimated Effort**: 4-6 hours

### Phase 7: Integration Testing & Refinement

**Goal**: Test with real SonarQube instance, refine based on feedback

**Status**: Not Started

**Tasks**:
1. Test against real SonarQube instance with test project
2. Test with multiple file types and issue counts
3. Performance testing (large branches)
4. Refine error messages based on real usage
5. Add telemetry/logging for troubleshooting
6. Bug fixes and polish
7. **Update this document**: Mark phase as complete, document any lessons learned
8. **Final documentation review**: Ensure all docs reflect final implementation

**Acceptance Criteria**:
- Works reliably on real codebases
- Performance is acceptable (< 5 min for typical branch)
- Error messages are actionable
- All documentation is accurate and complete

**Estimated Effort**: 8-10 hours

## Total Estimated Effort

**Development**: 44-58 hours (roughly 6-8 days)

**Phases**:
1. Git Branch Analysis: 4-6 hours
2. Project Management: 6-8 hours
3. Analysis Runner: 6-8 hours
4. Cleanup Orchestrator: 10-12 hours
5. CLI Integration: 6-8 hours
6. Documentation: 4-6 hours
7. Integration Testing: 8-10 hours

## Dependencies & Prerequisites

### External Tools
- `sonar-scanner` CLI must be installed
- Git repository with remote branches

### Configuration
- `.env.vibeheal` with valid SonarQube credentials
- SonarQube user must have project creation permissions

### SonarQube API Permissions
- `POST /api/projects/create` - Create projects
- `POST /api/projects/delete` - Delete projects
- `GET /api/issues/search` - Query issues
- `GET /api/ce/task` - Check analysis status

## Risks & Mitigations

### Risk 1: Orphaned Temporary Projects
**Problem**: If cleanup crashes, temp projects remain in SonarQube

**Mitigations**:
- Store project metadata in local file (`.vibe-heal/temp_projects.json`)
- Add `vibe-heal cleanup-projects` command to delete orphaned projects
- Add project expiry date in project name for manual cleanup

### Risk 2: Infinite Fix Loops
**Problem**: Fixes introduce new issues, creating infinite loop

**Mitigations**:
- Hard limit on iterations (default: 10)
- Detect no-progress (same issue count for 2 iterations)
- User can ctrl+C to abort

### Risk 3: Analysis Performance
**Problem**: Large branches with many files are slow to analyze

**Mitigations**:
- Optimize by only analyzing modified files (use `sonar.sources` parameter)
- Show progress indicators so user knows it's working
- Allow user to limit max issues per file

### Risk 4: SonarQube Scanner Not Installed
**Problem**: User doesn't have sonar-scanner CLI

**Mitigations**:
- Check for scanner in preconditions
- Provide clear error message with installation instructions
- Document in README

## Future Enhancements

### v1.1: Smart Iteration
- Learn from previous iterations to avoid re-analyzing clean files
- Only re-analyze files that were modified in previous iteration

### v1.2: Parallel Fixing
- Fix multiple files concurrently (with configurable parallelism)
- Speeds up large branches significantly

### v1.3: Quality Gate Integration
- Check if temp project passes quality gate
- Report which quality gate conditions are failing

### v1.4: PR Integration
- GitHub/GitLab integration to run on PRs automatically
- Comment on PR with cleanup results

## Success Criteria

**Feature is successful if**:
1. ✅ Users can clean entire branches with single command
2. ✅ Reduces manual effort from ~30 min to ~5 min for typical branch
3. ✅ No orphaned temporary projects (cleanup is robust)
4. ✅ Clear, actionable progress output
5. ✅ Handles edge cases gracefully (no crashes)
6. ✅ 90%+ test coverage for new code
7. ✅ Documentation is clear and complete

## Open Questions

1. **Command name preference?** Recommend `cleanup` but gather feedback
2. **Default max iterations?** Suggest 10, but may need tuning
3. **Auto-commit by default?** Or require `--auto-commit` flag for safety?
4. **Should we support fixing specific file patterns?** (e.g., only `*.py` files)
5. **How to handle merge conflicts during cleanup?** Abort or continue?

## Approval Checklist

Before starting implementation:
- [x] Command name decided: cleanup
- [x] Auto-commit behavior decided: require `--auto-commit` flag: default is auto-commit like the fix command, which is what we should reuse
- [x] SonarQube permissions verified (can create/delete projects)
- [x] `sonar-scanner` installation documented
- [x] Design reviewed by team
- [x] Priorities confirmed (can we defer any phases?)

---

**Document Version**: 1.0
**Created**: 2025-10-23
**Status**: Draft - Awaiting Approval
