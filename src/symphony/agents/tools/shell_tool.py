"""Agent 的 Shell 命令执行工具。"""

import asyncio
from pathlib import Path
from typing import Any


async def execute_command(
    command: str,
    _workspace: str = "",
    timeout: int = 60,
    **kwargs: Any,
) -> dict[str, Any]:
    """在工作区中执行 Shell 命令。

    Args:
        command: 要执行的 Shell 命令
        _workspace: 工作区目录（由 Agent 注入）
        timeout: 命令超时时间（秒）

    Returns:
        包含 stdout、stderr 和返回码的字典
    """
    workspace = Path(_workspace).resolve()

    # 运行命令
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
