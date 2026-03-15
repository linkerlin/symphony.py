"""Linear 事项的数据模型。

提供用于规范化事项表示的 Pydantic 模型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class BlockerRef(BaseModel):
    """阻塞事项的引用。

    属性：
        id: Linear 事项 ID
        identifier: 人类可读的标识符（例如 "ABC-123"）
        state: 阻塞事项的当前状态
    """

    id: str | None = None
    identifier: str | None = None
    state: str | None = None

    def is_terminal(self, terminal_states: set[str]) -> bool:
        """检查此阻塞项是否处于终止状态。

        参数：
            terminal_states: 被视为终止的状态名称集合

        返回：
            如果阻塞项处于终止状态则返回 True
        """
        if self.state is None:
            return False
        return self.state.lower() in {s.lower() for s in terminal_states}


class Issue(BaseModel):
    """规范化的 Linear 事项表示。

    此模型以规范化形式表示 Linear 事项，适用于
    编排、提示渲染和可观测性。

    属性：
        id: 稳定的跟踪器内部 ID
        identifier: 人类可读的工单键（例如 "ABC-123"）
        title: 事项标题
        description: 事项描述（可能为 None）
        priority: 优先级数字（数值越小优先级越高，通常为 1-4）
        state: 当前跟踪器状态名称
        branch_name: 跟踪器提供的分支元数据
        url: 事项 URL
        assignee_id: 被分配用户的 ID
        labels: 标签名称列表（规范化为小写）
        blocked_by: 阻塞事项引用列表
        assigned_to_worker: 此事项是否已分配给当前工作器
        created_at: 创建时间戳
        updated_at: 最后更新时间戳
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
        "frozen": False,  # 允许状态更新时进行修改
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_labels(cls, data: dict[str, Any]) -> dict[str, Any]:
        """将标签规范化为小写。"""
        if isinstance(data, dict) and "labels" in data:
            labels = data["labels"]
            if isinstance(labels, list):
                data["labels"] = [
                    label.lower() if isinstance(label, str) else str(label).lower()
                    for label in labels
                ]
        return data

    def get_normalized_state(self) -> str:
        """获取小写规范化的状态名称。"""
        return self.state.lower()

    def is_in_state(self, states: list[str] | set[str]) -> bool:
        """检查事项是否处于任一给定状态。

        参数：
            states: 要检查的状态名称列表或集合

        返回：
            如果事项状态匹配任一给定状态则返回 True
        """
        normalized = self.get_normalized_state()
        return any(normalized == s.lower() for s in states)

    def is_blocked(self, terminal_states: set[str]) -> bool:
        """检查此事项是否被非终止事项阻塞。

        仅适用于处于 "Todo" 状态的事项。处于其他状态的事项
        无论其是否有阻塞项，都不被视为阻塞。

        参数：
            terminal_states: 被视为终止的状态名称集合

        返回：
            如果事项有非终止阻塞项则返回 True
        """
        # 只有 Todo 状态的事项可能被阻塞
        if self.get_normalized_state() != "todo":
            return False

        # 检查是否有任何非终止阻塞项
        for blocker in self.blocked_by:
            if not blocker.is_terminal(terminal_states):
                return True

        return False

    def is_eligible_for_dispatch(
        self,
        active_states: set[str],
        terminal_states: set[str],
    ) -> bool:
        """检查此事项是否有资格被分派。

        当满足以下条件时，事项有资格被分派：
        - 具有所有必需字段（id、identifier、title、state）
        - 其状态在 active_states 中且不在 terminal_states 中
        - 未被非终止事项阻塞（如果处于 Todo 状态）

        参数：
            active_states: 活跃状态名称集合
            terminal_states: 终止状态名称集合

        返回：
            如果事项可以被分派则返回 True
        """
        # 检查必需字段
        if not all([self.id, self.identifier, self.title, self.state]):
            return False

        normalized_state = self.get_normalized_state()

        # 检查状态是否为活跃状态
        if normalized_state not in {s.lower() for s in active_states}:
            return False

        # 检查不是终止状态
        if normalized_state in {s.lower() for s in terminal_states}:
            return False

        # 检查未被阻塞
        if self.is_blocked(terminal_states):
            return False

        return True

    def get_context_string(self) -> str:
        """获取用于日志记录的简短上下文字符串。

        返回：
            形如 "issue_id=abc issue_identifier=ABC-123" 的字符串
        """
        return f"issue_id={self.id} issue_identifier={self.identifier}"

    def to_prompt_dict(self) -> dict[str, Any]:
        """转换为适合提示模板渲染的字典。

        返回：
            包含所有事项字段作为字符串的字典
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
        """事项的字符串表示。"""
        return f"Issue({self.get_context_string()} state={self.state})"

    def __hash__(self) -> int:
        """基于事项 ID 的哈希。"""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """基于事项 ID 的相等性比较。"""
        if not isinstance(other, Issue):
            return NotImplemented
        return self.id == other.id
