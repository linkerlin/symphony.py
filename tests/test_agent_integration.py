"""Integration tests for SymphonyAgent with real LLM calls.

Tests agent behavior including tool use and multi-turn conversations.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from symphony.agents.agent import SymphonyAgent
from symphony.llm.client import LLMClient
from symphony.models.issue import Issue
from symphony.prompts.builder import PromptBuilder


@pytest.mark.llm
@pytest.mark.timeout(15)
class TestAgentBasicExecution:
    """Tests for basic agent execution with real LLM."""
    
    async def test_agent_simple_task(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test agent completing a simple task."""
        prompt_builder = PromptBuilder(template="{{description}}")
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={},
        )
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Simple math",
            description="What is 5 + 3? Answer with just the number.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=3,
        )
        
        assert result["success"] is True
        assert result["turns"] <= 3
        assert result["total_tokens"]["prompt"] > 0
        assert result["total_tokens"]["completion"] > 0
        
        # Check response contains "8"
        messages = result.get("messages", [])
        content = " ".join(m.get("content", "") for m in messages)
        assert "8" in content
    
    async def test_agent_with_no_tools(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test agent behavior when no tools are available."""
        prompt_builder = PromptBuilder(template="{{description}}")
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={},  # No tools
        )
        
        issue = Issue(
            id="test-2",
            identifier="TEST-2",
            title="Greeting",
            description="Say hello to the user.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=2,
        )
        
        assert result["success"] is True
        
        # Should complete without tool calls
        messages = result.get("messages", [])
        content = " ".join(m.get("content", "") for m in messages)
        assert "hello" in content.lower()


@pytest.mark.llm
@pytest.mark.timeout(20)
class TestAgentToolUse:
    """Tests for agent tool usage with real LLM."""
    
    async def test_agent_reads_file(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test agent using read_file tool."""
        from symphony.agents.tools import read_file
        
        prompt_builder = PromptBuilder(
            template="""You have access to tools. 
Task: {{description}}
Use the read_file tool to read 'test.py' and tell me what it contains.
Respond with the file content."""
        )
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={"read_file": read_file},
        )
        
        issue = Issue(
            id="test-3",
            identifier="TEST-3",
            title="Read file",
            description="Read the test.py file in the workspace.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=5,
        )
        
        assert result["success"] is True
        
        # Should have read the file and reported content
        messages = result.get("messages", [])
        content = " ".join(m.get("content", "") for m in messages)
        
        # The file contains "print('hello')"
        assert "hello" in content.lower() or "print" in content
    
    async def test_agent_writes_file(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test agent using write_file tool."""
        from symphony.agents.tools import write_file
        
        prompt_builder = PromptBuilder(
            template="""You have access to tools.
Task: {{description}}
Use the write_file tool to create the file."""
        )
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={"write_file": write_file},
        )
        
        issue = Issue(
            id="test-4",
            identifier="TEST-4",
            title="Write file",
            description="Create a file called 'math.py' with a function 'add(a, b)' that returns a + b.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=5,
        )
        
        assert result["success"] is True
        
        # Check file was created
        math_file = temp_workspace / "math.py"
        assert math_file.exists(), f"File not created: {math_file}"
        
        content = math_file.read_text()
        assert "def add" in content
    
    async def test_agent_executes_command(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test agent using execute_command tool."""
        from symphony.agents.tools import execute_command
        
        prompt_builder = PromptBuilder(
            template="""You have access to tools including execute_command.
Task: {{description}}
Use the execute_command tool to run 'echo test_success'."""
        )
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={"execute_command": execute_command},
        )
        
        issue = Issue(
            id="test-5",
            identifier="TEST-5",
            title="Run command",
            description="Run a shell command and report the output.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=5,
        )
        
        assert result["success"] is True
        
        # Should have executed command and reported output
        messages = result.get("messages", [])
        content = " ".join(m.get("content", "") for m in messages)
        assert "test_success" in content or "execute" in content.lower()


@pytest.mark.llm
@pytest.mark.timeout(15)
class TestAgentPromptHandling:
    """Tests for agent prompt building and handling."""
    
    async def test_prompt_with_issue_data(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test that issue data is properly included in prompts."""
        prompt_builder = PromptBuilder(
            template="""Issue: {{identifier}}
Title: {{title}}
Description: {{description}}"""
        )
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={},
        )
        
        issue = Issue(
            id="test-6",
            identifier="PROJ-123",
            title="Test Title",
            description="Test Description",
            state="Todo",
            labels=["bug"],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=2,
        )
        
        assert result["success"] is True
        
        # Check that prompt was built with issue data
        messages = result.get("messages", [])
        system_msg = next((m for m in messages if m.get("role") == "system"), None)
        
        # System prompt should mention workspace
        if system_msg:
            assert "workspace" in system_msg.get("content", "").lower()
    
    async def test_retry_attempt_context(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test that retry attempt is passed to prompt builder."""
        prompt_builder = PromptBuilder(
            template="""{{description}}
Attempt: {{attempt}}"""
        )
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={},
        )
        
        issue = Issue(
            id="test-7",
            identifier="TEST-7",
            title="Retry test",
            description="Test retry context.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        # Run with attempt=2
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=2,
            attempt=2,
        )
        
        assert result["success"] is True


@pytest.mark.llm
@pytest.mark.timeout(10)
class TestAgentErrorHandling:
    """Tests for agent error handling."""
    
    async def test_max_turns_exceeded(self, fast_llm_client: LLMClient, temp_workspace: Path):
        """Test that agent respects max_turns limit."""
        prompt_builder = PromptBuilder(template="{{description}}")
        
        agent = SymphonyAgent(
            llm_client=fast_llm_client,
            prompt_builder=prompt_builder,
            tools={},
        )
        
        issue = Issue(
            id="test-8",
            identifier="TEST-8",
            title="Multi-turn",
            description="Have a conversation. Respond with 'continue' each time.",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = await agent.run(
            issue=issue,
            workspace_path=temp_workspace,
            max_turns=2,  # Very limited
        )
        
        # Should complete without error, respecting max_turns
        assert result["success"] is True
        assert result["turns"] <= 2
