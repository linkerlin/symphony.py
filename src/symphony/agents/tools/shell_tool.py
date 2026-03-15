"""Shell command execution tool for Agent."""

import asyncio
from pathlib import Path
from typing import Any


async def execute_command(
    command: str,
    _workspace: str = "",
    timeout: int = 60,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a shell command in the workspace.

    Args:
        command: Shell command to execute
        _workspace: Workspace directory (injected by agent)
        timeout: Command timeout in seconds

    Returns:
        Dict with stdout, stderr, and return code
    """
    workspace = Path(_workspace).resolve()

    # Run command
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )

        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
            "success": proc.returncode == 0,
        }

    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "returncode": -1,
            "success": False,
        }
