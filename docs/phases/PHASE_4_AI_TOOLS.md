# Phase 4: AI Tool Integration ✅ COMPLETE

## Objective

Implement abstract AI tool interface and Claude Code implementation to fix SonarQube issues.

## Status: ✅ COMPLETE

All AI tool integration features implemented and tested:
- [x] `AITool` abstract base class for tool implementations
- [x] `FixResult` model with success/failure tracking
- [x] Prompt template system for issue fixing
- [x] `ClaudeCodeTool` implementation with proper CLI integration
- [x] Uses correct `claude` binary with `--print` and `--output-format json`
- [x] Permission mode set to `acceptEdits` for automatic approval
- [x] Tool restriction to `Edit,Read` only for security
- [x] `AIToolFactory` with auto-detection capability
- [x] Comprehensive error handling and timeout management
- [x] Test coverage: 30 tests, 97% coverage

**Test Results**: 30 tests for ai_tools module, 97% coverage
**Overall Progress**: 98 tests passing, 95% code coverage

**Implementation Notes**:
- Claude CLI correctly invoked with `claude` command (not `claude-code`)
- JSON output format used for structured result parsing
- Configurable timeout (default: 5 minutes) for complex fixes
- Tool availability checking with `shutil.which`
- Async/await pattern for non-blocking operations

## Dependencies

- Phase 0, 1, 2, and 3 must be complete ✅
- `AIToolType` enum available ✅
- `SonarQubeIssue` model available ✅

## Files to Create/Modify

```
src/vibe_heal/
├── ai_tools/
│   ├── __init__.py              # Export public API
│   ├── base.py                  # AIToolType enum + AITool ABC (already has enum)
│   ├── models.py                # FixResult and related models
│   ├── factory.py               # Factory for creating AI tools
│   ├── claude_code.py           # Claude Code implementation
│   └── prompts.py               # Prompt templates
tests/
└── ai_tools/
    ├── test_base.py             # Enum tests (already exists)
    ├── test_models.py           # Model tests
    ├── test_factory.py          # Factory tests
    └── test_claude_code.py      # Claude Code implementation tests
```

## Tasks

### 1. Create AI Tool Models

**File**: `src/vibe_heal/ai_tools/models.py`

```python
from pydantic import BaseModel, Field


class FixResult(BaseModel):
    """Result of attempting to fix an issue."""

    success: bool = Field(description="Whether the fix succeeded")
    error_message: str | None = Field(
        default=None,
        description="Error message if fix failed"
    )
    files_modified: list[str] = Field(
        default_factory=list,
        description="List of files modified by the fix"
    )
    ai_response: str | None = Field(
        default=None,
        description="Raw response from AI tool (for debugging)"
    )

    @property
    def failed(self) -> bool:
        """Check if the fix failed."""
        return not self.success
```

### 2. Create Prompt Templates

**File**: `src/vibe_heal/ai_tools/prompts.py`

```python
from vibe_heal.sonarqube.models import SonarQubeIssue


def create_fix_prompt(issue: SonarQubeIssue, file_path: str) -> str:
    """Create a prompt for fixing a SonarQube issue.

    Args:
        issue: The SonarQube issue to fix
        file_path: Path to the file containing the issue

    Returns:
        Formatted prompt for AI tool
    """
    prompt = f"""Fix the following SonarQube issue in {file_path}:

**Issue Details:**
- Rule: {issue.rule}
- Severity: {issue.severity}
- Type: {issue.type}
- Line: {issue.line}
- Message: {issue.message}

**Instructions:**
1. Fix the issue while maintaining code functionality and style
2. Make minimal changes - only fix this specific issue
3. Do not fix other unrelated issues in the file
4. Ensure the fix doesn't break existing functionality
5. Follow the project's coding standards

Please make the necessary changes to fix this issue.
"""
    return prompt.strip()
```

### 3. Update AITool Base Class

**File**: `src/vibe_heal/ai_tools/base.py` (add to existing file)

