"""File operation tools for Agent."""

from pathlib import Path
from typing import Any

from symphony.workspace import PathSafetyError, resolve_workspace_path


def read_file(file_path: str, _workspace: str | None = None, **kwargs: Any) -> dict:
    """Read contents of a file.

    Args:
        file_path: Path to file (relative to workspace or absolute)
        _workspace: Workspace directory (injected by agent)

    Returns:
        Dict with content, path, and size
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
    """Write content to a file.

    Args:
        file_path: Path to file (relative to workspace)
        content: Content to write
        _workspace: Workspace directory (injected by agent)

    Returns:
        Dict with success status and file info
    """
    try:
        path = resolve_workspace_path(file_path, _workspace)
        
        # Create parent directories
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
    """List contents of a directory.

    Args:
        dir_path: Directory path (relative to workspace)
        _workspace: Workspace directory (injected by agent)

    Returns:
        Dict with directory entries
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
