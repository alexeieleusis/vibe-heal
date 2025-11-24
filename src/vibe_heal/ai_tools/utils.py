"""AI tool utilities."""

import asyncio
from pathlib import Path
from typing import NamedTuple


class CommandResult(NamedTuple):
    """Result of an external command."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int | None = None


async def run_command(
    cmd: list[str],
    timeout: int,
) -> CommandResult:
    """Run an external command and capture its output.

    Args:
        cmd: The command to execute, as a list of strings.
        timeout: Timeout in seconds.

    Returns:
        A CommandResult with the outcome.
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=Path.cwd(),
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        stdout = stdout_bytes.decode() if stdout_bytes else ""
        stderr = stderr_bytes.decode() if stderr_bytes else ""

        return CommandResult(
            success=process.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
        )

    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise
