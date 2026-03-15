"""Symphony 的工作空间管理器。

处理每个 Issue 的工作空间的创建、验证和生命周期管理。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from symphony.models.issue import Issue
from symphony.workspace.safety import PathSafety, PathSafetyError

logger = logging.getLogger(__name__)


class WorkspaceError(Exception):
    """当工作空间操作失败时抛出。"""

    pass


class WorkspaceManager:
    """管理每个 Issue 的工作空间。

    职责包括：
    - 创建和验证工作空间目录
    - 运行生命周期钩子
    - 清理工作空间
    """

    def __init__(
        self,
        root: str | Path,
        hooks: dict[str, str | None] | None = None,
        hook_timeout_ms: int = 60000,
    ) -> None:
        """初始化工作空间管理器。

        参数:
            root: 所有工作空间的根目录
            hooks: 钩子脚本字典（after_create、before_run、after_run、before_remove）
            hook_timeout_ms: 钩子执行的超时时间（毫秒）
        """
        self.root = Path(root).expanduser().resolve()
        self.hooks = hooks or {}
        self.hook_timeout_ms = hook_timeout_ms

        # 确保根目录存在
        self.root.mkdir(parents=True, exist_ok=True)

    def _get_workspace_path(self, identifier: str) -> Path:
        """获取 Issue 标识符对应的工作空间路径。

        参数:
            identifier: Issue 标识符

        返回:
            工作空间目录的路径
        """
        return PathSafety.get_workspace_path(identifier, self.root)

    async def create_for_issue(
        self,
        issue: Issue,
    ) -> tuple[Path, bool]:
        """为 Issue 创建工作空间。

        参数:
            issue: 要创建工作空间的 Issue

        返回:
            (workspace_path, created_new) 元组
            如果目录是新创建的，则 created_new 为 True

        抛出:
            WorkspaceError: 如果工作空间创建失败
        """
        workspace_path = self._get_workspace_path(issue.identifier)

        # 验证路径安全性
        try:
            PathSafety.validate_workspace_path(workspace_path, self.root)
        except PathSafetyError as e:
            raise WorkspaceError(f"Invalid workspace path: {e}") from e

        created_new = False

        # 处理已存在的路径
        if workspace_path.exists():
            if workspace_path.is_dir():
                logger.debug(f"Reusing existing workspace: {workspace_path}")
                return workspace_path, False
            else:
                # 删除非目录文件
                logger.warning(f"Removing non-directory at workspace path: {workspace_path}")
                if workspace_path.is_file():
                    workspace_path.unlink()
                else:
                    shutil.rmtree(workspace_path)

        # 创建目录
        try:
            workspace_path.mkdir(parents=True, exist_ok=True)
            created_new = True
            logger.info(f"Created workspace: {workspace_path}")
        except OSError as e:
            raise WorkspaceError(f"Failed to create workspace: {e}") from e

        # 运行 after_create 钩子
        if created_new:
            hook = self.hooks.get("after_create")
            if hook:
                await self._run_hook(hook, workspace_path, issue, "after_create")

        return workspace_path, created_new

    async def remove_workspace(
        self,
        identifier: str,
        run_hook: bool = True,
    ) -> None:
        """删除 Issue 的工作空间。

        参数:
            identifier: Issue 标识符
            run_hook: 是否运行 before_remove 钩子

        抛出:
            WorkspaceError: 如果删除失败
        """
        workspace_path = self._get_workspace_path(identifier)

        if not workspace_path.exists():
            logger.debug(f"Workspace does not exist, nothing to remove: {workspace_path}")
            return

        # 验证路径安全性
        try:
            PathSafety.validate_workspace_path(workspace_path, self.root)
        except PathSafetyError as e:
            raise WorkspaceError(f"Invalid workspace path: {e}") from e

        # 运行 before_remove 钩子
        if run_hook:
            hook = self.hooks.get("before_remove")
            if hook:
                try:
                    await self._run_hook(hook, workspace_path, None, "before_remove")
                except Exception as e:
                    logger.warning(f"before_remove hook failed: {e}")

        # 删除目录
        try:
            shutil.rmtree(workspace_path)
            logger.info(f"Removed workspace: {workspace_path}")
        except OSError as e:
            raise WorkspaceError(f"Failed to remove workspace: {e}") from e

    async def run_before_run_hook(
        self,
        workspace_path: str | Path,
        issue: Issue,
    ) -> None:
        """运行 before_run 钩子。

        参数:
            workspace_path: 工作空间路径
            issue: 正在处理的 Issue

        抛出:
            WorkspaceError: 如果钩子执行失败
        """
        hook = self.hooks.get("before_run")
        if hook:
            await self._run_hook(hook, Path(workspace_path), issue, "before_run")

    async def run_after_run_hook(
        self,
        workspace_path: str | Path,
        issue: Issue,
    ) -> None:
        """运行 after_run 钩子。

        参数:
            workspace_path: 工作空间路径
            issue: 正在处理的 Issue

        说明:
            钩子失败会被记录但不会抛出异常。
        """
        hook = self.hooks.get("after_run")
        if hook:
            try:
                await self._run_hook(hook, Path(workspace_path), issue, "after_run")
            except Exception as e:
                logger.warning(f"after_run hook failed: {e}")

    async def _run_hook(
        self,
        script: str,
        workspace_path: Path,
        issue: Issue | None,
        hook_name: str,
    ) -> None:
        """在工作空间中运行钩子脚本。

        参数:
            script: 要运行的 shell 脚本
            workspace_path: 脚本的工作目录
            issue: 可选的 Issue 上下文
            hook_name: 用于日志记录的钩子名称

        抛出:
            WorkspaceError: 如果钩子失败或超时
        """
        issue_ctx = issue.get_context_string() if issue else "issue=unknown"
        logger.info(f"Running {hook_name} hook: {issue_ctx} workspace={workspace_path}")

        timeout_seconds = self.hook_timeout_ms / 1000

        try:
            proc = await asyncio.create_subprocess_shell(
                script,
                cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise WorkspaceError(
                    f"{hook_name} hook timed out after {timeout_seconds}s"
                )

            if proc.returncode != 0:
                output = stdout.decode("utf-8", errors="replace")[:2000]
                raise WorkspaceError(
                    f"{hook_name} hook failed with exit code {proc.returncode}: {output}"
                )

            logger.debug(f"{hook_name} hook completed successfully")

        except WorkspaceError:
            raise
        except Exception as e:
            raise WorkspaceError(f"{hook_name} hook failed: {e}") from e

    def list_workspaces(self) -> list[Path]:
        """列出所有现有的工作空间目录。

        返回:
            工作空间路径列表
        """
        if not self.root.exists():
            return []

        return [
            p for p in self.root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        ]

    async def clean_terminal_workspaces(
        self,
        terminal_identifiers: list[str],
    ) -> None:
        """删除处于终止状态的 Issue 的工作空间。

        参数:
            terminal_identifiers: 处于终止状态的 Issue 标识符列表
        """
        terminal_set = set(terminal_identifiers)

        for workspace in self.list_workspaces():
            if workspace.name in terminal_set:
                try:
                    # 运行 before_remove 钩子
                    hook = self.hooks.get("before_remove")
                    if hook:
                        try:
                            await self._run_hook(hook, workspace, None, "before_remove")
                        except Exception as e:
                            logger.warning(f"before_remove hook failed: {e}")

                    # 删除工作空间
                    shutil.rmtree(workspace)
                    logger.info(f"Cleaned terminal workspace: {workspace}")
                except Exception as e:
                    logger.warning(f"Failed to clean workspace {workspace}: {e}")
