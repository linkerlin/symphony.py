"""Symphony 配置的 Pydantic 模型。

定义所有 Symphony 组件的配置模式。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def default_workspace_root() -> str:
    """返回默认工作区根路径。"""
    return str(Path(tempfile.gettempdir()) / "symphony_workspaces")


def get_env_or_default(env_var: str, default: str | None = None) -> str | None:
    """从环境变量获取值或返回默认值。"""
    return os.environ.get(env_var, default)


class LLMConfig(BaseModel):
    """LLM 提供商配置。
    
    支持多个提供商：openai、anthropic、deepseek、gemini 等。
    配置可以来自环境变量或 WORKFLOW.md。
    
    API 配置优先级：
    1. WORKFLOW.md 中的显式配置
    2. OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL（如果提供商是 openai）
    3. 提供商特定的环境变量（ANTHROPIC_API_KEY 等）
    4. 默认值
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
        """从环境变量解析 API key、base_url 和 model。
        
        优先级：
        1. 显式设置的值（非 None）
        2. OPENAI_* 环境变量（如果提供商是 openai）
        3. 提供商特定的环境变量
        """
        # 如果提供商是 openai 且值未设置，尝试 OPENAI_* 环境变量
        if self.provider == "openai":
            if self.api_key is None:
                self.api_key = get_env_or_default("OPENAI_API_KEY")
            if self.base_url is None:
                self.base_url = get_env_or_default("OPENAI_BASE_URL")
            if self.model == "gpt-4":  # 仅在使用默认值时覆盖
                env_model = get_env_or_default("OPENAI_MODEL")
                if env_model:
                    self.model = env_model
        
        # 提供商特定的环境变量作为后备
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
        """获取用于创建 LLM 客户端的配置字典。"""
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
    """问题追踪器（Linear）配置。"""

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
        """如果 API key 以 $ 开头，则从环境变量解析。"""
        if isinstance(v, str) and v.startswith("$"):
            env_var = v[1:]
            if env_var and all(c.isalnum() or c == "_" for c in env_var):
                return os.environ.get(env_var) or None
        return v


class PollingConfig(BaseModel):
    """轮询行为配置。"""

    interval_ms: int = Field(
        default=30000,
        ge=1000,
        description="Poll interval in milliseconds",
    )


class WorkspaceConfig(BaseModel):
    """工作区管理配置。"""

    root: str = Field(
        default_factory=default_workspace_root,
        description="Root directory for workspaces",
    )

    @field_validator("root", mode="before")
    @classmethod
    def resolve_workspace_root(cls, v: str | None) -> str:
        """解析工作区根路径，展开环境变量和 ~。"""
        if v is None:
            return default_workspace_root()

        # 解析环境变量
        if v.startswith("$"):
            env_var = v[1:]
            if env_var and all(c.isalnum() or c == "_" for c in env_var):
                v = os.environ.get(env_var) or default_workspace_root()

        # 将 ~ 展开为主目录
        v = os.path.expanduser(v)
        return v


class HooksConfig(BaseModel):
    """工作区生命周期钩子配置。"""

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
    """代理行为配置。"""

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
    """HTTP API 服务器配置。"""

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
    """可观测性功能配置。"""

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
    """Symphony 根配置。

    这是主配置类，保存从 WORKFLOW.md、环境变量或 .env 文件加载的所有设置。
    """

    # LLM 配置（替代旧的 codex 配置）
    llm: LLMConfig = Field(default_factory=LLMConfig)
    
    # 其他配置
    tracker: TrackerConfig = Field(default_factory=TrackerConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @model_validator(mode="after")
    def validate_tracker_config(self) -> "SymphonyConfig":
        """验证 tracker 特定要求。"""
        if self.tracker.kind == "linear":
            if not self.tracker.api_key:
                # 在初始加载期间允许缺少 api_key，稍后将进行验证
                pass
            if not self.tracker.project_slug:
                # 在初始加载期间允许缺少 project_slug
                pass
        return self

    def get_effective_poll_interval_ms(self) -> int:
        """获取有效的轮询间隔。"""
        return self.polling.interval_ms

    def get_effective_max_concurrent_agents(self) -> int:
        """获取有效的最大并发代理数。"""
        return self.agent.max_concurrent_agents

    def get_max_concurrent_for_state(self, state_name: str) -> int:
        """获取特定状态的最大并发代理数。"""
        normalized = state_name.lower()
        return self.agent.max_concurrent_agents_by_state.get(
            normalized, self.agent.max_concurrent_agents
        )

    def is_state_active(self, state_name: str) -> bool:
        """检查状态是否被认为是活动的。"""
        normalized = state_name.lower()
        return any(s.lower() == normalized for s in self.tracker.active_states)

    def is_state_terminal(self, state_name: str) -> bool:
        """检查状态是否被认为是终止的。"""
        normalized = state_name.lower()
        return any(s.lower() == normalized for s in self.tracker.terminal_states)

    def get_llm_client_config(self) -> dict[str, Any]:
        """获取 LLM 客户端配置。"""
        return self.llm.get_client_config()
