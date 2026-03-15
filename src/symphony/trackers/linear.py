"""Linear issue tracker implementation.

Provides GraphQL API client for Linear integration.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from symphony.models.issue import BlockerRef, Issue
from symphony.trackers.base import BaseTracker, TrackerError

logger = logging.getLogger(__name__)

# GraphQL queries
QUERY_CANDIDATE_ISSUES = """
query SymphonyLinearPoll($projectSlug: String!, $stateNames: [String!]!, $first: Int!, $relationFirst: Int!, $after: String) {
  issues(filter: {project: {slugId: {eq: $projectSlug}}, state: {name: {in: $stateNames}}}, first: $first, after: $after) {
    nodes {
      id
      identifier
      title
      description
      priority
      state {
        name
      }
      branchName
      url
      assignee {
        id
      }
      labels {
        nodes {
          name
        }
      }
      inverseRelations(first: $relationFirst) {
        nodes {
          type
          issue {
            id
            identifier
            state {
              name
            }
          }
        }
      }
      createdAt
      updatedAt
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

QUERY_ISSUES_BY_IDS = """
query SymphonyLinearIssuesById($ids: [ID!]!, $first: Int!, $relationFirst: Int!) {
  issues(filter: {id: {in: $ids}}, first: $first) {
    nodes {
      id
      identifier
      title
      description
      priority
      state {
        name
      }
      branchName
      url
      assignee {
        id
      }
      labels {
        nodes {
          name
        }
      }
      inverseRelations(first: $relationFirst) {
        nodes {
          type
          issue {
            id
            identifier
            state {
              name
            }
          }
        }
      }
      createdAt
      updatedAt
    }
  }
}
"""

QUERY_VIEWER = """
query SymphonyLinearViewer {
  viewer {
    id
  }
}
"""

MUTATION_CREATE_COMMENT = """
mutation SymphonyCreateComment($issueId: String!, $body: String!) {
  commentCreate(input: {issueId: $issueId, body: $body}) {
    success
  }
}
"""

MUTATION_UPDATE_STATE = """
mutation SymphonyUpdateState($issueId: String!, $stateId: String!) {
  issueUpdate(input: {id: $issueId, stateId: $stateId}) {
    success
  }
}
"""


class LinearTracker(BaseTracker):
    """Linear issue tracker client.

    Implements the BaseTracker interface for Linear's GraphQL API.
    """

    PAGE_SIZE = 50
    TIMEOUT_SECONDS = 30

    def __init__(
        self,
        api_key: str,
        project_slug: str,
        endpoint: str = "https://api.linear.app/graphql",
        active_states: list[str] | None = None,
        terminal_states: list[str] | None = None,
        assignee: str | None = None,
    ) -> None:
        """Initialize Linear tracker.

        Args:
            api_key: Linear API key
            project_slug: Linear project slug
            endpoint: GraphQL endpoint URL
            active_states: List of active state names
            terminal_states: List of terminal state names
            assignee: Filter by assignee ("me" for current user)
        """
        self.api_key = api_key
        self.project_slug = project_slug
        self.endpoint = endpoint
        self.active_states = active_states or ["Todo", "In Progress"]
        self.terminal_states = terminal_states or [
            "Closed", "Cancelled", "Canceled", "Duplicate", "Done"
        ]
        self.assignee = assignee
        self._viewer_id: str | None = None

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            timeout=self.TIMEOUT_SECONDS,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    async def _execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data

        Raises:
            TrackerError: If request fails
        """
        payload = {
            "query": query,
            "variables": variables or {},
        }

        try:
            response = await self._client.post(self.endpoint, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise TrackerError(f"Linear API error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise TrackerError(f"Linear API request failed: {e}") from e

        data = response.json()

        if "errors" in data:
            errors = data["errors"]
            raise TrackerError(f"Linear GraphQL errors: {errors}")

        return data.get("data", {})

    def _normalize_issue(self, issue_data: dict[str, Any]) -> Issue:
        """Normalize Linear API issue data to Issue model.

        Args:
            issue_data: Raw issue data from Linear API

        Returns:
            Normalized Issue object
        """
        # Extract state name
        state_data = issue_data.get("state", {}) or {}
        state_name = state_data.get("name", "")

        # Extract labels
        labels_data = issue_data.get("labels", {}) or {}
        label_nodes = labels_data.get("nodes", []) or []
        labels = [label.get("name", "").lower() for label in label_nodes if label]

        # Extract blockers from inverseRelations
        blockers = []
        relations_data = issue_data.get("inverseRelations", {}) or {}
        relation_nodes = relations_data.get("nodes", []) or []
        for relation in relation_nodes:
            if relation and relation.get("type", "").lower() == "blocks":
                blocker_issue = relation.get("issue", {})
                if blocker_issue:
                    blocker_state = blocker_issue.get("state", {}) or {}
                    blockers.append(
                        BlockerRef(
                            id=blocker_issue.get("id"),
                            identifier=blocker_issue.get("identifier"),
                            state=blocker_state.get("name"),
                        )
                    )

        # Parse timestamps
        created_at = self._parse_datetime(issue_data.get("createdAt"))
        updated_at = self._parse_datetime(issue_data.get("updatedAt"))

        # Extract assignee
        assignee_data = issue_data.get("assignee", {})
        assignee_id = assignee_data.get("id") if assignee_data else None

        # Determine if assigned to worker
        assigned_to_worker = self._check_assigned_to_worker(assignee_id)

        return Issue(
            id=issue_data.get("id", ""),
            identifier=issue_data.get("identifier", ""),
            title=issue_data.get("title", ""),
            description=issue_data.get("description"),
            priority=issue_data.get("priority"),
            state=state_name,
            branch_name=issue_data.get("branchName"),
            url=issue_data.get("url"),
            assignee_id=assignee_id,
            labels=labels,
            blocked_by=blockers,
            assigned_to_worker=assigned_to_worker,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse ISO datetime string."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _check_assigned_to_worker(self, assignee_id: str | None) -> bool:
        """Check if issue is assigned to this worker.

        If no assignee filter is configured, all issues are eligible.
        If "me" is configured, compares against viewer ID.
        """
        if not self.assignee:
            return True

        if self.assignee == "me":
            return assignee_id == self._viewer_id

        return True  # Other assignee filters not yet implemented

    async def _get_viewer_id(self) -> str | None:
        """Get current viewer ID for "me" assignee filter."""
        if self._viewer_id is not None:
            return self._viewer_id

        try:
            data = await self._execute(QUERY_VIEWER)
            viewer = data.get("viewer", {})
            self._viewer_id = viewer.get("id")
            return self._viewer_id
        except TrackerError:
            return None

    async def fetch_candidate_issues(self) -> list[Issue]:
        """Fetch issues in active states.

        Returns:
            List of Issue objects
        """
        if self.assignee == "me":
            await self._get_viewer_id()

        all_issues: list[Issue] = []
        after_cursor: str | None = None

        while True:
            variables = {
                "projectSlug": self.project_slug,
                "stateNames": self.active_states,
                "first": self.PAGE_SIZE,
                "relationFirst": self.PAGE_SIZE,
                "after": after_cursor,
            }

            data = await self._execute(QUERY_CANDIDATE_ISSUES, variables)
            issues_data = data.get("issues", {}) or {}
            nodes = issues_data.get("nodes", []) or []
            page_info = issues_data.get("pageInfo", {}) or {}

            for node in nodes:
                if node:
                    issue = self._normalize_issue(node)
                    if issue.assigned_to_worker:
                        all_issues.append(issue)

            if not page_info.get("hasNextPage"):
                break

            after_cursor = page_info.get("endCursor")
            if not after_cursor:
                break

        logger.debug(f"Fetched {len(all_issues)} candidate issues")
        return all_issues

    async def fetch_issues_by_states(self, states: list[str]) -> list[Issue]:
        """Fetch issues in specific states.

        Args:
            states: List of state names

        Returns:
            List of Issue objects
        """
        if not states:
            return []

        all_issues: list[Issue] = []
        after_cursor: str | None = None

        while True:
            variables = {
                "projectSlug": self.project_slug,
                "stateNames": states,
                "first": self.PAGE_SIZE,
                "relationFirst": self.PAGE_SIZE,
                "after": after_cursor,
            }

            data = await self._execute(QUERY_CANDIDATE_ISSUES, variables)
            issues_data = data.get("issues", {}) or {}
            nodes = issues_data.get("nodes", []) or []
            page_info = issues_data.get("pageInfo", {}) or {}

            for node in nodes:
                if node:
                    all_issues.append(self._normalize_issue(node))

            if not page_info.get("hasNextPage"):
                break

            after_cursor = page_info.get("endCursor")
            if not after_cursor:
                break

        return all_issues

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        """Fetch current states for specific issue IDs.

        Args:
            issue_ids: List of issue IDs

        Returns:
            List of Issue objects
        """
        if not issue_ids:
            return []

        # Split into batches
        all_issues: list[Issue] = []

        for i in range(0, len(issue_ids), self.PAGE_SIZE):
            batch = issue_ids[i : i + self.PAGE_SIZE]

            variables = {
                "ids": batch,
                "first": len(batch),
                "relationFirst": self.PAGE_SIZE,
            }

            data = await self._execute(QUERY_ISSUES_BY_IDS, variables)
            issues_data = data.get("issues", {}) or {}
            nodes = issues_data.get("nodes", []) or []

            for node in nodes:
                if node:
                    all_issues.append(self._normalize_issue(node))

        return all_issues

    async def create_comment(self, issue_id: str, body: str) -> None:
        """Create a comment on an issue.

        Args:
            issue_id: Issue ID
            body: Comment body
        """
        variables = {
            "issueId": issue_id,
            "body": body,
        }

        data = await self._execute(MUTATION_CREATE_COMMENT, variables)
        result = data.get("commentCreate", {})

        if not result.get("success"):
            raise TrackerError("Failed to create comment")

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """Update issue state.

        Note: This requires looking up the state ID from the state name,
        which is not implemented in this basic version.

        Args:
            issue_id: Issue ID
            state_name: New state name
        """
        # TODO: Implement state ID lookup
        raise NotImplementedError("State update requires state ID lookup")
