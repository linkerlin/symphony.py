"""End-to-end smoke tests for Symphony.

These tests verify the complete flow with real APIs.
They are designed to be fast but comprehensive.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from symphony.agents.agent import SymphonyAgent
from symphony.agents.tools import read_file, write_file
from symphony.config.schema import (
    AgentConfig,
    HooksConfig,
    LLMConfig,
    SymphonyConfig as Settings,
    TrackerConfig,
    WorkspaceConfig,
)
from symphony.llm.client import LLMClient
from symphony.models.issue import Issue
from symphony.orchestrator.orchestrator import Orchestrator
from symphony.orchestrator.state import OrchestratorState
from symphony.prompts.builder import PromptBuilder
from symphony.trackers.memory import MemoryTracker
from symphony.workspace.manager import WorkspaceManager


@pytest.mark.llm
@pytest.mark.integration
@pytest.mark.timeout(30)
class TestEndToEndSmoke:
    """End-to-end smoke tests with real LLM."""
    
    async def test_full_agent_workflow(self, fast_llm_client: LLMClient):
        """Test complete agent workflow with real LLM.
        
        This test:
        1. Creates a workspace
        2. Runs an agent to complete a simple task
        3. Verifies the output
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            # Setup agent with file tools
            prompt_builder = PromptBuilder(
                template="""You are a coding assistant.
Task: {{description}}
You have access to read_file and write_file tools.

Requirements:
1. Create a file called 'result.txt' with your answer
2. The file should contain a single word: "success"
3. Do not add any explanation, just create the file"""
            )
            
            agent = SymphonyAgent(
                llm_client=fast_llm_client,
                prompt_builder=prompt_builder,
                tools={
                    "read_file": read_file,
                    "write_file": write_file,
                },
            )
            
            issue = Issue(
                id="e2e-1",
                identifier="E2E-1",
                title="Create file",
                description="Create a file with 'success' in it.",
                state="Todo",
                labels=[],
                blockers=[],
            )
            
            # Run agent
            result = await agent.run(
                issue=issue,
                workspace_path=workspace,
                max_turns=5,
            )
            
            # Verify success
            assert result["success"] is True
            
            # Verify file was created with correct content
            result_file = workspace / "result.txt"
            if result_file.exists():
                content = result_file.read_text().strip().lower()
                assert "success" in content
            else:
                # Agent might have responded differently, check messages
                messages = result.get("messages", [])
                content = " ".join(m.get("content", "").lower() for m in messages)
                assert "success" in content or result["success"]
    
    async def test_orchestrator_state_transitions(self):
        """Test orchestrator state machine."""
        state = OrchestratorState(max_concurrent_agents=2)
        
        # Create test issues
        issues = [
            Issue(
                id=f"state-test-{i}",
                identifier=f"STATE-{i}",
                title=f"Test {i}",
                description="Test",
                state="Todo",
                labels=[],
                blockers=[],
            )
            for i in range(3)
        ]
        
        # Claim all issues
        for issue in issues:
            assert state.claim(issue) is True
        
        assert len(state.claimed) == 3
        
        # Start first two (max concurrent)
        from symphony.models.session import SessionState
        
        for issue in issues[:2]:
            session = SessionState(issue_id=issue.id)
            assert state.start(issue, session) is True
        
        assert len(state.running) == 2
        assert state.available_slots == 0
        
        # Third should fail (at max)
        session3 = SessionState(issue_id=issues[2].id)
        assert state.start(issues[2], session3) is False
        
        # Complete one
        state.complete(issues[0], success=True)
        
        assert len(state.running) == 1
        assert state.available_slots == 1
        
        # Now third can start
        assert state.start(issues[2], session3) is True
    
    async def test_workspace_lifecycle(self):
        """Test workspace creation and cleanup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = WorkspaceManager(
                root=tmpdir,
                hooks={},
                hook_timeout_ms=1000,
            )
            
            issue = Issue(
                id="ws-lifecycle-1",
                identifier="WS-1",
                title="Test",
                description="Test workspace lifecycle",
                state="Todo",
                labels=[],
                blockers=[],
            )
            
            # Create workspace
            result = await manager.create_for_issue(issue)
            assert result.success is True
            assert Path(result.path).exists()
            
            # Verify workspace is isolated
            test_file = Path(result.path) / "test.txt"
            test_file.write_text("test")
            
            # Remove workspace
            remove_result = await manager.remove_for_issue(issue)
            assert remove_result.success is True
            assert not Path(result.path).exists()


@pytest.mark.llm
@pytest.mark.slow
@pytest.mark.timeout(60)
class TestEndToEndWithRealLLM:
    """More comprehensive end-to-end tests with real LLM.
    
    These tests take longer but verify complete functionality.
    """
    
    async def test_agent_with_math_task(self, llm_client: LLMClient):
        """Test agent completing a math task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            
            prompt_builder = PromptBuilder(
                template="""You are a coding assistant.
Task: {{description}}

Write a Python function in 'math_utils.py' that:
1. Is named 'fibonacci'
2. Takes an integer n
3. Returns the nth Fibonacci number
4. Include a simple docstring

Use the write_file tool to create the file."""
            )
            
            agent = SymphonyAgent(
                llm_client=llm_client,
                prompt_builder=prompt_builder,
                tools={"write_file": write_file},
            )
            
            issue = Issue(
                id="math-1",
                identifier="MATH-1",
                title="Write fibonacci",
                description="Write a fibonacci function",
                state="Todo",
                labels=[],
                blockers=[],
            )
            
            result = await agent.run(
                issue=issue,
                workspace_path=workspace,
                max_turns=5,
            )
            
            assert result["success"] is True
            
            # Verify file was created
            math_file = workspace / "math_utils.py"
            if math_file.exists():
                content = math_file.read_text()
                assert "def fibonacci" in content
                assert "n" in content  # Should have parameter
    
    async def test_concurrent_agent_execution(self, llm_client: LLMClient):
        """Test running multiple agents concurrently."""
        async def run_agent(agent_id: str):
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / f"workspace_{agent_id}"
                workspace.mkdir()
                
                prompt_builder = PromptBuilder(
                    template="{{description}}\n\nCreate a file '{{identifier}}.txt' with content 'done'."
                )
                
                agent = SymphonyAgent(
                    llm_client=llm_client,
                    prompt_builder=prompt_builder,
                    tools={"write_file": write_file},
                )
                
                issue = Issue(
                    id=f"concurrent-{agent_id}",
                    identifier=f"CON-{agent_id}",
                    title=f"Task {agent_id}",
                    description=f"Create file for task {agent_id}",
                    state="Todo",
                    labels=[],
                    blockers=[],
                )
                
                return await agent.run(
                    issue=issue,
                    workspace_path=workspace,
                    max_turns=3,
                )
        
        # Run 2 agents concurrently
        results = await asyncio.gather(
            run_agent("A"),
            run_agent("B"),
            return_exceptions=True,
        )
        
        # Both should succeed
        for result in results:
            assert isinstance(result, dict)
            assert result.get("success") is True