```python
from abc import ABC, abstractmethod
from enum import Enum

from vibe_heal.ai_tools.models import FixResult
from vibe_heal.sonarqube.models import SonarQubeIssue


class AIToolType(str, Enum):
    """Supported AI coding tools."""

    CLAUDE_CODE = "claude-code"
    AIDER = "aider"

    @property
    def cli_command(self) -> str:
        """Get the CLI command name for this tool."""
        return self.value

    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        return {
            AIToolType.CLAUDE_CODE: "Claude Code",
            AIToolType.AIDER: "Aider",
        }[self]


class AITool(ABC):
    """Abstract base class for AI coding tools."""

    tool_type: AIToolType

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the tool is installed and accessible.

        Returns:
            True if tool is available, False otherwise
        """

    @abstractmethod
    async def fix_issue(
        self,
        issue: SonarQubeIssue,
        file_path: str
    ) -> FixResult:
        """Attempt to fix a SonarQube issue.

        Args:
            issue: The SonarQube issue to fix
            file_path: Path to the file containing the issue

        Returns:
            Result of the fix attempt
        """
```

### 4. Implement Claude Code Tool

**File**: `src/vibe_heal/ai_tools/claude_code.py`

```python
import asyncio
import shutil
from pathlib import Path

from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.models import FixResult
from vibe_heal.ai_tools.prompts import create_fix_prompt
from vibe_heal.sonarqube.models import SonarQubeIssue


class ClaudeCodeTool(AITool):
    """Claude Code AI tool implementation."""

    tool_type = AIToolType.CLAUDE_CODE

    def __init__(self, timeout: int = 300):
        """Initialize Claude Code tool.

        Args:
            timeout: Timeout in seconds for AI operations (default: 5 minutes)
        """
        self.timeout = timeout

    def is_available(self) -> bool:
        """Check if Claude Code CLI is installed.

        Returns:
            True if claude-code command is available
        """
        return shutil.which("claude-code") is not None

    async def fix_issue(
        self,
        issue: SonarQubeIssue,
        file_path: str
    ) -> FixResult:
        """Fix an issue using Claude Code.

        Args:
            issue: The SonarQube issue to fix
            file_path: Path to the file containing the issue

        Returns:
            Result of the fix attempt
        """
        if not self.is_available():
            return FixResult(
                success=False,
                error_message="Claude Code CLI not found. Please install it first."
            )

        # Verify file exists
        if not Path(file_path).exists():
            return FixResult(
                success=False,
                error_message=f"File not found: {file_path}"
            )

        # Create prompt
        prompt = create_fix_prompt(issue, file_path)

        # Invoke Claude Code
        try:
            result = await self._invoke_claude_code(prompt, file_path)
            return result
        except asyncio.TimeoutError:
            return FixResult(
                success=False,
                error_message=f"Claude Code timed out after {self.timeout} seconds"
            )
        except Exception as e:
            return FixResult(
                success=False,
                error_message=f"Error invoking Claude Code: {e}"
            )

    async def _invoke_claude_code(
        self,
        prompt: str,
        file_path: str
    ) -> FixResult:
        """Invoke Claude Code CLI.

        Args:
            prompt: The prompt to send to Claude Code
            file_path: File to fix

        Returns:
            FixResult with outcome
        """
        # Build command
        # Note: Adjust this based on actual Claude Code CLI interface
        cmd = [
            "claude-code",
            "--message", prompt,
            "--no-interactive",
        ]

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""

            # Check if successful
            if process.returncode == 0:
                return FixResult(
                    success=True,
                    files_modified=[file_path],
                    ai_response=stdout_text,
                )
            else:
                return FixResult(
                    success=False,
                    error_message=f"Claude Code failed: {stderr_text}",
                    ai_response=stdout_text,
                )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
```

### 5. Implement AI Tool Factory

**File**: `src/vibe_heal/ai_tools/factory.py`

```python
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.claude_code import ClaudeCodeTool


class AIToolFactory:
    """Factory for creating AI tool instances."""

    _tool_map: dict[AIToolType, type[AITool]] = {
        AIToolType.CLAUDE_CODE: ClaudeCodeTool,
        # AIToolType.AIDER will be added in Phase 8
    }

    @staticmethod
    def create(tool_type: AIToolType) -> AITool:
        """Create an AI tool instance based on type.

        Args:
            tool_type: The type of AI tool to create

        Returns:
            AI tool instance

        Raises:
            ValueError: If tool type is not supported
        """
        tool_class = AIToolFactory._tool_map.get(tool_type)
        if not tool_class:
            raise ValueError(f"Unsupported AI tool type: {tool_type}")
        return tool_class()

    @staticmethod
    def detect_available() -> AIToolType | None:
        """Auto-detect first available AI tool.

        Tries tools in order of preference:
        1. Claude Code
        2. Aider

        Returns:
            AIToolType of first available tool, or None if none found
        """
        # Try in preference order
        for tool_type in [AIToolType.CLAUDE_CODE]:  # Add AIDER later
            try:
                tool = AIToolFactory.create(tool_type)
                if tool.is_available():
                    return tool_type
            except ValueError:
                continue

        return None
```

