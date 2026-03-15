"""Workspace manager for Symphony.

Handles creation, validation, and lifecycle of per-issue workspaces.
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
    """Raised when workspace operation fails."""

    pass


class WorkspaceManager:
    """Manages per-issue workspaces.

    Responsible for:
    - Creating and validating workspace directories
    - Running lifecycle hooks
    - Cleaning up workspaces
    """

    def __init__(
        self,
        root: str | Path,
        hooks: dict[str, str | None] | None = None,
        hook_timeout_ms: int = 60000,
    ) -> None:
        """Initialize workspace manager.

        Args:
            root: Root directory for all workspaces
            hooks: Dict with hook scripts (after_create, before_run, after_run, before_remove)
            hook_timeout_ms: Timeout for hook execution
        """
        self.root = Path(root).expanduser().resolve()
        self.hooks = hooks or {}
        self.hook_timeout_ms = hook_timeout_ms

        # Ensure root exists
        self.root.mkdir(parents=True, exist_ok=True)

    def _get_workspace_path(self, identifier: str) -> Path:
        """Get workspace path for an issue identifier.

        Args:
            identifier: Issue identifier

        Returns:
            Path to workspace directory
        """
        return PathSafety.get_workspace_path(identifier, self.root)

    async def create_for_issue(
        self,
        issue: Issue,
    ) -> tuple[Path, bool]:
        """Create workspace for an issue.

        Args:
            issue: Issue to create workspace for

        Returns:
            Tuple of (workspace_path, created_new)
            created_new is True if directory was newly created

        Raises:
            WorkspaceError: If workspace creation fails
        """
        workspace_path = self._get_workspace_path(issue.identifier)

        # Validate path safety
        try:
            PathSafety.validate_workspace_path(workspace_path, self.root)
        except PathSafetyError as e:
            raise WorkspaceError(f"Invalid workspace path: {e}") from e

        created_new = False

        # Handle existing path
        if workspace_path.exists():
            if workspace_path.is_dir():
                logger.debug(f"Reusing existing workspace: {workspace_path}")
                return workspace_path, False
            else:
                # Remove non-directory file
                logger.warning(f"Removing non-directory at workspace path: {workspace_path}")
                if workspace_path.is_file():
                    workspace_path.unlink()
                else:
                    shutil.rmtree(workspace_path)

        # Create directory
        try:
            workspace_path.mkdir(parents=True, exist_ok=True)
            created_new = True
            logger.info(f"Created workspace: {workspace_path}")
        except OSError as e:
            raise WorkspaceError(f"Failed to create workspace: {e}") from e

        # Run after_create hook
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
        """Remove workspace for an issue.

        Args:
            identifier: Issue identifier
            run_hook: Whether to run before_remove hook

        Raises:
            WorkspaceError: If removal fails
        """
        workspace_path = self._get_workspace_path(identifier)

        if not workspace_path.exists():
            logger.debug(f"Workspace does not exist, nothing to remove: {workspace_path}")
            return

        # Validate path safety
        try:
            PathSafety.validate_workspace_path(workspace_path, self.root)
        except PathSafetyError as e:
            raise WorkspaceError(f"Invalid workspace path: {e}") from e

        # Run before_remove hook
        if run_hook:
            hook = self.hooks.get("before_remove")
            if hook:
                try:
                    await self._run_hook(hook, workspace_path, None, "before_remove")
                except Exception as e:
                    logger.warning(f"before_remove hook failed: {e}")

        # Remove directory
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
        """Run before_run hook.

        Args:
            workspace_path: Path to workspace
            issue: Issue being processed

        Raises:
            WorkspaceError: If hook fails
        """
        hook = self.hooks.get("before_run")
        if hook:
            await self._run_hook(hook, Path(workspace_path), issue, "before_run")

    async def run_after_run_hook(
        self,
        workspace_path: str | Path,
        issue: Issue,
    ) -> None:
        """Run after_run hook.

        Args:
            workspace_path: Path to workspace
            issue: Issue being processed

        Note:
            Hook failures are logged but not raised.
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
        """Run a hook script in the workspace.

        Args:
            script: Shell script to run
            workspace_path: Working directory for script
            issue: Optional issue context
            hook_name: Name of hook for logging

        Raises:
            WorkspaceError: If hook fails or times out
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
        """List all existing workspace directories.

        Returns:
            List of workspace paths
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
        """Remove workspaces for issues in terminal states.

        Args:
            terminal_identifiers: List of issue identifiers in terminal states
        """
        terminal_set = set(terminal_identifiers)

        for workspace in self.list_workspaces():
            if workspace.name in terminal_set:
                try:
                    # Run before_remove hook
                    hook = self.hooks.get("before_remove")
                    if hook:
                        try:
                            await self._run_hook(hook, workspace, None, "before_remove")
                        except Exception as e:
                            logger.warning(f"before_remove hook failed: {e}")

                    # Remove workspace
                    shutil.rmtree(workspace)
                    logger.info(f"Cleaned terminal workspace: {workspace}")
                except Exception as e:
                    logger.warning(f"Failed to clean workspace {workspace}: {e}")
