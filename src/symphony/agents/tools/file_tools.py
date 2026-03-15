"""Agent 的文件操作工具。"""

from pathlib import Path
from typing import Any

from symphony.workspace import PathSafetyError, resolve_workspace_path


def read_file(file_path: str, _workspace: str | None = None, **kwargs: Any) -> dict:
    """读取文件内容。

    Args:
        file_path: 文件路径（相对于工作区或绝对路径）
        _workspace: 工作区目录（由 Agent 注入）

    Returns:
        包含 content、path 和 size 的字典
    """
    try:
        path = resolve_workspace_path(file_path, _workspace)
        
        if not path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}",
            }
        
        if not path.is_file():
            return {
                "success": False,
                "error": f"Path is not a file: {file_path}",
            }
        
        content = path.read_text(encoding="utf-8")
        return {
            "success": True,
            "content": content,
            "path": str(path),
            "size": len(content),
        }
    except PathSafetyError as e:
        return {
            "success": False,
            "error": f"Security violation: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def write_file(
    file_path: str,
    content: str,
    _workspace: str | None = None,
    **kwargs: Any,
) -> dict:
    """将内容写入文件。

    Args:
        file_path: 文件路径（相对于工作区）
        content: 要写入的内容
        _workspace: 工作区目录（由 Agent 注入）

    Returns:
        包含成功状态和文件信息的字典
    """
    try:
        path = resolve_workspace_path(file_path, _workspace)
        
        # 创建父目录
        path.parent.mkdir(parents=True, exist_ok=True)
        
        path.write_text(content, encoding="utf-8")
        
        return {
            "success": True,
            "path": str(path),
            "bytes_written": len(content.encode("utf-8")),
            "message": f"Successfully wrote {len(content)} characters to {file_path}",
        }
    except PathSafetyError as e:
        return {
            "success": False,
            "error": f"Security violation: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def list_directory(
    dir_path: str = ".",
    _workspace: str | None = None,
    **kwargs: Any,
) -> dict:
    """列出目录内容。

    Args:
        dir_path: 目录路径（相对于工作区）
        _workspace: 工作区目录（由 Agent 注入）

    Returns:
        包含目录条目的字典
    """
    try:
        path = resolve_workspace_path(dir_path, _workspace)
        
        if not path.exists():
            return {
                "success": False,
                "error": f"Directory not found: {dir_path}",
            }
        
        if not path.is_dir():
            return {
                "success": False,
                "error": f"Path is not a directory: {dir_path}",
            }
        
        entries = []
        for p in sorted(path.iterdir()):
            entry = {
                "name": p.name,
                "type": "directory" if p.is_dir() else "file",
            }
            if p.is_file():
                entry["size"] = p.stat().st_size
            entries.append(entry)
        
        return {
            "success": True,
            "path": str(path),
            "entries": [e["name"] for e in entries],
            "details": entries,
            "count": len(entries),
        }
    except PathSafetyError as e:
        return {
            "success": False,
            "error": f"Security violation: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
