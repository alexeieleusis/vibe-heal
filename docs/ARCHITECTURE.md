# vibe-heal Architecture

## Overview

vibe-heal follows a modular, layered architecture with clear separation of concerns.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CLI Layer                           │
│  (typer, rich - user interface, progress, reporting)    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              Orchestration Layer                        │
│  (VibeHealOrchestrator - main workflow logic)          │
└──┬──────────┬──────────┬──────────┬─────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│Config│ │SonarQube│ │AI Tool│ │   Git    │
│ Mgmt │ │ Client  │ │Manager │ │ Manager  │
└──────┘ └────────┘ └────────┘ └──────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│.env  │ │SonarQube│ │Claude  │ │   Git    │
│files │ │   API   │ │Code/   │ │   Repo   │
│      │ │         │ │Aider   │ │          │
└──────┘ └────────┘ └────────┘ └──────────┘
```

## Module Structure

```
src/vibe_heal/
├── __init__.py
├── __main__.py              # Entry point for `python -m vibe_heal`
├── cli.py                   # CLI interface (typer)
├── orchestrator.py          # Main workflow orchestration
├── config/
│   ├── __init__.py
│   ├── models.py           # Configuration Pydantic models
│   └── loader.py           # Configuration loading logic
├── sonarqube/
│   ├── __init__.py
│   ├── client.py           # SonarQube API client
│   └── models.py           # SonarQube response models
├── ai_tools/
│   ├── __init__.py
│   ├── base.py             # Abstract base class + AIToolType enum
│   ├── claude_code.py      # Claude Code implementation
│   ├── aider.py            # Aider implementation
│   ├── factory.py          # Factory for creating AI tool instances
│   └── models.py           # Shared models (FixResult, etc.)
├── git/
│   ├── __init__.py
│   └── manager.py          # Git operations
├── processor/
│   ├── __init__.py
│   ├── issue_processor.py  # Issue sorting and filtering
│   └── models.py           # Processing models
└── utils/
    ├── __init__.py
    ├── logging.py          # Logging setup
    └── validators.py       # Common validation utilities
