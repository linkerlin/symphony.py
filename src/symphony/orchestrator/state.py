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
class ClaimedEntry:
    """已被认领但未运行的问题条目。"""

    issue_id: str
    identifier: str
    claimed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RunningEntry:
    """当前运行中问题的条目。"""

    issue: Issue
    session_state: SessionState
    task: asyncio.Task | None = None
    worker_host: str | None = None
    workspace_path: str | None = None
    retry_attempt: int | None = None
    started_at: datetime | None = None

    def __post_init__(self):
        """初始化后设置默认值。"""
        if self.started_at is None:
            self.started_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典以进行序列化。"""
        return {
            "issue": self.issue.to_prompt_dict(),
            "session": self.session_state.to_dict(),
            "worker_host": self.worker_host,
            "workspace_path": str(self.workspace_path) if self.workspace_path else None,
            "retry_attempt": self.retry_attempt,
            "started_at": self.started_at.isoformat() if self.started_at else None,
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

    def __init__(
        self,
        issue_id: str,
        identifier: str,
        attempt: int,
        scheduled_at: datetime,
        due_at: datetime | None = None,
        delay_seconds: int = 0,
        error: str | None = None,
        worker_host: str | None = None,
        workspace_path: str | None = None,
        timer_handle: asyncio.TimerHandle | None = None,
    ):
        """初始化重试条目。

        参数:
            issue_id: 问题 ID
            identifier: 问题标识符
            attempt: 尝试次数
            scheduled_at: 调度时间
            due_at: 到期时间（可选，会根据 delay_seconds 计算）
            delay_seconds: 延迟秒数（用于计算 due_at）
            error: 错误信息
            worker_host: 工作节点主机
            workspace_path: 工作空间路径
            timer_handle: 定时器句柄
        """
        self.issue_id = issue_id
        self.identifier = identifier
        self.attempt = attempt
        self.scheduled_at = scheduled_at
        self.error = error
        self.worker_host = worker_host
        self.workspace_path = workspace_path
        self.timer_handle = timer_handle
        
        # 计算到期时间
        if due_at is not None:
            self.due_at = due_at
        else:
            self.due_at = scheduled_at + timedelta(seconds=delay_seconds)

    @property
    def due_in_seconds(self) -> float:
        """获取距离重试到期的秒数。"""
        now = datetime.utcnow()
        if self.due_at <= now:
            return 0.0
        return (self.due_at - now).total_seconds()

    def is_due(self) -> bool:
        """检查重试是否到期。"""
        return datetime.utcnow() >= self.due_at

    @staticmethod
    def calculate_backoff(attempt: int, base_delay: int = 5, max_delay: int = 300) -> int:
        """计算指数退避延迟。

        参数:
            attempt: 尝试次数（从 1 开始）
            base_delay: 基础延迟秒数
            max_delay: 最大延迟秒数

        返回:
            延迟秒数
        """
        import math
        delay = base_delay * (2 ** (attempt - 1))
        return min(delay, max_delay)

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
    claimed: dict[str, ClaimedEntry] = field(default_factory=dict)
    retry_attempts: dict[str, RetryEntry] = field(default_factory=dict)
    completed: dict[str, dict[str, Any]] = field(default_factory=dict)

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

    def claim(self, issue: Issue) -> bool:
        """认领一个问题。

        参数:
            issue: 要认领的问题

        返回:
            如果成功认领则返回 True，如果已被认领则返回 False
        """
        if issue.id in self.claimed or issue.id in self.running:
            return False
        self.claimed[issue.id] = ClaimedEntry(
            issue_id=issue.id,
            identifier=issue.identifier,
        )
        return True

    def start(self, issue: Issue, session_state: SessionState) -> bool:
        """开始运行一个问题。

        参数:
            issue: 要开始的问题
            session_state: 会话状态

        返回:
            如果成功开始则返回 True，如果已达到最大并发数则返回 False
        """
        if self.is_at_capacity:
            return False
        if issue.id not in self.claimed:
            return False
        
        # 从 claimed 移到 running
        self.claimed.pop(issue.id, None)
        self.running[issue.id] = RunningEntry(
            issue=issue,
            session_state=session_state,
        )
        return True

    def complete(self, issue: Issue, success: bool = True) -> bool:
        """完成一个问题。

        参数:
            issue: 要完成的问题
            success: 是否成功完成

        返回:
            如果成功完成则返回 True
        """
        if issue.id not in self.running:
            return False
        
        entry = self.running.pop(issue.id)
        self.completed[issue.id] = {
            "issue_id": issue.id,
            "identifier": issue.identifier,
            "success": success,
            "completed_at": datetime.utcnow().isoformat(),
        }
        return True

    def schedule_retry(
        self,
        issue: Issue,
        attempt: int,
        delay_seconds: int = 0,
        error: str | None = None,
    ) -> None:
        """安排一个问题重试。

        参数:
            issue: 要重试的问题
            attempt: 尝试次数
            delay_seconds: 延迟秒数
            error: 错误信息
        """
        scheduled_at = datetime.utcnow()
        self.retry_attempts[issue.id] = RetryEntry(
            issue_id=issue.id,
            identifier=issue.identifier,
            attempt=attempt,
            scheduled_at=scheduled_at,
            delay_seconds=delay_seconds,
            error=error,
        )

    def get_ready_retries(self) -> list[RetryEntry]:
        """获取所有已到期可重试的条目。

        返回:
            到期的重试条目列表
        """
        now = datetime.utcnow()
        return [
            entry for entry in self.retry_attempts.values()
            if entry.due_at <= now
        ]

    def release(self, issue: Issue) -> None:
        """释放一个已认领的问题。

        参数:
            issue: 要释放的问题
        """
        self.claimed.pop(issue.id, None)

    def get_summary(self) -> dict[str, Any]:
        """获取状态摘要。

        返回:
            包含各种状态计数的字典
        """
        return {
            "claimed": len(self.claimed),
            "running": len(self.running),
            "retrying": len(self.retry_attempts),
            "completed": len(self.completed),
            "available_slots": self.available_slots,
        }

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
