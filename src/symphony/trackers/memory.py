"""用于测试的内存跟踪器。

提供一个将问题存储在内存中的跟踪器实现，
适用于测试和开发。
"""

from __future__ import annotations

from symphony.models.issue import Issue
from symphony.trackers.base import BaseTracker


class MemoryTracker(BaseTracker):
    """用于测试的内存问题跟踪器。"""

    def __init__(
        self,
        active_states: list[str] | None = None,
        terminal_states: list[str] | None = None,
    ) -> None:
        """初始化内存跟踪器。

        参数:
            active_states: 活跃状态列表，用于过滤候选问题
            terminal_states: 终止状态列表，用于识别已完成问题
        """
        self._issues: dict[str, Issue] = {}
        self._comments: dict[str, list[str]] = {}
        self._claimed: set[str] = set()
        self._completed_issues: dict[str, dict] = {}
        # 规范化状态为小写
        self._active_states = {s.lower() for s in active_states} if active_states else {"todo", "in progress"}
        self._terminal_states = {s.lower() for s in terminal_states} if terminal_states else {"done", "closed", "canceled"}

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

    async def close(self) -> None:
        """关闭跟踪器，清理资源。"""
        self._issues.clear()
        self._comments.clear()
        self._claimed.clear()

    async def claim(self, issue: Issue) -> bool:
        """认领一个问题。

        参数:
            issue: 要认领的问题

        返回:
            如果成功认领则返回 True，如果已被认领则返回 False
        """
        if issue.id in self._claimed:
            return False
        self._claimed.add(issue.id)
        return True

    async def complete(self, issue: Issue, success: bool = True) -> bool:
        """完成一个问题。

        参数:
            issue: 要完成的问题
            success: 是否成功完成

        返回:
            如果成功完成则返回 True
        """
        self._completed_issues[issue.id] = {
            "issue_id": issue.id,
            "success": success,
        }
        # 从认领集合中移除
        self._claimed.discard(issue.id)
        return True

    @property
    def completed_issues(self) -> dict[str, dict]:
        """获取已完成问题的字典。"""
        return self._completed_issues

    async def fetch_candidate_issues(self) -> list[Issue]:
        """获取所有非终止状态的问题。"""
        return [
            issue for issue in self._issues.values()
            if issue.get_normalized_state() in self._active_states
        ]
