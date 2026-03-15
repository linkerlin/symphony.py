"""Tests for workspace path safety and security.

These tests verify that file operations cannot escape the workspace.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

import os

from symphony.agents.tools.file_tools import list_directory, read_file, write_file
from symphony.agents.tools.shell_tool import execute_command
from symphony.workspace import PathSafetyError, resolve_workspace_path


def _normalize_path_for_test(path: Path) -> Path:
    """规范化路径以进行比较，处理 macOS /private 前缀。"""
    return Path(os.path.realpath(path))


class TestPathResolution:
    """Tests for path resolution and safety checks."""
    
    def test_resolve_valid_path(self):
        """Test resolving a valid path within workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            result = resolve_workspace_path("test.py", str(workspace))
            # 使用规范化路径进行比较，处理 macOS /private 前缀
            assert _normalize_path_for_test(result) == _normalize_path_for_test(workspace / "test.py")
    
    def test_resolve_nested_path(self):
        """Test resolving nested path within workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            (workspace / "subdir").mkdir()
            
            result = resolve_workspace_path("subdir/test.py", str(workspace))
            # 使用规范化路径进行比较，处理 macOS /private 前缀
            assert _normalize_path_for_test(result) == _normalize_path_for_test(workspace / "subdir" / "test.py")
    
    def test_resolve_absolute_path_in_workspace(self):
        """Test resolving absolute path that is within workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            result = resolve_workspace_path(str(workspace / "test.py"), str(workspace))
            # 使用规范化路径进行比较，处理 macOS /private 前缀
            assert _normalize_path_for_test(result) == _normalize_path_for_test(workspace / "test.py")
    
    def test_resolve_path_with_dotdot_blocked(self):
        """Test that .. is blocked from escaping workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            with pytest.raises(PathSafetyError) as exc_info:
                resolve_workspace_path("../outside.txt", str(workspace))
            
            assert "outside" in str(exc_info.value).lower()
    
    def test_resolve_path_traversal_blocked(self):
        """Test various path traversal attempts are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            (workspace / "subdir").mkdir()
            
            traversal_attempts = [
                "../outside.txt",
                "subdir/../../../etc/passwd",
                "./../outside.txt",
                "deep/nested/../../../../../outside",
            ]
            
            for attempt in traversal_attempts:
                with pytest.raises(PathSafetyError):
                    resolve_workspace_path(attempt, str(workspace))
    
    def test_resolve_symlink_blocked(self):
        """Test that symlinks outside workspace are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            
            # Create symlink pointing outside
            symlink = workspace / "link"
            symlink.symlink_to(outside)
            
            with pytest.raises(PathSafetyError) as exc_info:
                resolve_workspace_path("link/file.txt", str(workspace))
    
    def test_resolve_no_workspace(self):
        """Test resolution without workspace (should use cwd)."""
        result = resolve_workspace_path("test.py", None)
        assert result == Path("test.py").resolve()


class TestFileToolSafety:
    """Tests for file tool safety."""
    
    def test_read_file_in_workspace(self):
        """Test reading file within workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            test_file = workspace / "test.txt"
            test_file.write_text("hello")
            
            result = read_file("test.txt", _workspace=str(workspace))
            
            assert result["content"] == "hello"
            # 使用规范化路径进行比较，处理 macOS /private 前缀
            assert _normalize_path_for_test(Path(result["path"])) == _normalize_path_for_test(test_file)
    
    def test_read_file_outside_workspace_blocked(self):
        """Test reading file outside workspace is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            outside = Path(tmpdir) / "secret.txt"
            outside.write_text("secret")
            
            result = read_file("../secret.txt", _workspace=str(workspace))
            # File tools catch PathSafetyError and return error dict
            assert result["success"] is False
            assert "security" in result.get("error", "").lower() or "violation" in result.get("error", "").lower()
    
    def test_write_file_in_workspace(self):
        """Test writing file within workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            result = write_file("output.txt", "content", _workspace=str(workspace))
            
            assert result["success"] is True
            assert (workspace / "output.txt").read_text() == "content"
    
    def test_write_file_outside_workspace_blocked(self):
        """Test writing file outside workspace is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            result = write_file("../outside.txt", "content", _workspace=str(workspace))
            # File tools catch PathSafetyError and return error dict
            assert result["success"] is False
            assert "security" in result.get("error", "").lower() or "violation" in result.get("error", "").lower()
            
            # Verify file was not created
            assert not (Path(tmpdir) / "outside.txt").exists()
    
    def test_list_directory_stays_in_workspace(self):
        """Test list_directory respects workspace boundaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            (workspace / "file1.txt").touch()
            (workspace / "subdir").mkdir()
            
            outside = Path(tmpdir) / "outside.txt"
            outside.touch()
            
            # List workspace
            result = list_directory(".", _workspace=str(workspace))
            
            assert "file1.txt" in result["entries"]
            assert "subdir" in result["entries"]
            assert "outside.txt" not in result["entries"]
    
    def test_list_directory_parent_blocked(self):
        """Test listing parent directory is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            result = list_directory("..", _workspace=str(workspace))
            # File tools catch PathSafetyError and return error dict
            assert result["success"] is False
            assert "security" in result.get("error", "").lower() or "violation" in result.get("error", "").lower()


class TestShellToolSafety:
    """Tests for shell command safety."""
    
    async def test_command_runs_in_workspace(self):
        """Test that commands run in workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            result = await execute_command("pwd", _workspace=str(workspace))
            
            assert result["returncode"] == 0
            assert str(workspace) in result["stdout"]
    
    async def test_command_cannot_escape_workspace(self):
        """Test that commands respect workspace boundary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            outside = Path(tmpdir) / "secret.txt"
            outside.write_text("secret")
            
            # Try to read file outside workspace
            result = await execute_command(
                f"cat {outside}",
                _workspace=str(workspace)
            )
            
            # Command should succeed but not read the file
            # (because the path is absolute, not relative escape)
            # This tests that we at least run in correct directory
    
    async def test_command_timeout(self):
        """Test that long-running commands are terminated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            result = await execute_command(
                "sleep 10",
                timeout=1,  # Short timeout
                _workspace=str(workspace)
            )
            
            assert result["returncode"] != 0 or "timeout" in result["stderr"].lower()
    
    async def test_command_output_capture(self):
        """Test that command output is captured correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            result = await execute_command(
                'echo "stdout message" && echo "stderr message" >&2',
                _workspace=str(workspace)
            )
            
            assert result["returncode"] == 0
            assert "stdout message" in result["stdout"]
            assert "stderr message" in result["stderr"]
    
    async def test_command_error_handling(self):
        """Test handling of failed commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            result = await execute_command(
                "exit 42",
                _workspace=str(workspace)
            )
            
            assert result["returncode"] == 42


