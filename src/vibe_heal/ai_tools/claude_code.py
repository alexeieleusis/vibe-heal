"""Claude Code AI tool implementation."""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

import aiofiles

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
        # Create a temporary file for the detailed instructions
        temp_file = None
        try:
            # Create temp file with the prompt
            fd, temp_file = tempfile.mkstemp(suffix=".txt", text=True)
            os.close(fd)  # Close the file descriptor immediately
            async with aiofiles.open(temp_file, mode="w") as f:
                await f.write(prompt)

            # Build command with JSON output for structured parsing
            # Pass a simple prompt that references the temp file
            cmd = [
                "claude",
                "--print",
                f"Please implement the changes specified in {temp_file}",
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

        finally:
            # Clean up temporary file
            if temp_file and Path(temp_file).exists():
                Path(temp_file).unlink()

    def _parse_modified_files(self, json_output: str, file_path: str) -> list[str]:
        """Parse JSON output to extract modified files.

        Args:
            json_output: JSON output from Claude CLI
            file_path: The file we asked Claude to fix

        Returns:
            List of modified file paths
        """
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError:
            # If JSON parsing fails, assume the file was modified
            return [file_path]

        # Extract modified files from tool uses
        modified_files = self._extract_modified_files_from_data(data)

        # If we found specific modified files, return them
        if modified_files:
            return list(modified_files)

        # Otherwise, assume the target file was modified if JSON was valid
        return [file_path]

    def _extract_modified_files_from_data(self, data: dict | list) -> set[str]:
        """Extract modified files from Claude CLI JSON data.

        Args:
            data: Parsed JSON data from Claude CLI

        Returns:
            Set of modified file paths
        """
        modified_files: set[str] = set()

        if not isinstance(data, dict):
            return modified_files

        # Check for 'toolUses' or similar fields that indicate Edit/Write operations
        tool_uses = data.get("toolUses", [])
        for tool_use in tool_uses:
            file_path = self._extract_file_path_from_tool_use(tool_use)
            if file_path:
                modified_files.add(file_path)

        return modified_files

    def _extract_file_path_from_tool_use(self, tool_use: dict | list) -> str | None:
        """Extract file path from a tool use entry.

        Args:
            tool_use: Tool use dictionary

        Returns:
            File path if found, None otherwise
        """
        if not isinstance(tool_use, dict):
            return None

        tool_name = tool_use.get("name", "")
        # Edit and Write tools modify files
        if tool_name not in ("Edit", "Write"):
            return None

        # Extract file_path parameter if present
        params = tool_use.get("parameters", {})
        if isinstance(params, dict) and "file_path" in params:
            return cast(str, params["file_path"])

        return None
