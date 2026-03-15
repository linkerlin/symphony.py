"""Linear 问题跟踪器实现。

为 Linear 集成提供 GraphQL API 客户端。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from symphony.models.issue import BlockerRef, Issue
from symphony.trackers.base import BaseTracker, TrackerError

logger = logging.getLogger(__name__)

# GraphQL 查询
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
    """Linear 问题跟踪器客户端。

    为 Linear 的 GraphQL API 实现 BaseTracker 接口。
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
        """初始化 Linear 跟踪器。

        参数:
            api_key: Linear API 密钥
            project_slug: Linear 项目标识
            endpoint: GraphQL 端点 URL
            active_states: 活跃状态名称列表
            terminal_states: 终止状态名称列表
            assignee: 按负责人筛选（"me" 表示当前用户）
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
        """关闭 HTTP 客户端。"""
        await self._client.aclose()

    async def _execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行 GraphQL 查询。

        参数:
            query: GraphQL 查询字符串
            variables: 查询变量

        返回:
            响应数据

        抛出:
            TrackerError: 如果请求失败
        """
        payload = {
            "query": query,
            "variables": variables or {},
        }

        try:
            response = await self._client.post(self.endpoint, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise TrackerError(f"Linear API 错误: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise TrackerError(f"Linear API 请求失败: {e}") from e

        data = response.json()

        if "errors" in data:
            errors = data["errors"]
            raise TrackerError(f"Linear GraphQL 错误: {errors}")

        return data.get("data", {})

    def _normalize_issue(self, issue_data: dict[str, Any]) -> Issue:
        """将 Linear API 问题数据规范化为 Issue 模型。

        参数:
            issue_data: Linear API 返回的原始问题数据

        返回:
            规范化后的 Issue 对象
        """
        # 提取状态名称
        state_data = issue_data.get("state", {}) or {}
        state_name = state_data.get("name", "")

        # 提取标签
        labels_data = issue_data.get("labels", {}) or {}
        label_nodes = labels_data.get("nodes", []) or []
        labels = [label.get("name", "").lower() for label in label_nodes if label]

        # 从 inverseRelations 提取阻塞项
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

        # 解析时间戳
        created_at = self._parse_datetime(issue_data.get("createdAt"))
        updated_at = self._parse_datetime(issue_data.get("updatedAt"))

        # 提取负责人
        assignee_data = issue_data.get("assignee", {})
        assignee_id = assignee_data.get("id") if assignee_data else None

        # 判断是否分配给当前工作器
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
        """解析 ISO 格式的时间字符串。"""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _check_assigned_to_worker(self, assignee_id: str | None) -> bool:
        """检查问题是否分配给当前工作器。

        如果未配置负责人筛选，则所有问题都符合条件。
        如果配置了 "me"，则与当前查看者 ID 比较。
        """
        if not self.assignee:
            return True

        if self.assignee == "me":
            return assignee_id == self._viewer_id

        return True  # 其他负责人筛选尚未实现

    async def _get_viewer_id(self) -> str | None:
        """获取当前查看者 ID，用于 "me" 负责人筛选。"""
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
        """获取处于活跃状态的问题。

        返回:
            Issue 对象列表
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

        logger.debug(f"获取到 {len(all_issues)} 个候选问题")
        return all_issues

    async def fetch_issues_by_states(self, states: list[str]) -> list[Issue]:
        """获取特定状态的问题。

        参数:
            states: 状态名称列表

        返回:
            Issue 对象列表
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
        """获取特定问题 ID 的当前状态。

        参数:
            issue_ids: 问题 ID 列表

        返回:
            Issue 对象列表
        """
        if not issue_ids:
            return []

        # 分批处理
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
        """在问题上创建评论。

        参数:
            issue_id: 问题 ID
            body: 评论正文
        """
        variables = {
            "issueId": issue_id,
            "body": body,
        }

        data = await self._execute(MUTATION_CREATE_COMMENT, variables)
        result = data.get("commentCreate", {})

        if not result.get("success"):
            raise TrackerError("创建评论失败")

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """更新问题状态。

        注意：这需要根据状态名称查找状态 ID，
        在此基础版本中尚未实现。

        参数:
            issue_id: 问题 ID
            state_name: 新状态名称
        """
        # TODO: 实现状态 ID 查找
        raise NotImplementedError("状态更新需要状态 ID 查找")
