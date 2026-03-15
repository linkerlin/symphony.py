"""Symphony 会话状态模型。

提供用于跟踪智能体会话状态和指标的数据模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class SessionStatus(Enum):
    """智能体会话的状态。"""

    PREPARING = auto()
    BUILDING_PROMPT = auto()
    LAUNCHING = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    TIMED_OUT = auto()
    STALLED = auto()
    CANCELLED = auto()


@dataclass
class LLMUsage:
    """LLM 令牌使用指标。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage: dict[str, int]) -> None:
        """添加响应中的使用情况。"""
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)

    def to_dict(self) -> dict[str, int]:
        """转换为字典。"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMTotals:
    """聚合的 LLM 使用和运行时间指标。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    seconds_running: float = 0.0

    def add_usage(self, prompt: int, completion: int) -> None:
        """将令牌数添加到总计。"""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion

    def add_runtime(self, seconds: float) -> None:
        """将运行秒数添加到总计。"""
        self.seconds_running += seconds

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "seconds_running": self.seconds_running,
        }


@dataclass
class SessionState:
    """单个智能体会话的状态。

    跟踪智能体执行会话的生命周期和指标。
    """

    # 标识符
    issue_id: str
    issue_identifier: str
    session_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None

    # 状态
    status: SessionStatus = SessionStatus.PREPARING
    error: str | None = None

    # 运行时信息
    workspace_path: str | None = None
    worker_host: str | None = None
    llm_model: str | None = None

    # 时间戳
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None

    # 令牌跟踪（与 LLM 提供商无关）
    llm_usage: LLMUsage = field(default_factory=LLMUsage)
    turn_count: int = 0

    # 事件跟踪
    last_event: str | None = None
    last_message: str | None = None

    def update_activity(self) -> None:
        """更新最后活动时间戳。"""
        self.last_activity_at = datetime.utcnow()

    def add_usage(self, usage: dict[str, int]) -> None:
        """将 LLM 使用情况添加到会话。"""
        self.llm_usage.add(usage)
        self.update_activity()

    def increment_turn(self) -> None:
        """增加轮次计数器。"""
        self.turn_count += 1
        self.update_activity()

    def set_event(self, event: str, message: str | None = None) -> None:
        """设置最后事件和可选消息。"""
        self.last_event = event
        if message:
            self.last_message = message
        self.update_activity()

    def complete(self, status: SessionStatus = SessionStatus.COMPLETED) -> None:
        """将会话标记为以给定状态完成。"""
        self.status = status
        self.ended_at = datetime.utcnow()

    def get_runtime_seconds(self) -> float:
        """获取当前运行时间（秒）。"""
        end = self.ended_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def start(self) -> None:
        """启动会话，设置状态为 RUNNING 并记录开始时间。"""
        self.status = SessionStatus.RUNNING
        self.started_at = datetime.utcnow()
        self.update_activity()

    def is_active(self) -> bool:
        """检查会话是否仍处于活动状态。"""
        return self.status in {
            SessionStatus.RUNNING,
            SessionStatus.BUILDING_PROMPT,
            SessionStatus.LAUNCHING,
            SessionStatus.INITIALIZING,
        }

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "issue_id": self.issue_id,
            "issue_identifier": self.issue_identifier,
            "session_id": self.session_id,
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "status": self.status.name,
            "error": self.error,
            "workspace_path": self.workspace_path,
            "worker_host": self.worker_host,
            "llm_model": self.llm_model,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "llm_usage": self.llm_usage.to_dict(),
            "turn_count": self.turn_count,
            "last_event": self.last_event,
            "last_message": self.last_message,
            "runtime_seconds": self.get_runtime_seconds(),
        }
