"""In-memory tracker for testing.

Provides a tracker implementation that stores issues in memory,
useful for testing and development.
"""

from __future__ import annotations

from symphony.models.issue import Issue
from symphony.trackers.base import BaseTracker


class MemoryTracker(BaseTracker):
    """In-memory issue tracker for testing."""

    def __init__(self) -> None:
        """Initialize memory tracker."""
        self._issues: dict[str, Issue] = {}
        self._comments: dict[str, list[str]] = {}

    def add_issue(self, issue: Issue) -> None:
        """Add an issue to the tracker.

        Args:
            issue: Issue to add
        """
        self._issues[issue.id] = issue

    def update_issue(self, issue: Issue) -> None:
        """Update an existing issue.

        Args:
            issue: Issue to update
        """
        self._issues[issue.id] = issue

    def remove_issue(self, issue_id: str) -> None:
        """Remove an issue.

        Args:
            issue_id: ID of issue to remove
        """
        self._issues.pop(issue_id, None)

    def clear(self) -> None:
        """Clear all issues."""
        self._issues.clear()
        self._comments.clear()

    async def fetch_candidate_issues(self) -> list[Issue]:
        """Fetch all non-terminal issues."""
        return [
            issue for issue in self._issues.values()
            if not issue.is_in_state({"closed", "done", "cancelled", "canceled", "duplicate"})
        ]

    async def fetch_issues_by_states(self, states: list[str]) -> list[Issue]:
        """Fetch issues in specific states."""
        return [issue for issue in self._issues.values() if issue.is_in_state(states)]

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        """Fetch issues by IDs."""
        return [self._issues[id] for id in issue_ids if id in self._issues]

    async def create_comment(self, issue_id: str, body: str) -> None:
        """Create a comment on an issue."""
        if issue_id not in self._comments:
            self._comments[issue_id] = []
        self._comments[issue_id].append(body)

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """Update issue state."""
        if issue_id in self._issues:
            issue = self._issues[issue_id]
            # Create updated issue with new state
            updated = Issue(
                id=issue.id,
                identifier=issue.identifier,
                title=issue.title,
                description=issue.description,
                priority=issue.priority,
                state=state_name,
                branch_name=issue.branch_name,
                url=issue.url,
                assignee_id=issue.assignee_id,
                labels=issue.labels,
                blocked_by=issue.blocked_by,
                assigned_to_worker=issue.assigned_to_worker,
                created_at=issue.created_at,
                updated_at=issue.updated_at,
            )
            self._issues[issue_id] = updated
