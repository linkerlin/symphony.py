"""Data models for Linear Issues.

Provides Pydantic models for normalized issue representation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class BlockerRef(BaseModel):
    """Reference to a blocking issue.

    Attributes:
        id: Linear issue ID
        identifier: Human-readable issue identifier (e.g., "ABC-123")
        state: Current state of the blocking issue
    """

    id: str | None = None
    identifier: str | None = None
    state: str | None = None

    def is_terminal(self, terminal_states: set[str]) -> bool:
        """Check if this blocker is in a terminal state.

        Args:
            terminal_states: Set of state names considered terminal

        Returns:
            True if blocker is in a terminal state
        """
        if self.state is None:
            return False
        return self.state.lower() in {s.lower() for s in terminal_states}


class Issue(BaseModel):
    """Normalized Linear issue representation.

    This model represents a Linear issue in a normalized form suitable
    for orchestration, prompt rendering, and observability.

    Attributes:
        id: Stable tracker-internal ID
        identifier: Human-readable ticket key (e.g., "ABC-123")
        title: Issue title
        description: Issue description (may be None)
        priority: Priority number (lower is higher priority, 1-4 typical)
        state: Current tracker state name
        branch_name: Tracker-provided branch metadata
        url: Issue URL
        assignee_id: ID of assigned user
        labels: List of label names (normalized to lowercase)
        blocked_by: List of blocking issue references
        assigned_to_worker: Whether this issue is assigned to current worker
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: str
    identifier: str
    title: str
    description: str | None = None
    priority: int | None = None
    state: str
    branch_name: str | None = None
    url: str | None = None
    assignee_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    blocked_by: list[BlockerRef] = Field(default_factory=list)
    assigned_to_worker: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {
        "frozen": False,  # Allow mutation for state updates
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_labels(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize labels to lowercase."""
        if isinstance(data, dict) and "labels" in data:
            labels = data["labels"]
            if isinstance(labels, list):
                data["labels"] = [
                    label.lower() if isinstance(label, str) else str(label).lower()
                    for label in labels
                ]
        return data

    def get_normalized_state(self) -> str:
        """Get lowercase normalized state name."""
        return self.state.lower()

    def is_in_state(self, states: list[str] | set[str]) -> bool:
        """Check if issue is in any of the given states.

        Args:
            states: List or set of state names to check

        Returns:
            True if issue state matches any of the given states
        """
        normalized = self.get_normalized_state()
        return any(normalized == s.lower() for s in states)

    def is_blocked(self, terminal_states: set[str]) -> bool:
        """Check if this issue is blocked by non-terminal issues.

        Only applies to issues in "Todo" state. Issues in other states
        are not considered blocked regardless of their blockers.

        Args:
            terminal_states: Set of state names considered terminal

        Returns:
            True if issue has non-terminal blockers
        """
        # Only Todo issues can be blocked
        if self.get_normalized_state() != "todo":
            return False

        # Check for any non-terminal blocker
        for blocker in self.blocked_by:
            if not blocker.is_terminal(terminal_states):
                return True

        return False

    def is_eligible_for_dispatch(
        self,
        active_states: set[str],
        terminal_states: set[str],
    ) -> bool:
        """Check if this issue is eligible for dispatch.

        An issue is eligible if:
        - It has all required fields (id, identifier, title, state)
        - Its state is in active_states and not in terminal_states
        - It's not blocked by non-terminal issues (if in Todo state)

        Args:
            active_states: Set of active state names
            terminal_states: Set of terminal state names

        Returns:
            True if issue can be dispatched
        """
        # Check required fields
        if not all([self.id, self.identifier, self.title, self.state]):
            return False

        normalized_state = self.get_normalized_state()

        # Check state is active
        if normalized_state not in {s.lower() for s in active_states}:
            return False

        # Check not terminal
        if normalized_state in {s.lower() for s in terminal_states}:
            return False

        # Check not blocked
        if self.is_blocked(terminal_states):
            return False

        return True

    def get_context_string(self) -> str:
        """Get a short context string for logging.

        Returns:
            String like "issue_id=abc issue_identifier=ABC-123"
        """
        return f"issue_id={self.id} issue_identifier={self.identifier}"

    def to_prompt_dict(self) -> dict[str, Any]:
        """Convert to dictionary suitable for prompt template rendering.

        Returns:
            Dictionary with all issue fields as strings
        """
        return {
            "id": self.id,
            "identifier": self.identifier,
            "title": self.title,
            "description": self.description or "",
            "priority": self.priority,
            "state": self.state,
            "branch_name": self.branch_name or "",
            "url": self.url or "",
            "labels": self.labels,
            "blocked_by": [
                {
                    "id": b.id or "",
                    "identifier": b.identifier or "",
                    "state": b.state or "",
                }
                for b in self.blocked_by
            ],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        """String representation of Issue."""
        return f"Issue({self.get_context_string()} state={self.state})"

    def __hash__(self) -> int:
        """Hash based on issue ID."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Equality based on issue ID."""
        if not isinstance(other, Issue):
            return NotImplemented
        return self.id == other.id