### 6. Export Public API

**File**: `src/vibe_heal/ai_tools/__init__.py`

```python
from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.claude_code import ClaudeCodeTool
from vibe_heal.ai_tools.factory import AIToolFactory
from vibe_heal.ai_tools.models import FixResult
from vibe_heal.ai_tools.prompts import create_fix_prompt

__all__ = [
    "AITool",
    "AIToolType",
    "ClaudeCodeTool",
    "AIToolFactory",
    "FixResult",
    "create_fix_prompt",
]
```

### 7. Write Comprehensive Tests

**File**: `tests/ai_tools/test_models.py`
- Test `FixResult` model
- Test `failed` property

**File**: `tests/ai_tools/test_factory.py`
- Test creating Claude Code tool
- Test auto-detection
- Test invalid tool type raises error

**File**: `tests/ai_tools/test_claude_code.py`
- Test `is_available()` (mock `shutil.which`)
- Test successful fix (mock subprocess)
- Test timeout handling
- Test file not found error
- Test Claude Code not installed error
- Test command execution failure

Use `pytest-mock` to mock subprocess and file system operations.

## Example Usage

```python
from vibe_heal.ai_tools import AIToolFactory, AIToolType
from vibe_heal.sonarqube.models import SonarQubeIssue

# Create tool
tool = AIToolFactory.create(AIToolType.CLAUDE_CODE)

# Check availability
if not tool.is_available():
    print("Claude Code not available")
    exit(1)

# Fix an issue
issue = SonarQubeIssue(
    key="issue-123",
    rule="python:S1481",
    severity="MAJOR",
    message="Remove unused import",
    component="project:src/main.py",
    line=10,
    status="OPEN",
    type="CODE_SMELL",
)

result = await tool.fix_issue(issue, "src/main.py")

if result.success:
    print(f"Fixed! Modified files: {result.files_modified}")
else:
    print(f"Failed: {result.error_message}")
```

## Verification Steps

1. Run tests:
   ```bash
   uv run pytest tests/ai_tools/ -v --cov=src/vibe_heal/ai_tools
   ```

2. Manual test (requires Claude Code installed):
   ```python
   import asyncio
   from vibe_heal.ai_tools import ClaudeCodeTool
   from vibe_heal.sonarqube.models import SonarQubeIssue

   async def test():
       tool = ClaudeCodeTool()
       print(f"Available: {tool.is_available()}")

       # Create a test issue
       issue = SonarQubeIssue(...)
       result = await tool.fix_issue(issue, "test_file.py")
       print(result)

   asyncio.run(test())
   ```

3. Type checking:
   ```bash
   uv run mypy src/vibe_heal/ai_tools/
   ```

## Definition of Done

- ✅ `AITool` abstract base class
- ✅ `FixResult` model
- ✅ Prompt template system
- ✅ `ClaudeCodeTool` implementation
- ✅ `AIToolFactory` with auto-detection
- ✅ Tool availability checking
- ✅ Timeout handling
- ✅ Error handling (tool not found, file not found, execution errors)
- ✅ Comprehensive tests (>85% coverage)
- ✅ Type checking passes
- ✅ Can invoke Claude Code to fix issues

## Notes

- **Important**: The Claude Code CLI interface in this phase is a placeholder. You'll need to adjust the command-line arguments based on the actual Claude Code CLI API
- The timeout is configurable (default 5 minutes) to handle complex fixes
- Each tool implementation should be in its own file for maintainability
- Aider implementation will be added in Phase 8
- Consider adding retry logic in future if AI tools occasionally fail
- The prompt template is crucial - iterate on it based on real-world results
