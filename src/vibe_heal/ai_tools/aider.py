"""Aider AI tool implementation."""

import asyncio
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from vibe_heal.ai_tools.base import AITool, AIToolType
from vibe_heal.ai_tools.models import FixResult

if TYPE_CHECKING:
    from vibe_heal.sonarqube.models import SonarQubeIssue


class AiderTool(AITool):
    """Aider AI tool implementation."""

    tool_type = AIToolType.AIDER

    def __init__(
        self,
        timeout: int = 300,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        """Initialize Aider tool.

        Args:
            timeout: Timeout in seconds for AI operations (default: 5 minutes)
            model: Model to use with Aider (e.g., 'ollama_chat/gemma3:27b')
            api_key: API key for model provider (sets OLLAMA_API_KEY env var)
            api_base: API base URL for model provider (sets OLLAMA_API_BASE env var)
        """
        self.timeout = timeout
        self.model = model
        self.api_key = api_key
        self.api_base = api_base

    def is_available(self) -> bool:
        """Check if Aider CLI is installed.

        Returns:
            True if aider command is available
        """
        return shutil.which("aider") is not None

    async def fix_issue(
        self,
        issue: "SonarQubeIssue",
        file_path: str,
    ) -> FixResult:
        """Fix an issue using Aider.

        Args:
            issue: The SonarQube issue to fix
            file_path: Path to the file containing the issue

        Returns:
            Result of the fix attempt
        """
        # Import here to avoid circular dependency
        from vibe_heal.ai_tools.prompts import create_fix_prompt

        if not self.is_available():
            return FixResult(
                success=False,
                error_message="Aider CLI not found. Please install Aider first.",
            )

        # Verify file exists
        if not Path(file_path).exists():
            return FixResult(
                success=False,
                error_message=f"File not found: {file_path}",
            )

        # Create prompt
        prompt = create_fix_prompt(issue, file_path)

        # Invoke Aider
        try:
            result = await self._invoke_aider(prompt, file_path)
            return result
        except asyncio.TimeoutError:
            return FixResult(
                success=False,
                error_message=f"Aider timed out after {self.timeout} seconds",
            )
        except Exception as e:
            return FixResult(
                success=False,
                error_message=f"Error invoking Aider: {e}",
            )

    async def _invoke_aider(
        self,
        prompt: str,
        file_path: str,
    ) -> FixResult:
        """Invoke Aider CLI.

        Args:
            prompt: The prompt to send to Aider
            file_path: File to fix

        Returns:
            FixResult with outcome
        """
        # Build command
        # --yes: Auto-confirm changes
        # --no-git: Don't auto-commit (we handle commits ourselves)
        # --message: Provide the fix prompt
        cmd = [
            "aider",
            "--yes",
            "--no-git",
            "--message",
            prompt,
            file_path,
        ]

        # Add model flag if specified
        if self.model:
            cmd.extend(["--model", self.model])

        # Prepare environment variables
        env = os.environ.copy()
        if self.api_key:
            env["OLLAMA_API_KEY"] = self.api_key
        if self.api_base:
            env["OLLAMA_API_BASE"] = self.api_base

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd(),
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""

            # Check if successful
            # Aider returns 0 on success, even if no changes were made
            if process.returncode == 0:
                # Aider modifies the file in place
                return FixResult(
                    success=True,
                    files_modified=[file_path],
                    ai_response=stdout_text,
                )
            return FixResult(
                success=False,
                error_message=f"Aider failed with exit code {process.returncode}: {stderr_text}",
                ai_response=stdout_text,
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