```

## Core Components

### 1. Configuration Management (`config/`)

**Purpose**: Load and validate configuration from environment variables and config files.

**Key Classes**:
- `AIToolType`: Enum for supported AI tools
  ```python
  class AIToolType(str, Enum):
      CLAUDE_CODE = "claude-code"
      AIDER = "aider"
  ```

- `VibeHealConfig`: Pydantic model with settings
  - Uses `pydantic-settings` to load from `.env.vibeheal` or `.env`
  - Validation of required fields
  - Smart defaults

**Example**:
```python
class VibeHealConfig(BaseSettings):
    sonarqube_url: str
    sonarqube_token: str | None = None
    sonarqube_username: str | None = None
    sonarqube_password: str | None = None
    sonarqube_project_key: str
    ai_tool: AIToolType | None = None  # auto-detect if None

    model_config = SettingsConfigDict(
        env_file=['.env.vibeheal', '.env'],
        env_file_encoding='utf-8',
        env_prefix='',
    )

    @field_validator('ai_tool', mode='before')
    @classmethod
    def parse_ai_tool(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return AIToolType(v.lower())
        return v
```

### 2. SonarQube Client (`sonarqube/`)

**Purpose**: Interface with SonarQube Web API to fetch issues.

**Key Classes**:
- `SonarQubeClient`: HTTP client for SonarQube API
  - Authentication handling (token or basic auth)
  - `get_issues_for_file(file_path: str) -> list[SonarQubeIssue]`
  - Error handling and retries

- `SonarQubeIssue`: Pydantic model representing an issue
  ```python
  class SonarQubeIssue(BaseModel):
      key: str
      rule: str
      severity: str
      message: str
      line: int | None
      component: str
      status: str
  ```

**SonarQube API Endpoints Used**:
- `/api/issues/search` - Search for issues
  - Params: `componentKeys`, `resolved=false`
  - Filter by file path in results

### 3. Issue Processor (`processor/`)

**Purpose**: Sort and filter issues to determine fix order.

**Key Classes**:
- `IssueProcessor`: Business logic for issue processing
  - `sort_issues(issues: list[SonarQubeIssue]) -> list[SonarQubeIssue]`
    - Sort by line number descending (reverse order)
    - Handle issues without line numbers (skip or put at end)
  - `filter_fixable(issues: list[SonarQubeIssue]) -> list[SonarQubeIssue]`
    - Remove won't-fix, false-positives
    - Optionally filter by severity

### 4. AI Tool Manager (`ai_tools/`)

**Purpose**: Abstract interface for AI coding tools with multiple implementations.

**Key Classes**:
- `AIToolType` (Enum): Enum defining supported AI tools
  ```python
  class AIToolType(str, Enum):
      CLAUDE_CODE = "claude-code"
      AIDER = "aider"

      @property
      def cli_command(self) -> str:
          """Get the CLI command name for this tool"""
          return self.value

      @property
      def display_name(self) -> str:
          """Get human-readable display name"""
          return {
              AIToolType.CLAUDE_CODE: "Claude Code",
              AIToolType.AIDER: "Aider",
          }[self]
  ```

- `AITool` (ABC): Abstract base class
  ```python
  class AITool(ABC):
      tool_type: AIToolType

      @abstractmethod
      def is_available(self) -> bool:
          """Check if tool is installed and accessible"""

      @abstractmethod
      async def fix_issue(
          self,
          issue: SonarQubeIssue,
          file_path: str
      ) -> FixResult:
          """Attempt to fix the issue"""
  ```

- `ClaudeCodeTool(AITool)`: Claude Code implementation
  ```python
  class ClaudeCodeTool(AITool):
      tool_type = AIToolType.CLAUDE_CODE

      def is_available(self) -> bool:
          # Check for claude-code CLI
  ```

- `AiderTool(AITool)`: Aider implementation
  ```python
  class AiderTool(AITool):
      tool_type = AIToolType.AIDER

      def is_available(self) -> bool:
          # Check for aider CLI
  ```

- `AIToolFactory`: Factory for creating tool instances
  ```python
  class AIToolFactory:
      @staticmethod
      def create(tool_type: AIToolType) -> AITool:
          """Create an AI tool instance based on type"""
          tool_map = {
              AIToolType.CLAUDE_CODE: ClaudeCodeTool,
              AIToolType.AIDER: AiderTool,
          }
          return tool_map[tool_type]()

      @staticmethod
      def detect_available() -> AIToolType | None:
          """Auto-detect first available AI tool"""
          # Try Claude Code first, then Aider
          for tool_type in AIToolType:
              tool = AIToolFactory.create(tool_type)
              if tool.is_available():
                  return tool_type
          return None
  ```

- `FixResult`: Result model
  ```python
  class FixResult(BaseModel):
      success: bool
      error_message: str | None = None
      files_modified: list[str] = []
  ```

**Prompt Template**:
```
Fix the following SonarQube issue in {file_path}:

Rule: {rule}
Line: {line}
Severity: {severity}
Message: {message}

Please fix this issue while maintaining code functionality and style.
```

### 5. Git Manager (`git/`)

**Purpose**: Handle git operations for committing fixes.

**Key Classes**:
- `GitManager`: Wrapper around GitPython
  - `is_repository() -> bool`
  - `is_clean() -> bool`
  - `commit_fix(issue: SonarQubeIssue, files: list[str], ai_tool_type: AIToolType)`
  - `get_current_branch() -> str`

**Commit Message Format**:
```
fix: [SQ-ABC123] Remove unused import

Fixes SonarQube issue on line 42
Rule: python:S1481
Message: Remove this unused import

Fixed by vibe-heal using Claude Code
```

### 6. Orchestrator (`orchestrator.py`)

**Purpose**: Main workflow coordination.

**Key Class**:
- `VibeHealOrchestrator`: Coordinates all components
  ```python
  class VibeHealOrchestrator:
      def __init__(self, config: VibeHealConfig):
          self.config = config
          self.sonarqube_client = SonarQubeClient(config)
          self.git_manager = GitManager()
          self.ai_tool = self._initialize_ai_tool()

      def _initialize_ai_tool(self) -> AITool:
          """Initialize AI tool based on config or auto-detect"""
          if self.config.ai_tool:
              tool_type = self.config.ai_tool
          else:
              tool_type = AIToolFactory.detect_available()
              if not tool_type:
                  raise RuntimeError("No AI tool found (Claude Code or Aider)")

          return AIToolFactory.create(tool_type)

      async def fix_file(
          self,
          file_path: str,
          dry_run: bool = False,
          max_issues: int | None = None
      ) -> FixSummary:
          # Main workflow
  ```

**Workflow**:
1. Validate preconditions (git clean, file exists, etc.)
2. Fetch issues from SonarQube
3. Sort and filter issues
4. For each issue:
   - Show progress
   - Invoke AI tool
   - If success and not dry-run: commit
   - Track results
5. Return summary

### 7. CLI (`cli.py`)

**Purpose**: User interface.

**Key Functions**:
- `app = typer.Typer()` - Main CLI app
- `@app.command()` decorated functions for commands
- Rich progress bars and formatting
- Error display

**Commands**:
```bash
vibe-heal fix <file_path>           # Fix issues in file
  --dry-run                          # Preview without committing
  --max-issues N                     # Limit number of fixes
  --ai-tool {claude-code,aider}      # Override tool detection
  --verbose                          # Debug logging

vibe-heal config                     # Show current configuration
vibe-heal version                    # Show version
```

**CLI uses AIToolType enum**:
```python
@app.command()
def fix(
    file_path: str,
    dry_run: bool = False,
    max_issues: int | None = None,
    ai_tool: AIToolType | None = typer.Option(None, help="AI tool to use"),
    verbose: bool = False,
):
    # ...
```

## Data Flow

### Happy Path: Fixing a File

```
1. User runs: vibe-heal fix src/foo.py

2. CLI parses arguments
   ├─> Load configuration
   └─> Create VibeHealOrchestrator

3. Orchestrator.__init__()
   ├─> Initialize components
   └─> _initialize_ai_tool()
       ├─> config.ai_tool is None
       ├─> AIToolFactory.detect_available()
       │   ├─> Try ClaudeCodeTool().is_available() → True
       │   └─> Return AIToolType.CLAUDE_CODE
       └─> AIToolFactory.create(AIToolType.CLAUDE_CODE)
           └─> Return ClaudeCodeTool instance

4. Orchestrator.fix_file("src/foo.py")
   ├─> GitManager.is_clean() → ✓
   ├─> SonarQubeClient.get_issues_for_file("src/foo.py")
   │   └─> Returns [Issue1(line=50), Issue2(line=30), Issue3(line=10)]
   ├─> IssueProcessor.sort_issues()
   │   └─> Returns [Issue1(line=50), Issue2(line=30), Issue3(line=10)]
   │
   ├─> For Issue1 (line=50):
   │   ├─> AITool.fix_issue(Issue1, "src/foo.py")
   │   │   └─> Returns FixResult(success=True, files_modified=["src/foo.py"])
   │   └─> GitManager.commit_fix(Issue1, ["src/foo.py"], AIToolType.CLAUDE_CODE)
   │
   ├─> For Issue2 (line=30):
   │   ├─> AITool.fix_issue(Issue2, "src/foo.py")
   │   │   └─> Returns FixResult(success=True, files_modified=["src/foo.py"])
   │   └─> GitManager.commit_fix(Issue2, ["src/foo.py"], AIToolType.CLAUDE_CODE)
   │
   └─> For Issue3 (line=10):
       ├─> AITool.fix_issue(Issue3, "src/foo.py")
       │   └─> Returns FixResult(success=False, error_message="...")
       └─> Track as failed

5. Return FixSummary(fixed=2, failed=1, skipped=0)

6. CLI displays summary report
```

## Error Handling Strategy

### Validation Errors (Fail Fast)
- Missing configuration → Clear error message, exit
- Git repo not clean → Error message, exit
- File doesn't exist → Error message, exit
- SonarQube auth failure → Error message, exit
- No AI tool available → Error message, exit

### Recoverable Errors (Continue)
- AI tool fails on one issue → Log error, continue to next issue
- Commit fails → Log error, continue to next issue
- Issue has no line number → Skip issue

### Rollback Strategy
- Each fix is a separate commit
- If something goes wrong, user can `git reset HEAD~N` to undo N fixes
- In future: Could add `vibe-heal undo` command

## Configuration Priority

1. Command-line arguments (`--ai-tool` flag)
2. `.env.vibeheal` file
3. `.env` file
4. Environment variables
5. Auto-detection (if ai_tool not specified)

## Testing Strategy

### Unit Tests
- Each module has comprehensive unit tests
- Mock external dependencies (SonarQube API, Git, AI tools)
- Use `pytest-mock` and `responses` library

### Integration Tests
- End-to-end tests with real git repos (temporary directories)
- Mock SonarQube API responses
- Mock or stub AI tool responses

### Manual Testing
- Test with real SonarQube instance
- Test with real Claude Code/Aider
- Test in various git states

## Security Considerations

1. **Credentials**: Never log tokens or passwords
2. **Code Execution**: AI tools execute code - require clean git state
3. **Input Validation**: Validate file paths to prevent directory traversal
4. **API Rate Limiting**: Respect SonarQube API rate limits
5. **Secrets in .env**: Add `.env*` to `.gitignore` (already done in template)

## Performance Considerations

1. **Sequential Processing**: Fix issues one at a time (safety over speed)
2. **HTTP Client**: Use `httpx` with connection pooling
3. **Async Where Possible**: Use async/await for I/O operations
4. **Lazy Loading**: Only initialize components when needed

## Future Architecture Improvements

1. **Plugin System**: Allow custom AI tool implementations via enum extension
2. **Event System**: Emit events for fixes, commits (for monitoring)
3. **Queue System**: For multi-file processing
4. **Caching**: Cache SonarQube responses
5. **State Management**: Track progress across runs
