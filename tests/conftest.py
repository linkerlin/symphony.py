"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "tracker": {
            "kind": "memory",
            "active_states": ["Todo", "In Progress"],
            "terminal_states": ["Done", "Closed"],
        },
        "polling": {"interval_ms": 1000},
        "workspace": {"root": "/tmp/test-workspaces"},
        "agent": {"max_concurrent_agents": 2},
    }
