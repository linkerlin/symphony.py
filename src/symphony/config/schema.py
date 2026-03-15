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


def get_env_or_default(env_var: str, default: str | None = None) -> str | None:
    """Get value from environment variable or return default."""
    return os.environ.get(env_var, default)


class LLMConfig(BaseModel):
    """Configuration for LLM provider.
    
    Supports multiple providers: openai, anthropic, deepseek, gemini, etc.
    Configuration can come from environment variables or WORKFLOW.md.
    
    Priority for API configuration:
    1. Explicit config in WORKFLOW.md
    2. OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL (if provider is openai)
    3. Provider-specific env vars (ANTHROPIC_API_KEY, etc.)
    4. Default values
    """

    provider: Literal["openai", "anthropic", "deepseek", "gemini", "azure"] = Field(
        default="openai",
        description="LLM provider name",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for the LLM provider",
    )
    base_url: str | None = Field(
        default=None,
        description="Base URL for the API (for custom endpoints)",
    )
    model: str = Field(
        default="gpt-4",
        description="Model name to use",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="Maximum tokens per response",
    )
    timeout: int = Field(
        default=120,
        ge=1,
        description="Request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retries for failed requests",
    )

    @model_validator(mode="after")
    def resolve_from_env(self) -> "LLMConfig":
        """Resolve API key, base_url, and model from environment variables.
        
        Priority:
        1. Explicitly set values (not None)
        2. OPENAI_* environment variables (if provider is openai)
        3. Provider-specific environment variables
        """
        # If provider is openai and values not set, try OPENAI_* env vars
        if self.provider == "openai":
            if self.api_key is None:
                self.api_key = get_env_or_default("OPENAI_API_KEY")
            if self.base_url is None:
                self.base_url = get_env_or_default("OPENAI_BASE_URL")
            if self.model == "gpt-4":  # Only override if using default
                env_model = get_env_or_default("OPENAI_MODEL")
                if env_model:
                    self.model = env_model
        
        # Provider-specific env vars as fallback
        provider_env_map = {
            "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"),
            "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
            "gemini": ("GEMINI_API_KEY", None, "GEMINI_MODEL"),
            "azure": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_MODEL"),
        }
        
        if self.provider in provider_env_map:
            key_var, url_var, model_var = provider_env_map[self.provider]
            
            if self.api_key is None:
                self.api_key = get_env_or_default(key_var)
            if self.base_url is None and url_var:
                self.base_url = get_env_or_default(url_var)
            if model_var:
                env_model = get_env_or_default(model_var)
                if env_model and self.model == "gpt-4":
                    self.model = env_model
        
        return self

    def get_client_config(self) -> dict[str, Any]:
        """Get configuration dict for creating LLM client."""
        config = {
            "provider": self.provider,
            "api_key": self.api_key,
            "model": self.model,
            "temperature": self.temperature,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
        }
        if self.base_url:
            config["base_url"] = self.base_url
        if self.max_tokens:
            config["max_tokens"] = self.max_tokens
        return config


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
    turn_timeout_seconds: int = Field(
        default=3600,
        ge=60,
        description="Maximum seconds per agent turn",
    )
    stall_timeout_seconds: int = Field(
        default=300,
        ge=0,
        description="Stall detection timeout in seconds (0 to disable)",
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
    loaded from WORKFLOW.md, environment variables, or .env file.
    """

    # LLM configuration (replaces old codex config)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    
    # Other configurations
    tracker: TrackerConfig = Field(default_factory=TrackerConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @model_validator(mode="after")
    def validate_tracker_config(self) -> "SymphonyConfig":
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

    def get_llm_client_config(self) -> dict[str, Any]:
        """Get LLM client configuration."""
        return self.llm.get_client_config()
