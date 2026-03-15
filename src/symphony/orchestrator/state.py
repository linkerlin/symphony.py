"""State management for the Orchestrator.

Defines data structures for tracking running and retrying issues.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from symphony.models.issue import Issue
from symphony.models.session import CodexTotals, SessionState


@dataclass
class RunningEntry:
    """Entry for a currently running issue."""

    task: asyncio.Task
    issue: Issue
    session_state: SessionState
    worker_host: str | None = None
    workspace_path: str | None = None
    retry_attempt: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "issue": self.issue.to_prompt_dict(),
            "session": self.session_state.to_dict(),
            "worker_host": self.worker_host,
            "workspace_path": str(self.workspace_path) if self.workspace_path else None,
            "retry_attempt": self.retry_attempt,
        }


@dataclass
class RetryEntry:
    """Entry for an issue scheduled for retry."""

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
        """Get seconds until retry is due."""
        now = datetime.utcnow()
        if self.due_at <= now:
            return 0.0
        return (self.due_at - now).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
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
    """Complete state of the orchestrator.

    This class holds all mutable state that the orchestrator manages.
    """

    # Configuration (can be updated dynamically)
    poll_interval_ms: int = 30000
    max_concurrent_agents: int = 10
    max_retry_backoff_ms: int = 300000

    # Running and retrying issues
    running: dict[str, RunningEntry] = field(default_factory=dict)
    claimed: set[str] = field(default_factory=set)
    retry_attempts: dict[str, RetryEntry] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)

    # Metrics
    codex_totals: CodexTotals = field(default_factory=CodexTotals)
    codex_rate_limits: dict[str, Any] | None = None

    # Internal
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def available_slots(self) -> int:
        """Get number of available agent slots."""
        return max(0, self.max_concurrent_agents - len(self.running))

    @property
    def is_at_capacity(self) -> bool:
        """Check if at maximum concurrency."""
        return len(self.running) >= self.max_concurrent_agents

    def get_running_issue_ids(self) -> set[str]:
        """Get set of currently running issue IDs."""
        return set(self.running.keys())

    def is_issue_claimed(self, issue_id: str) -> bool:
        """Check if an issue is claimed (running or retrying)."""
        return issue_id in self.claimed

    def is_issue_running(self, issue_id: str) -> bool:
        """Check if an issue is currently running."""
        return issue_id in self.running

    def get_retry_entry(self, issue_id: str) -> RetryEntry | None:
        """Get retry entry for an issue if it exists."""
        return self.retry_attempts.get(issue_id)

    def get_running_count_for_state(self, state_name: str) -> int:
        """Count running issues in a specific state."""
        normalized = state_name.lower()
        return sum(
            1
            for entry in self.running.values()
            if entry.issue.get_normalized_state() == normalized
        )

    def to_snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current state."""
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
            "codex_totals": self.codex_totals.to_dict(),
            "codex_rate_limits": self.codex_rate_limits,
        }