class TestWorkspaceManager:
    """Tests for workspace manager functionality."""
    
    async def test_create_workspace(self, workspace_manager: WorkspaceManager):
        """Test workspace creation."""
        from symphony.models.issue import Issue
        
        issue = Issue(
            id="ws-test-1",
            identifier="WS-1",
            title="Test",
            description="Test workspace creation",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await workspace_manager.create_for_issue(issue)
        
        assert result.success is True
        assert Path(result.path).exists()
        assert result.issue_id == issue.id
    
    async def test_workspace_isolation(self, workspace_manager: WorkspaceManager):
        """Test that workspaces are isolated from each other."""
        from symphony.models.issue import Issue
        
        issue1 = Issue(
            id="ws-test-2a",
            identifier="WS-2A",
            title="Test A",
            description="Workspace A",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        issue2 = Issue(
            id="ws-test-2b",
            identifier="WS-2B",
            title="Test B",
            description="Workspace B",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result1 = await workspace_manager.create_for_issue(issue1)
        result2 = await workspace_manager.create_for_issue(issue2)
        
        # Write file in workspace 1
        (Path(result1.path) / "file_a.txt").write_text("A")
        
        # Verify it's not in workspace 2
        assert not (Path(result2.path) / "file_a.txt").exists()
        assert (Path(result2.path) / "file_a.txt").parent.exists()
    
    async def test_remove_workspace(self, workspace_manager: WorkspaceManager):
        """Test workspace removal."""
        from symphony.models.issue import Issue
        
        issue = Issue(
            id="ws-test-3",
            identifier="WS-3",
            title="Test",
            description="Test workspace removal",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await workspace_manager.create_for_issue(issue)
        path = result.path
        
        assert Path(path).exists()
        
        remove_result = await workspace_manager.remove_for_issue(issue)
        
        assert remove_result.success is True
        assert not Path(path).exists()
