"""工作空间管理模块。

处理每个 Issue 的工作空间的创建、验证和生命周期管理。
"""

from symphony.workspace.manager import WorkspaceManager
from symphony.workspace.safety import PathSafety, PathSafetyError, resolve_workspace_path

__all__ = ["WorkspaceManager", "PathSafety", "PathSafetyError", "resolve_workspace_path"]
