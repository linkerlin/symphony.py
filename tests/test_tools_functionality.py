"""Tests for agent tools functionality.

Tests tool execution with real filesystem and shell operations.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from symphony.agents.tools.file_tools import list_directory, read_file, write_file
from symphony.agents.tools.shell_tool import execute_command


def _normalize_path_for_test(path: Path | str) -> Path:
    """规范化路径以进行比较，处理 macOS /private 前缀。"""
    return Path(os.path.realpath(str(path)))


class TestFileTools:
    """Tests for file operation tools."""
    
    def test_read_existing_file(self):
        """Test reading an existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello, World!")
            
            result = read_file("test.txt", _workspace=tmpdir)
            
            assert result["success"] is True
            assert result["content"] == "Hello, World!"
            # 使用规范化路径进行比较，处理 macOS /private 前缀
            assert _normalize_path_for_test(result["path"]) == _normalize_path_for_test(test_file)
            assert result["size"] == 13
    
    def test_read_nonexistent_file(self):
        """Test reading a file that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = read_file("nonexistent.txt", _workspace=tmpdir)
            
            assert result["success"] is False
            assert "error" in result
            assert "not found" in result["error"].lower() or "does not exist" in result["error"].lower()
    
    def test_write_new_file(self):
        """Test writing a new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = write_file(
                "output.txt",
                "Test content",
                _workspace=tmpdir
            )
            
            assert result["success"] is True
            assert (Path(tmpdir) / "output.txt").read_text() == "Test content"
    
    def test_write_nested_file(self):
        """Test writing a file in nested directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = write_file(
                "subdir/nested/file.txt",
                "Nested content",
                _workspace=tmpdir
            )
            
            assert result["success"] is True
            assert (Path(tmpdir) / "subdir" / "nested" / "file.txt").read_text() == "Nested content"
    
    def test_overwrite_existing_file(self):
        """Test overwriting an existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "existing.txt"
            test_file.write_text("Old content")
            
            result = write_file(
                "existing.txt",
                "New content",
                _workspace=tmpdir
            )
            
            assert result["success"] is True
            assert test_file.read_text() == "New content"
    
    def test_list_empty_directory(self):
        """Test listing an empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = list_directory(".", _workspace=tmpdir)
            
            assert result["success"] is True
            assert result["entries"] == []
            assert result["count"] == 0
    
    def test_list_directory_with_files(self):
        """Test listing directory with files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("file1.txt").touch()
            Path(tmpdir).joinpath("file2.py").touch()
            Path(tmpdir).joinpath("subdir").mkdir()
            
            result = list_directory(".", _workspace=tmpdir)
            
            assert result["success"] is True
            assert result["count"] == 3
            assert "file1.txt" in result["entries"]
            assert "file2.py" in result["entries"]
            assert "subdir" in result["entries"]
    
    def test_list_subdirectory(self):
        """Test listing a subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").touch()
            
            result = list_directory("subdir", _workspace=tmpdir)
            
            assert result["success"] is True
            assert result["count"] == 1
            assert "nested.txt" in result["entries"]


class TestShellTool:
    """Tests for shell command tool."""
    
    async def test_simple_echo(self):
        """Test simple echo command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command("echo hello", _workspace=tmpdir)
            
            assert result["returncode"] == 0
            assert "hello" in result["stdout"]
            assert result["stderr"] == ""
    
    async def test_command_in_workspace(self):
        """Test that command runs in workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command("pwd", _workspace=tmpdir)
            
            assert result["returncode"] == 0
            assert result["stdout"].strip() == str(Path(tmpdir).resolve())
    
    async def test_command_with_error(self):
        """Test handling of failing command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command("exit 42", _workspace=tmpdir)
            
            assert result["returncode"] == 42
    
    async def test_command_with_stderr(self):
        """Test capturing stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command(
                'echo error >&2',
                _workspace=tmpdir
            )
            
            assert result["returncode"] == 0
            assert "error" in result["stderr"]
    
    async def test_command_with_multiple_lines(self):
        """Test command with multi-line output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command(
                'echo "line1\nline2"',
                _workspace=tmpdir
            )
            
            assert result["returncode"] == 0
            assert "line1" in result["stdout"]
            assert "line2" in result["stdout"]
    
    async def test_command_timeout(self):
        """Test command timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command(
                "sleep 5",
                timeout=1,
                _workspace=tmpdir
            )
            
            # Should fail or timeout
            assert result["returncode"] != 0 or "timeout" in result.get("error", "").lower()
    
    async def test_create_file_with_echo(self):
        """Test creating file with echo command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command(
                'echo "file content" > testfile.txt',
                _workspace=tmpdir
            )
            
            assert result["returncode"] == 0
            assert (Path(tmpdir) / "testfile.txt").read_text().strip() == "file content"
    
    async def test_list_files_command(self):
        """Test listing files with ls command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.txt").touch()
            (Path(tmpdir) / "b.py").touch()
            
            result = await execute_command("ls", _workspace=tmpdir)
            
            assert result["returncode"] == 0
            assert "a.txt" in result["stdout"]
            assert "b.py" in result["stdout"]
    
    async def test_piped_commands(self):
        """Test piped commands."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await execute_command(
                'echo "hello world" | tr " " "\n" | wc -l',
                _workspace=tmpdir
            )
            
            assert result["returncode"] == 0
            # Should output 2 (two lines: hello, world)
            assert "2" in result["stdout"]


