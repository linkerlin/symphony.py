"""Pytest configuration and fixtures for Symphony tests.

Uses real API connections with fast/cheap models for integration testing.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

from symphony.llm.client import LLMClient
from symphony.config.schema import (
    LLMConfig,
    AgentConfig,
    HooksConfig,
    SymphonyConfig as Settings,
    TrackerConfig,
    WorkspaceConfig,
)
from symphony.workspace.manager import WorkspaceManager


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def _detect_provider() -> str:
    """Detect which LLM provider to use based on environment."""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    elif os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    elif os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    else:
        pytest.skip("No LLM API key found in environment. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.")


def _get_test_model(provider: str) -> str:
    """Get fast/cheap test model for provider."""
    models = {
        "openai": "gpt-4o-mini",  # Fast and cheap
        "anthropic": "claude-3-haiku-20240307",  # Fastest Claude
        "deepseek": "deepseek-chat",
        "gemini": "gemini-1.5-flash",  # Fast Gemini
        "azure": os.environ.get("AZURE_MODEL", "gpt-4o-mini"),
    }
    return models.get(provider, "gpt-4o-mini")


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings using real but fast/cheap models."""
    # Detect available LLM provider from environment
    provider = _detect_provider()
    
    return Settings(
        llm=LLMConfig(
            provider=provider,  # type: ignore
            model=_get_test_model(provider),
            temperature=0.1,  # Low temperature for deterministic tests
            max_tokens=500,   # Limit tokens for speed
        ),
        tracker=TrackerConfig(
            kind="memory",  # Use memory tracker for tests
            project_slug="test-project",
        ),
        agent=AgentConfig(
            max_turns=5,  # Limit turns for fast tests
            include_patterns=["**/*.py", "**/*.md"],
            exclude_patterns=["**/.git/**", "**/__pycache__/**"],
        ),
        workspace=WorkspaceConfig(
            root=tempfile.gettempdir() + "/symphony-test-workspaces",
            max_concurrent_agents=2,
        ),
        hooks=HooksConfig(
            timeout_ms=5000,  # Short timeout for tests
        ),
    )


# ============================================================================
# LLM Client Fixtures
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def llm_client(test_settings: Settings) -> AsyncGenerator[LLMClient, None]:
    """Create LLM client with real API connection."""
    config = test_settings.llm
    client = LLMClient.from_config(config)
    
    yield client
    
    await client.close()


@pytest_asyncio.fixture(scope="function")
async def fast_llm_client() -> AsyncGenerator[LLMClient, None]:
    """Create LLM client specifically optimized for fast tests.
    
    Uses the cheapest/fastest available model with minimal tokens.
    """
    provider = _detect_provider()
    
    # Override with even more aggressive settings for speed
    fast_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku-20240307",
        "deepseek": "deepseek-chat",
        "gemini": "gemini-1.5-flash",
    }
    
    config = LLMConfig(
        provider=provider,  # type: ignore
        model=fast_models.get(provider, "gpt-4o-mini"),
        temperature=0.0,  # Deterministic
        max_tokens=100,   # Very limited for speed
    )
    
    client = LLMClient.from_config(config)
    yield client
    await client.close()


# ============================================================================
# Workspace Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory(prefix="symphony-test-") as tmpdir:
        workspace_path = Path(tmpdir) / "workspace"
        workspace_path.mkdir(parents=True)
        
        # Create some test files
        (workspace_path / "test.py").write_text("# Test file\nprint('hello')\n")
        (workspace_path / "README.md").write_text("# Test Project\n")
        
        yield workspace_path


@pytest_asyncio.fixture(scope="function")
async def workspace_manager(test_settings: Settings) -> AsyncGenerator[WorkspaceManager, None]:
    """Create workspace manager with test settings."""
    manager = WorkspaceManager(
        root=test_settings.workspace.root,
        hooks={},
        hook_timeout_ms=test_settings.hooks.timeout_ms,
    )
    
    yield manager
    
    # Cleanup: remove all test workspaces
    import shutil
    if Path(test_settings.workspace.root).exists():
        shutil.rmtree(test_settings.workspace.root, ignore_errors=True)


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def test_issue_data() -> dict:
    """Generate test issue data."""
    return {
        "id": f"test-issue-{uuid.uuid4().hex[:8]}",
        "identifier": f"TEST-{uuid.uuid4().int % 1000}",
        "title": "Test Issue: Add simple function",
        "description": "Create a Python function that returns the sum of two numbers.",
        "state": "Todo",
        "labels": ["test", "automated"],
        "blockers": [],
    }


@pytest.fixture(scope="function")
def simple_math_prompt() -> str:
    """Simple prompt for fast testing."""
    return """You are a helpful assistant. 

Task: Write a Python function called 'add' that takes two numbers and returns their sum.

Requirements:
1. Function should be named 'add'
2. Takes two parameters: a and b
3. Returns a + b
4. Include a docstring

Respond with just the Python code, no explanation."""


@pytest.fixture(scope="function")
def simple_tool_prompt() -> str:
    """Prompt that tests tool usage."""
    return """You have access to file tools. 

Task: Read the file 'test.py' and tell me what it contains.

Use the read_file tool to read 'test.py'."""


# ============================================================================
# Markers
# ============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "llm: marks tests that call real LLM APIs (may incur costs)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
