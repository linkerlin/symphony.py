"""用于测试的内存跟踪器。

提供一个将问题存储在内存中的跟踪器实现，
适用于测试和开发。
"""

from __future__ import annotations

from symphony.models.issue import Issue
from symphony.trackers.base import BaseTracker


class MemoryTracker(BaseTracker):
    """用于测试的内存问题跟踪器。"""

    def __init__(self) -> None:
        """初始化内存跟踪器。"""
        self._issues: dict[str, Issue] = {}
        self._comments: dict[str, list[str]] = {}

    def add_issue(self, issue: Issue) -> None:
        """向跟踪器添加一个问题。

        参数:
            issue: 要添加的问题
        """
        self._issues[issue.id] = issue

    def update_issue(self, issue: Issue) -> None:
        """更新现有问题。

        参数:
            issue: 要更新的问题
        """
        self._issues[issue.id] = issue

    def remove_issue(self, issue_id: str) -> None:
        """移除一个问题。

        参数:
            issue_id: 要移除的问题 ID
        """
        self._issues.pop(issue_id, None)

    def clear(self) -> None:
        """清除所有问题。"""
        self._issues.clear()
        self._comments.clear()

    async def fetch_candidate_issues(self) -> list[Issue]:
        """获取所有非终止状态的问题。"""
        return [
            issue for issue in self._issues.values()
            if not issue.is_in_state({"closed", "done", "cancelled", "canceled", "duplicate"})
        ]

    async def fetch_issues_by_states(self, states: list[str]) -> list[Issue]:
        """获取特定状态的问题。"""
        return [issue for issue in self._issues.values() if issue.is_in_state(states)]

    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        """根据 ID 获取问题。"""
        return [self._issues[id] for id in issue_ids if id in self._issues]

    async def create_comment(self, issue_id: str, body: str) -> None:
        """在问题上创建评论。"""
        if issue_id not in self._comments:
            self._comments[issue_id] = []
        self._comments[issue_id].append(body)

    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """更新问题状态。"""
        if issue_id in self._issues:
            issue = self._issues[issue_id]
            # 创建带有新状态的更新后的问题
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