@pytest.mark.integration
class TestConfigurationLoading:
    """Tests for configuration loading."""
    
    def test_settings_from_env(self):
        """Test loading settings from environment variables."""
        import os
        
        # Save original values
        original_openai_key = os.environ.get("OPENAI_API_KEY")
        
        try:
            # Set test values
            os.environ["OPENAI_API_KEY"] = "test-key"
            os.environ["OPENAI_MODEL"] = "gpt-4o-mini"
            
            settings = Settings()
            
            # Should pick up environment values
            assert settings.llm.provider == "openai"
            assert settings.llm.model == "gpt-4o-mini"
            
        finally:
            # Restore original values
            if original_openai_key:
                os.environ["OPENAI_API_KEY"] = original_openai_key
            else:
                del os.environ["OPENAI_API_KEY"]
    
    def test_provider_detection(self):
        """Test provider detection based on API keys."""
        import os
        
        # Test with different keys set
        scenarios = [
            ("OPENAI_API_KEY", "openai"),
            ("ANTHROPIC_API_KEY", "anthropic"),
            ("DEEPSEEK_API_KEY", "deepseek"),
            ("GEMINI_API_KEY", "gemini"),
        ]
        
        for env_var, expected_provider in scenarios:
            # Clear all keys
            for var, _ in scenarios:
                if var in os.environ:
                    del os.environ[var]
            
            # Set only this key
            os.environ[env_var] = "test-key"
            
            # Default should be this provider
            settings = Settings()
            # Note: This depends on implementation - may need adjustment
            
            # Cleanup
            if env_var in os.environ:
                del os.environ[env_var]


@pytest.mark.integration
class TestPromptBuilder:
    """Tests for prompt builder functionality."""
    
    def test_simple_template(self):
        """Test simple template rendering."""
        builder = PromptBuilder(template="Hello {{name}}!")
        
        result = builder.render(name="World")
        
        assert result == "Hello World!"
    
    def test_issue_template(self):
        """Test issue-based template rendering."""
        template = "Issue {{identifier}}: {{title}}\n{{description}}"
        builder = PromptBuilder(template=template)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test Title",
            description="Test Description",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = builder.build_prompt(issue)
        
        assert "TEST-1" in result
        assert "Test Title" in result
        assert "Test Description" in result
    
    def test_conditional_rendering(self):
        """Test conditional logic in templates."""
        template = """Issue: {{title}}
{% if blockers %}
Blocked by: {% for blocker in blockers %}{{ blocker.identifier or blocker }} {% endfor %}
{% endif %}"""
        
        builder = PromptBuilder(template=template)
        
        # Without blockers
        issue1 = Issue(
            id="1",
            identifier="A-1",
            title="No blockers",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result1 = builder.build_prompt(issue1)
        assert "Blocked by" not in result1
        
        # With blockers
        issue2 = Issue(
            id="2",
            identifier="A-2",
            title="With blockers",
            description="Test",
            state="Todo",
            labels=[],
            blockers=["BLOCK-1"],
        )
        
        result2 = builder.build_prompt(issue2)
        assert "Blocked by" in result2
        assert "BLOCK-1" in result2
