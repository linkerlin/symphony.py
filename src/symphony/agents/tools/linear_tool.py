"""Linear GraphQL tool for Agent.

Allows agent to interact with Linear API.
"""

from __future__ import annotations

import json
from typing import Any

import httpx


async def linear_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    _workspace: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a GraphQL query against Linear.

    This tool allows the agent to interact with Linear, such as:
    - Adding comments to issues
    - Updating issue state
    - Querying issue information
    - Creating new issues

    Args:
        query: GraphQL query or mutation string
        variables: Optional variables for the query
        _workspace: Workspace directory (injected by agent)
        **kwargs: Additional arguments (may include api_key from config)

    Returns:
        GraphQL response data

    Example:
        >>> result = await linear_graphql(
        ...     query="mutation {{ commentCreate(input: {{issueId: \"...\", body: \"Done\"}}) {{ success }} }}",
        ...     api_key="lin_api_..."
        ... )
    """
    # Get API key from kwargs or environment
    api_key = kwargs.get("api_key") or kwargs.get("linear_api_key")
    if not api_key:
        # Try to get from environment
        import os
        api_key = os.environ.get("LINEAR_API_KEY")

    if not api_key:
        return {
            "success": False,
            "error": "LINEAR_API_KEY not configured. Set it in environment or pass as api_key."
        }

    endpoint = kwargs.get("endpoint", "https://api.linear.app/graphql")

    payload = {
        "query": query,
        "variables": variables or {},
    }

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                endpoint,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                return {
                    "success": False,
                    "error": data["errors"],
                    "data": data.get("data"),
                }

            return {
                "success": True,
                "data": data.get("data"),
            }

        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error {e.response.status_code}: {e.response.text}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


async def add_comment(
    issue_id: str,
    body: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Add a comment to a Linear issue.

    Args:
        issue_id: Linear issue ID
        body: Comment text (supports Markdown)
        **kwargs: Additional arguments

    Returns:
        Result dict with success status
    """
    query = """
    mutation AddComment($issueId: String!, $body: String!) {
        commentCreate(input: {issueId: $issueId, body: $body}) {
            success
            comment {
                id
                url
            }
        }
    }
    """

    variables = {
        "issueId": issue_id,
        "body": body,
    }

    result = await linear_graphql(query, variables, **kwargs)

    if result.get("success"):
        return {
            "success": True,
            "comment_id": result.get("data", {}).get("commentCreate", {}).get("comment", {}).get("id"),
            "url": result.get("data", {}).get("commentCreate", {}).get("comment", {}).get("url"),
        }

    return result


async def update_issue_state(
    issue_id: str,
    state_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Update the state of a Linear issue.

    Args:
        issue_id: Linear issue ID
        state_id: State ID to transition to
        **kwargs: Additional arguments

    Returns:
        Result dict with success status
    """
    query = """
    mutation UpdateIssueState($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: {stateId: $stateId}) {
            success
            issue {
                id
                identifier
                state {
                    name
                }
            }
        }
    }
    """

    variables = {
        "id": issue_id,
        "stateId": state_id,
    }

    result = await linear_graphql(query, variables, **kwargs)

    if result.get("success"):
        issue = result.get("data", {}).get("issueUpdate", {}).get("issue", {})
        return {
            "success": True,
            "issue_id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "new_state": issue.get("state", {}).get("name"),
        }

    return result


async def get_issue(
    issue_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Get details of a Linear issue.

    Args:
        issue_id: Linear issue ID
        **kwargs: Additional arguments

    Returns:
        Issue details dict
    """
    query = """
    query GetIssue($id: String!) {
        issue(id: $id) {
            id
            identifier
            title
            description
            state {
                id
                name
            }
            assignee {
                id
                name
            }
            labels {
                nodes {
                    name
                }
            }
            comments {
                nodes {
                    id
                    body
                    user {
                        name
                    }
                    createdAt
                }
            }
        }
    }
    """

    variables = {"id": issue_id}
    result = await linear_graphql(query, variables, **kwargs)

    if result.get("success"):
        return {
            "success": True,
            "issue": result.get("data", {}).get("issue"),
        }

    return result
