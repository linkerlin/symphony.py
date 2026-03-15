"""问题跟踪器适配器的基类。

定义所有跟踪器实现必须遵循的接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from symphony.models.issue import Issue


class TrackerError(Exception):
    """当跟踪器操作失败时抛出。"""

    pass


class BaseTracker(ABC):
    """问题跟踪器的抽象基类。

    所有跟踪器实现必须继承自此类并实现所需的方法。
    """

    @abstractmethod
    async def fetch_candidate_issues(self) -> list[Issue]:
        """获取处于活跃状态、可作为分派候选的问题。

        返回:
            Issue 对象列表

        抛出:
            TrackerError: 如果获取失败
        """
        pass

    @abstractmethod
    async def fetch_issues_by_states(self, states: list[str]) -> list[Issue]:
        """获取特定状态的问题。

        参数:
            states: 要获取的状态名称列表

        返回:
            Issue 对象列表

        抛出:
            TrackerError: 如果获取失败
        """
        pass

    @abstractmethod
    async def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> list[Issue]:
        """获取特定问题 ID 的当前状态。

        用于对账检查，确认运行中的问题是否已改变状态。

        参数:
            issue_ids: 要获取的问题 ID 列表

        返回:
            包含当前状态的 Issue 对象列表

        抛出:
            TrackerError: 如果获取失败
        """
        pass

    @abstractmethod
    async def create_comment(self, issue_id: str, body: str) -> None:
        """在问题上创建评论。

        参数:
            issue_id: 要评论的问题 ID
            body: 评论正文文本

        抛出:
            TrackerError: 如果评论创建失败
        """
        pass

    @abstractmethod
    async def update_issue_state(self, issue_id: str, state_name: str) -> None:
        """更新问题的状态。

        参数:
            issue_id: 要更新的问题 ID
            state_name: 新状态名称

        抛出:
            TrackerError: 如果更新失败
        """
        pass

    async def health_check(self) -> dict[str, Any]:
        """检查跟踪器的连接和健康状态。

        返回:
            包含健康状态信息的字典
        """
        return {"healthy": True, "tracker": self.__class__.__name__}
