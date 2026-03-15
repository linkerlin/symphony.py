"""Base class for issue tracker adapters.

Defines the interface that all tracker implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from symphony.models.issue import Issue


class TrackerError(Exception):
    """Raised when tracker operation fails."""

    pass


class BaseTracker(ABC):
    """Abstract base class for issue trackers.

    All tracker implementations must inherit from this class
    and implement the required methods.
    """

    @abstractmethod
    async def fetch_candidate_issues(self) -> list[Issue]:
        """Fetch issues in active states that are candidates for dispatch.

        Returns:
            List of Issue objects

        Raises:
            TrackerError: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_issues_by_states(self, states: list[str]) -> list[Issue]:
        """Fetch issues in specific states.

        Args:
            states: List of state names to fetch

        Returns:
            List of Issue objects

        Raises:
            TrackerError: If fetch fails
        """
        pass

    @abstractmethod
    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        """Fetch current states for specific issue IDs.

        Used for reconciliation to check if running issues have changed state.

        Args:
            issue_ids: List of issue IDs to fetch

        Returns:
            List of Issue objects with current state

        Raises:
            TrackerError: If fetch fails
        """
        pass

    @abstractmethod
    async def create_comment(self, issue_id: str, body: str) -> None:
        """Create a comment on an issue.

        Args:
            issue_id: Issue ID to comment on
            body: Comment body text

        Raises:
            TrackerError: If comment creation fails
        """
        pass

    @abstractmethod
    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """Update the state of an issue.

        Args:
            issue_id: Issue ID to update
            state_name: New state name

        Raises:
            TrackerError: If update fails
        """
        pass

    async def health_check(self) -> dict[str, Any]:
        """Check tracker connectivity and health.

        Returns:
            Dictionary with health status information
        """
        return {"healthy": True, "tracker": self.__class__.__name__}
