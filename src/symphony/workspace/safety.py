"""Path safety validation for workspaces.

Ensures workspace paths stay within configured root directory.
"""

from __future__ import annotations

import re
from pathlib import Path


class PathSafetyError(Exception):
    """Raised when a path fails safety checks."""

    pass


def resolve_workspace_path(file_path: str, workspace: str | None = None) -> Path:
    """Resolve a file path relative to workspace with safety checks.
    
    Args:
        file_path: Path to resolve (relative or absolute)
        workspace: Workspace root directory (optional)
        
    Returns:
        Resolved Path object
        
    Raises:
        PathSafetyError: If path escapes workspace or contains traversal
    """
    # Handle absolute paths
    path = Path(file_path)
    
    if workspace is None:
        # No workspace specified, use current directory
        return path.resolve()
    
    workspace_path = Path(workspace).expanduser().resolve()
    
    # Check for path traversal attempts
    if PathSafety.check_path_traversal(file_path):
        raise PathSafetyError(
            f"Path traversal detected: {file_path}"
        )
    
    # Resolve relative to workspace
    if path.is_absolute():
        # If absolute, check it's within workspace
        try:
            path.relative_to(workspace_path)
            return path
        except ValueError:
            raise PathSafetyError(
                f"Absolute path {file_path} is outside workspace {workspace_path}"
            )
    else:
        # Relative path - join with workspace
        full_path = (workspace_path / path).resolve()
        
        # Verify resolved path is still within workspace
        try:
            full_path.relative_to(workspace_path)
        except ValueError:
            raise PathSafetyError(
                f"Resolved path {full_path} escapes workspace {workspace_path}"
            )
        
        # Check for symlink escapes
        if full_path.exists() and full_path.is_symlink():
            real_path = full_path.resolve()
            try:
                real_path.relative_to(workspace_path)
            except ValueError:
                raise PathSafetyError(
                    f"Symlink {full_path} points outside workspace"
                )
        
        return full_path


class PathSafety:
    """Validates workspace path safety.

    Ensures that:
    1. Workspace paths stay within the configured root
    2. Path components are sanitized
    3. Symlink escapes are detected
    """

    # Characters allowed in workspace directory names
    SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")

    @classmethod
    def sanitize_identifier(cls, identifier: str) -> str:
        """Sanitize an issue identifier for use as directory name.

        Replaces any character not in [A-Za-z0-9._-] with underscore.

        Args:
            identifier: Raw issue identifier

        Returns:
            Sanitized identifier safe for filesystem use
        """
        if not identifier:
            return "unknown"

        # Replace unsafe characters with underscore
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", identifier)

        # Remove leading/trailing dots (could be hidden files)
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
        """Validate that workspace path is within root.

        Args:
            workspace_path: Path to validate
            root_path: Root directory that must contain workspace

        Returns:
            Resolved Path object

        Raises:
            PathSafetyError: If path is outside root or invalid
        """
        root = Path(root_path).expanduser().resolve()
        workspace = Path(workspace_path).expanduser().resolve()

        # Check workspace equals root (not allowed)
        if workspace == root:
            raise PathSafetyError(
                f"Workspace cannot be the same as root: {workspace}"
            )

        # Check workspace is under root
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
        """Get safe workspace path for an issue.

        Args:
            identifier: Issue identifier
            root_path: Workspace root directory

        Returns:
            Safe workspace path
        """
        root = Path(root_path).expanduser().resolve()
        safe_id = cls.sanitize_identifier(identifier)
        return root / safe_id

    @classmethod
    def is_safe_path_component(cls, name: str) -> bool:
        """Check if a path component is safe.

        Args:
            name: Path component to check

        Returns:
            True if safe for filesystem use
        """
        if not name:
            return False

        if name in (".", ".."):
            return False

        return bool(cls.SAFE_IDENTIFIER_PATTERN.match(name))

    @classmethod
    def check_path_traversal(cls, path: str) -> bool:
        """Check if path contains traversal attempts.

        Args:
            path: Path to check

        Returns:
            True if path contains traversal attempts
        """
        normalized = path.replace("\\", "/")
        return ".." in normalized or normalized.startswith("/")
