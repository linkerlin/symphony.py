"""工作空间的路径安全验证。

确保工作空间路径始终位于配置的根目录内。
"""

from __future__ import annotations

import re
from pathlib import Path


class PathSafetyError(Exception):
    """当路径未通过安全检查时抛出。"""

    pass


def _normalize_path_for_comparison(path: Path) -> Path:
    """规范化路径以进行比较，处理 macOS /private 前缀。
    
    在 macOS 上，/var/folders/... 会被解析为 /private/var/folders/...
    这会导致路径比较失败。此函数通过比较 realpath 来规范化路径。
    
    参数:
        path: 要规范化的路径
        
    返回:
        规范化后的路径
    """
    import os
    # 使用 os.path.realpath 来获取真实的绝对路径
    real_path = os.path.realpath(path)
    return Path(real_path)


def resolve_workspace_path(file_path: str, workspace: str | None = None) -> Path:
    """解析相对于工作空间的路径，并进行安全检查。
    
    参数:
        file_path: 要解析的路径（相对或绝对）
        workspace: 工作空间根目录（可选）
        
    返回:
        解析后的 Path 对象
        
    抛出:
        PathSafetyError: 如果路径逸出工作空间或包含路径遍历
    """
    # 处理绝对路径
    path = Path(file_path)
    
    if workspace is None:
        # 未指定工作空间，使用当前目录
        return path.resolve()
    
    # 使用 realpath 来规范化工作空间路径（处理 macOS /private 前缀）
    import os
    workspace_real = os.path.realpath(os.path.expanduser(workspace))
    workspace_path = Path(workspace_real)
    
    # 检查路径遍历尝试（仅对相对路径，绝对路径在下面检查是否在工作空间内）
    if not path.is_absolute() and PathSafety.check_path_traversal(file_path):
        raise PathSafetyError(
            f"Path traversal detected: {file_path}"
        )
    
    # 解析相对于工作空间的路径
    if path.is_absolute():
        # 如果是绝对路径，检查是否在工作空间内
        # 使用 realpath 进行规范化比较
        path_real = os.path.realpath(path)
        try:
            Path(path_real).relative_to(workspace_path)
            # 返回原始路径，但确保它在工作空间内
            return Path(path_real)
        except ValueError:
            raise PathSafetyError(
                f"Absolute path {file_path} is outside workspace {workspace_path}"
            )
    else:
        # 相对路径 - 与工作空间拼接
        full_path = (workspace_path / path).resolve()
        full_path_real = os.path.realpath(full_path)
        
        # 验证解析后的路径仍在工作空间内（使用规范化路径比较）
        try:
            Path(full_path_real).relative_to(workspace_path)
        except ValueError:
            raise PathSafetyError(
                f"Resolved path {full_path} escapes workspace {workspace_path}"
            )
        
        # 检查符号链接逸出
        if full_path.exists() and full_path.is_symlink():
            real_path = os.path.realpath(full_path)
            try:
                Path(real_path).relative_to(workspace_path)
            except ValueError:
                raise PathSafetyError(
                    f"Symlink {full_path} points outside workspace"
                )
        
        return Path(full_path_real)


class PathSafety:
    """验证工作空间路径安全。

    确保：
    1. 工作空间路径位于配置的根目录内
    2. 路径组件已清理
    3. 检测到符号链接逸出
    """

    # 工作空间目录名中允许的字符
    SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")

    @classmethod
    def sanitize_identifier(cls, identifier: str) -> str:
        """清理 Issue 标识符，使其可作为目录名使用。

        将任何不在 [A-Za-z0-9._-] 范围内的字符替换为下划线。

        参数:
            identifier: 原始 Issue 标识符

        返回:
            适合文件系统使用的已清理标识符
        """
        if not identifier:
            return "unknown"

        # 将不安全的字符替换为下划线
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", identifier)

        # 移除首尾的点（可能是隐藏文件）
        sanitized = sanitized.strip(".")

        if not sanitized:
            return "unknown"

        return sanitized

    @classmethod
    def validate_workspace_path(
        cls,
        workspace_path: str | Path,
        root_path: str | Path,
    ) -> Path:
        """验证工作空间路径是否在根目录内。

        参数:
            workspace_path: 要验证的路径
            root_path: 必须包含工作空间的根目录

        返回:
            解析后的 Path 对象

        抛出:
            PathSafetyError: 如果路径在根目录外或无效
        """
        root = Path(root_path).expanduser().resolve()
        workspace = Path(workspace_path).expanduser().resolve()

        # 检查工作空间是否等于根目录（不允许）
        if workspace == root:
            raise PathSafetyError(
                f"Workspace cannot be the same as root: {workspace}"
            )

        # 检查工作空间是否在根目录下
        try:
            workspace.relative_to(root)
        except ValueError:
            raise PathSafetyError(
                f"Workspace {workspace} is outside root {root}"
            )

        return workspace

    @classmethod
    def get_workspace_path(
        cls,
        identifier: str,
        root_path: str | Path,
    ) -> Path:
        """获取 Issue 的安全工作空间路径。

        参数:
            identifier: Issue 标识符
            root_path: 工作空间根目录

        返回:
            安全的工作空间路径
        """
        root = Path(root_path).expanduser().resolve()
        safe_id = cls.sanitize_identifier(identifier)
        return root / safe_id

    @classmethod
    def is_safe_path_component(cls, name: str) -> bool:
        """检查路径组件是否安全。

        参数:
            name: 要检查的路径组件

        返回:
            如果适合文件系统使用则返回 True
        """
        if not name:
            return False

        if name in (".", ".."):
            return False

        return bool(cls.SAFE_IDENTIFIER_PATTERN.match(name))

    @classmethod
    def check_path_traversal(cls, path: str) -> bool:
        """检查路径是否包含遍历尝试。

        参数:
            path: 要检查的路径

        返回:
            如果路径包含遍历尝试则返回 True
        """
        normalized = path.replace("\\", "/")
        return ".." in normalized or normalized.startswith("/")
