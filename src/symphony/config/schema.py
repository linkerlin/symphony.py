"""Pydantic models for Symphony configuration.

Defines the configuration schema for all Symphony components.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def default_workspace_root() -> str:
    """Return default workspace root path."""
    return str(Path(tempfile.gettempdir()) / "symphony_workspaces")


class TrackerConfig(BaseModel):
    """Configuration for issue tracker (Linear)."""

    kind: Literal["linear", "memory"] = Field(
        default="linear",
        description="Tracker type: linear or memory (for testing)",
    )
    endpoint: str = Field(
        default="https://api.linear.app/graphql",
        description="Linear GraphQL API endpoint",
    )
    api_key: str | None = Field(
        default=None,
        description="Linear API key or $ENV_VAR reference",
    )
    project_slug: str | None = Field(
        default=None,
        description="Linear project slug identifier",
    )
    assignee: str | None = Field(
        default=None,
        description="Filter by assignee (use 'me' for current user)",
    )
    active_states: list[str] = Field(
        default=["Todo", "In Progress"],
        description="Issue states considered active",
    )
    terminal_states: list[str] = Field(
        default=["Closed", "Cancelled", "Canceled", "Duplicate", "Done"],
        description="Issue states considered terminal",
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def resolve_api_key(cls, v: str | None) -> str | None:
        """Resolve API key from environment variable if prefixed with $."""
        if isinstance(v, str) and v.startswith("$"):
            env_var = v[1:]
            if env_var and all(c.isalnum() or c == "_" for c in env_var):
                return os.environ.get(env_var) or None
        return v


class PollingConfig(BaseModel):
    """Configuration for polling behavior."""

    interval_ms: int = Field(
        default=30000,
        ge=1000,
        description="Poll interval in milliseconds",
    )


class WorkspaceConfig(BaseModel):
    """Configuration for workspace management."""

    root: str = Field(
        default_factory=default_workspace_root,
        description="Root directory for workspaces",
    )

    @field_validator("root", mode="before")
    @classmethod
    def resolve_workspace_root(cls, v: str | None) -> str:
        """Resolve workspace root, expanding env vars and ~."""
        if v is None:
            return default_workspace_root()

        # Resolve environment variables
        if v.startswith("$"):
            env_var = v[1:]
            if env_var and all(c.isalnum() or c == "_" for c in env_var):
                v = os.environ.get(env_var) or default_workspace_root()

        # Expand ~ to home directory
        v = os.path.expanduser(v)
        return v


class HooksConfig(BaseModel):
    """Configuration for workspace lifecycle hooks."""

    after_create: str | None = Field(
        default=None,
        description="Shell script to run after workspace creation",
    )
    before_run: str | None = Field(
        default=None,
        description="Shell script to run before agent execution",
    )
    after_run: str | None = Field(
        default=None,
        description="Shell script to run after agent execution",
    )
    before_remove: str | None = Field(
        default=None,
        description="Shell script to run before workspace removal",
    )
    timeout_ms: int = Field(
        default=60000,
        ge=1000,
        description="Hook execution timeout in milliseconds",
    )


class AgentConfig(BaseModel):
    """Configuration for agent behavior."""

    max_concurrent_agents: int = Field(
        default=10,
        ge=1,
        description="Maximum concurrent agent executions",
    )
    max_turns: int = Field(
        default=20,
        ge=1,
        description="Maximum turns per agent session",
    )
    max_retry_backoff_ms: int = Field(
        default=300000,
        ge=1000,
        description="Maximum retry backoff in milliseconds",
    )
    max_concurrent_agents_by_state: dict[str, int] = Field(
        default_factory=dict,
        description="Per-state concurrency limits",
    )


class CodexConfig(BaseModel):
    """Configuration for Codex/coding agent integration."""

    command: str = Field(
        default="codex app-server",
        description="Command to start coding agent app-server",
    )
    approval_policy: str | dict[str, Any] = Field(
        default="never",
        description="Approval policy: never, on-failure, on-request, or dict",
    )
    thread_sandbox: str = Field(
        default="workspace-write",
        description="Sandbox mode: read-only, workspace-write, danger-full-access",
    )
    turn_sandbox_policy: dict[str, Any] | None = Field(
        default=None,
        description="Per-turn sandbox policy configuration",
    )
    turn_timeout_ms: int = Field(
        default=3600000,
        ge=1000,
        description="Turn timeout in milliseconds",
    )
    read_timeout_ms: int = Field(
        default=5000,
        ge=1000,
        description="Read timeout for app-server responses",
    )
    stall_timeout_ms: int = Field(
        default=300000,
        ge=0,
        description="Stall detection timeout (0 to disable)",
    )


class WorkerConfig(BaseModel):
    """Configuration for remote workers via SSH."""

    ssh_hosts: list[str] = Field(
        default_factory=list,
        description="List of SSH host strings for remote execution",
    )
    max_concurrent_agents_per_host: int | None = Field(
        default=None,
        ge=1,
        description="Maximum agents per SSH host",
    )


class ServerConfig(BaseModel):
    """Configuration for HTTP API server."""

    port: int | None = Field(
        default=None,
        ge=0,
        description="HTTP server port (None to disable)",
    )
    host: str = Field(
        default="127.0.0.1",
        description="HTTP server bind address",
    )


class ObservabilityConfig(BaseModel):
    """Configuration for observability features."""

    dashboard_enabled: bool = Field(
        default=True,
        description="Enable terminal dashboard",
    )
    refresh_ms: int = Field(
        default=1000,
        ge=100,
        description="Dashboard refresh interval in milliseconds",
    )


class SymphonyConfig(BaseModel):
    """Root configuration for Symphony.

    This is the main configuration class that holds all settings
    loaded from WORKFLOW.md or environment variables.
    """

    tracker: TrackerConfig = Field(default_factory=TrackerConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    codex: CodexConfig = Field(default_factory=CodexConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @model_validator(mode="after")
    def validate_tracker_config(self) -> SymphonyConfig:
        """Validate tracker-specific requirements."""
        if self.tracker.kind == "linear":
            if not self.tracker.api_key:
                # Allow missing api_key during initial load, will be validated later
                pass
            if not self.tracker.project_slug:
                # Allow missing project_slug during initial load
                pass
        return self

    def get_effective_poll_interval_ms(self) -> int:
        """Get effective poll interval."""
        return self.polling.interval_ms

    def get_effective_max_concurrent_agents(self) -> int:
        """Get effective max concurrent agents."""
        return self.agent.max_concurrent_agents

    def get_max_concurrent_for_state(self, state_name: str) -> int:
        """Get max concurrent agents for a specific state."""
        normalized = state_name.lower()
        return self.agent.max_concurrent_agents_by_state.get(
            normalized, self.agent.max_concurrent_agents
        )

    def is_state_active(self, state_name: str) -> bool:
        """Check if a state is considered active."""
        normalized = state_name.lower()
        return any(s.lower() == normalized for s in self.tracker.active_states)

    def is_state_terminal(self, state_name: str) -> bool:
        """Check if a state is considered terminal."""
        normalized = state_name.lower()
        return any(s.lower() == normalized for s in self.tracker.terminal_states)
