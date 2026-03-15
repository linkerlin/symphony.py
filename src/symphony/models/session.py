"""Session state models for Symphony.

Provides data models for tracking agent session state and metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class SessionStatus(Enum):
    """Status of an agent session."""

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
class CodexTotals:
    """Aggregate token and runtime metrics.

    Tracks cumulative metrics across all completed and running sessions.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    seconds_running: float = 0.0

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Add token counts to totals."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens

    def add_runtime(self, seconds: float) -> None:
        """Add runtime seconds to totals."""
        self.seconds_running += seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "seconds_running": self.seconds_running,
        }


@dataclass
class SessionState:
    """State of a single agent session.

    Tracks the lifecycle and metrics of an agent execution session.
    """

    # Identifiers
    issue_id: str
    issue_identifier: str
    session_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None

    # Status
    status: SessionStatus = SessionStatus.PREPARING
    error: str | None = None

    # Runtime info
    workspace_path: str | None = None
    worker_host: str | None = None
    codex_app_server_pid: str | None = None

    # Timestamps
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None

    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # Event tracking
    last_event: str | None = None
    last_message: str | None = None
    turn_count: int = 0

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity_at = datetime.utcnow()

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Add token counts to session."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.update_activity()

    def increment_turn(self) -> None:
        """Increment turn counter."""
        self.turn_count += 1
        self.update_activity()

    def set_event(self, event: str, message: str | None = None) -> None:
        """Set last event and optional message."""
        self.last_event = event
        if message:
            self.last_message = message
        self.update_activity()

    def complete(self, status: SessionStatus = SessionStatus.COMPLETED) -> None:
        """Mark session as completed with given status."""
        self.status = status
        self.ended_at = datetime.utcnow()

    def get_runtime_seconds(self) -> float:
        """Get current runtime in seconds."""
        end = self.ended_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def is_active(self) -> bool:
        """Check if session is still active."""
        return self.status in {
            SessionStatus.PREPARING,
            SessionStatus.BUILDING_PROMPT,
            SessionStatus.LAUNCHING,
            SessionStatus.INITIALIZING,
            SessionStatus.RUNNING,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
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
            "codex_app_server_pid": self.codex_app_server_pid,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "last_event": self.last_event,
            "last_message": self.last_message,
            "turn_count": self.turn_count,
            "runtime_seconds": self.get_runtime_seconds(),
        }
