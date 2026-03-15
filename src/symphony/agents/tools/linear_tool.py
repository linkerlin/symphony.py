"""Agent 的 Linear GraphQL 工具。

允许 Agent 与 Linear API 交互。
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
    """对 Linear 执行 GraphQL 查询。

    此工具允许 Agent 与 Linear 交互，例如：
    - 为问题添加评论
    - 更新问题状态
    - 查询问题信息
    - 创建新问题

    Args:
        query: GraphQL 查询或变更字符串
        variables: 查询的可选变量
        _workspace: 工作区目录（由 Agent 注入）
        **kwargs: 附加参数（可能包含来自配置的 api_key）

    Returns:
        GraphQL 响应数据

    Example:
        >>> result = await linear_graphql(
        ...     query="mutation {{ commentCreate(input: {{issueId: \"...\", body: \"Done\"}}) {{ success }} }}",
        ...     api_key="lin_api_..."
        ... )
    """
    # 从 kwargs 或环境变量获取 API 密钥
    api_key = kwargs.get("api_key") or kwargs.get("linear_api_key")
    if not api_key:
        # 尝试从环境变量获取
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
    """为 Linear 问题添加评论。

    Args:
        issue_id: Linear 问题 ID
        body: 评论文本（支持 Markdown）
        **kwargs: 附加参数

    Returns:
        包含成功状态的结果字典
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
    """更新 Linear 问题的状态。

    Args:
        issue_id: Linear 问题 ID
        state_id: 要转换到的状态 ID
        **kwargs: 附加参数

    Returns:
        包含成功状态的结果字典
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
    """获取 Linear 问题的详细信息。

    Args:
        issue_id: Linear 问题 ID
        **kwargs: 附加参数

    Returns:
        问题详细信息字典
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
