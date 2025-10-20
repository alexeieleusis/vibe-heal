"""Claude Code AI tool implementation."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.models import FixResult

if TYPE_CHECKING:
    from vibe_heal.sonarqube.models import SonarQubeIssue, SonarQubeRule, SourceLine


class ClaudeCodeTool(AITool):
    """Claude Code AI tool implementation."""

    tool_type = AIToolType.CLAUDE_CODE

    def __init__(self, timeout: int = 300) -> None:
        """Initialize Claude Code tool.

        Args:
            timeout: Timeout in seconds for AI operations (default: 5 minutes)
        """
        self.timeout = timeout

    def is_available(self) -> bool:
        """Check if Claude CLI is installed.

        Returns:
            True if claude command is available
        """
        return shutil.which("claude") is not None

    async def fix_issue(
        self,
        issue: "SonarQubeIssue",
        file_path: str,
        rule: "SonarQubeRule | None" = None,
        code_context: "list[SourceLine] | None" = None,
    ) -> FixResult:
        """Fix an issue using Claude Code.

        Args:
            issue: The SonarQube issue to fix
            file_path: Path to the file containing the issue
            rule: Detailed rule information (optional)
            code_context: Source code lines around the issue (optional)

        Returns:
            Result of the fix attempt
        """
        # Import here to avoid circular dependency
        from vibe_heal.ai_tools.prompts import create_fix_prompt

        if not self.is_available():
            return FixResult(
                success=False,
                error_message="Claude CLI not found. Please install Claude Code first.",
            )

        # Verify file exists
        if not Path(file_path).exists():
            return FixResult(
                success=False,
                error_message=f"File not found: {file_path}",
            )

        # Create prompt with enriched context
        prompt = create_fix_prompt(issue, file_path, rule=rule, code_context=code_context)

        # Invoke Claude
        try:
            result = await self._invoke_claude(prompt, file_path)
            return result
        except asyncio.TimeoutError:
            return FixResult(
                success=False,
                error_message=f"Claude timed out after {self.timeout} seconds",
            )
        except Exception as e:
            return FixResult(
                success=False,
                error_message=f"Error invoking Claude: {e}",
            )

    async def _invoke_claude(
        self,
        prompt: str,
        file_path: str,
    ) -> FixResult:
        """Invoke Claude CLI.

        Args:
            prompt: The prompt to send to Claude
            file_path: File to fix

        Returns:
            FixResult with outcome
        """
        # Build command with JSON output for structured parsing
        cmd = [
            "claude",
            "--print",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Edit,Read",
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
                timeout=self.timeout,
            )

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""

            # Check if successful
            if process.returncode == 0:
                # Parse JSON response to extract information
                files_modified = self._parse_modified_files(stdout_text, file_path)

                return FixResult(
                    success=True,
                    files_modified=files_modified,
                    ai_response=stdout_text,
                )
            return FixResult(
                success=False,
                error_message=f"Claude failed with exit code {process.returncode}: {stderr_text}",
                ai_response=stdout_text,
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

    def _parse_modified_files(self, json_output: str, file_path: str) -> list[str]:
        """Parse JSON output to extract modified files.

        Args:
            json_output: JSON output from Claude CLI
            file_path: The file we asked Claude to fix

        Returns:
            List of modified file paths
        """
        try:
            # Validate JSON structure (will raise JSONDecodeError if invalid)
            json.loads(json_output)
            # Look for tool uses that indicate file modifications
            # The structure may vary, but typically Edit tool usage indicates modifications
            # For now, assume the file was modified if command succeeded
            # TODO: Parse actual tool usage from JSON response to be more precise
            return [file_path]
        except json.JSONDecodeError:
            # If JSON parsing fails, assume the file was modified
            return [file_path]