class TestToolIntegration:
    """Integration tests combining multiple tools."""
    
    async def test_write_read_roundtrip(self):
        """Test writing then reading a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write file
            write_result = write_file(
                "roundtrip.txt",
                "Roundtrip content",
                _workspace=tmpdir
            )
            assert write_result["success"] is True
            
            # Read file
            read_result = read_file("roundtrip.txt", _workspace=tmpdir)
            assert read_result["success"] is True
            assert read_result["content"] == "Roundtrip content"
    
    async def test_shell_and_file_tools(self):
        """Test using shell and file tools together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with shell
            await execute_command(
                'echo "shell created" > shell.txt',
                _workspace=tmpdir
            )
            
            # Read with file tool
            read_result = read_file("shell.txt", _workspace=tmpdir)
            assert read_result["content"].strip() == "shell created"
            
            # Write with file tool
            write_file("file.txt", "file created", _workspace=tmpdir)
            
            # Verify with shell
            result = await execute_command("cat file.txt", _workspace=tmpdir)
            assert result["stdout"].strip() == "file created"
    
    async def test_directory_listing_and_navigation(self):
        """Test directory operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create structure with file tool
            write_file("dir1/file1.txt", "content1", _workspace=tmpdir)
            write_file("dir2/file2.txt", "content2", _workspace=tmpdir)
            
            # List root
            root_list = list_directory(".", _workspace=tmpdir)
            assert root_list["count"] == 2
            assert "dir1" in root_list["entries"]
            assert "dir2" in root_list["entries"]
            
            # List subdir
            dir1_list = list_directory("dir1", _workspace=tmpdir)
            assert dir1_list["count"] == 1
            assert "file1.txt" in dir1_list["entries"]
    
    async def test_complex_workflow(self):
        """Test a complex workflow using multiple tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a Python file
            code = '''
def greet(name):
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("World"))
'''
            write_result = write_file("greet.py", code, _workspace=tmpdir)
            assert write_result["success"]
            
            # List files
            list_result = list_directory(".", _workspace=tmpdir)
            assert "greet.py" in list_result["entries"]
            
            # Run the Python file
            run_result = await execute_command(
                "python greet.py",
                _workspace=tmpdir
            )
            assert run_result["returncode"] == 0
            assert "Hello, World!" in run_result["stdout"]
            
            # Read the file
            read_result = read_file("greet.py", _workspace=tmpdir)
            assert "def greet" in read_result["content"]
