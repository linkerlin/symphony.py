"""Workspace management module.

Handles creation, validation, and lifecycle of per-issue workspaces.
"""

from symphony.workspace.manager import WorkspaceManager
from symphony.workspace.safety import PathSafety, PathSafetyError, resolve_workspace_path

__all__ = ["WorkspaceManager", "PathSafety", "PathSafetyError", "resolve_workspace_path"]
