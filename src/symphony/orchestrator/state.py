"""编排器的状态管理。

定义用于跟踪运行中和重试中问题的数据结构。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from symphony.models.issue import Issue
from symphony.models.session import LLMTotals, SessionState


@dataclass
class RunningEntry:
    """当前运行中问题的条目。"""

    task: asyncio.Task
    issue: Issue
    session_state: SessionState
    worker_host: str | None = None
    workspace_path: str | None = None
    retry_attempt: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以进行序列化。"""
        return {
            "issue": self.issue.to_prompt_dict(),
            "session": self.session_state.to_dict(),
            "worker_host": self.worker_host,
            "workspace_path": str(self.workspace_path) if self.workspace_path else None,
            "retry_attempt": self.retry_attempt,
        }


@dataclass
class RetryEntry:
    """已安排重试的问题条目。"""

    issue_id: str
    identifier: str
    attempt: int
    scheduled_at: datetime
    due_at: datetime
    error: str | None = None
    worker_host: str | None = None
    workspace_path: str | None = None
    timer_handle: asyncio.TimerHandle | None = None

    @property
    def due_in_seconds(self) -> float:
        """获取距离重试到期的秒数。"""
        now = datetime.utcnow()
        if self.due_at <= now:
            return 0.0
        return (self.due_at - now).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以进行序列化。"""
        return {
            "issue_id": self.issue_id,
            "identifier": self.identifier,
            "attempt": self.attempt,
            "scheduled_at": self.scheduled_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "due_in_seconds": self.due_in_seconds,
            "error": self.error,
            "worker_host": self.worker_host,
        }


@dataclass
class OrchestratorState:
    """编排器的完整状态。

    此类保存编排器管理的所有可变状态。
    """

    # 配置（可动态更新）
    poll_interval_ms: int = 30000
    max_concurrent_agents: int = 10
    max_retry_backoff_ms: int = 300000

    # 运行中和重试中的问题
    running: dict[str, RunningEntry] = field(default_factory=dict)
    claimed: set[str] = field(default_factory=set)
    retry_attempts: dict[str, RetryEntry] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)

    # 指标（与 LLM 提供商无关）
    llm_totals: LLMTotals = field(default_factory=LLMTotals)
    rate_limits: dict[str, Any] | None = None

    # 内部
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def available_slots(self) -> int:
        """获取可用的智能体槽位数。"""
        return max(0, self.max_concurrent_agents - len(self.running))

    @property
    def is_at_capacity(self) -> bool:
        """检查是否已达到最大并发数。"""
        return len(self.running) >= self.max_concurrent_agents

    def get_running_issue_ids(self) -> set[str]:
        """获取当前运行中的问题 ID 集合。"""
        return set(self.running.keys())

    def is_issue_claimed(self, issue_id: str) -> bool:
        """检查问题是否已被认领（运行中或重试中）。"""
        return issue_id in self.claimed

    def is_issue_running(self, issue_id: str) -> bool:
        """检查问题是否正在运行。"""
        return issue_id in self.running

    def get_retry_entry(self, issue_id: str) -> RetryEntry | None:
        """获取问题的重试条目（如果存在）。"""
        return self.retry_attempts.get(issue_id)

    def get_running_count_for_state(self, state_name: str) -> int:
        """统计特定状态中运行的问题数。"""
        normalized = state_name.lower()
        return sum(
            1
            for entry in self.running.values()
            if entry.issue.get_normalized_state() == normalized
        )

    def to_snapshot(self) -> dict[str, Any]:
        """创建当前状态的快照。"""
        return {
            "poll_interval_ms": self.poll_interval_ms,
            "max_concurrent_agents": self.max_concurrent_agents,
            "available_slots": self.available_slots,
            "running_count": len(self.running),
            "retrying_count": len(self.retry_attempts),
            "claimed_count": len(self.claimed),
            "completed_count": len(self.completed),
            "running": [entry.to_dict() for entry in self.running.values()],
            "retrying": [entry.to_dict() for entry in self.retry_attempts.values()],
            "llm_totals": self.llm_totals.to_dict(),
            "rate_limits": self.rate_limits,
        }
