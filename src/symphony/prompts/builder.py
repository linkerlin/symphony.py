"""Symphony 的提示词构建器。

从工作流模板和问题数据构建智能体提示词。
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import StrictUndefined, Template, UndefinedError

from symphony.models.issue import Issue
from symphony.workflow.loader import WorkflowLoader

logger = logging.getLogger(__name__)


# 当工作流正文为空时使用的默认提示词模板
DEFAULT_PROMPT_TEMPLATE = """You are working on a Linear issue.

Identifier: {{ issue.identifier }}
Title: {{ issue.title }}

Description:
{% if issue.description %}
{{ issue.description }}
{% else %}
No description provided.
{% endif %}

Please analyze this issue and implement the necessary changes.
"""


class PromptBuilder:
    """从模板和问题数据构建提示词。

    使用 Jinja2 进行模板渲染，并启用严格的变量检查。
    """

    def __init__(self, template: str | None = None) -> None:
        """初始化提示词构建器。

        参数:
            template: Jinja2 模板字符串，若为 None 则使用默认模板
        """
        self.template_str = template or DEFAULT_PROMPT_TEMPLATE
        self._template: Template | None = None

    @classmethod
    def from_workflow(cls, workflow_path: str | Path) -> "PromptBuilder":
        """从工作流文件创建构建器。

        参数:
            workflow_path: WORKFLOW.md 文件的路径

        返回:
            配置好的 PromptBuilder
        """
        loader = WorkflowLoader()
        result = loader.load(workflow_path)

        if result.error:
            logger.warning(f"加载工作流失败，使用默认模板: {result.error}")
            return cls()

        template = result.prompt_template
        if not template or not template.strip():
            logger.debug("提示词模板为空，使用默认模板")
            return cls()

        return cls(template)

    def _get_template(self) -> Template:
        """获取或编译 Jinja2 模板。"""
        if self._template is None:
            self._template = Template(
                self.template_str,
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        return self._template

    def build_prompt(
        self,
        issue: Issue,
        attempt: int | None = None,
        turn_number: int = 1,
        max_turns: int = 20,
    ) -> str:
        """为一个问题构建提示词。

        参数:
            issue: 要构建提示词的问题
            attempt: 重试尝试次数（首次运行为 None）
            turn_number: 当前轮次编号（从 1 开始）
            max_turns: 允许的最大轮次数

        返回:
            渲染后的提示词字符串

        抛出:
            ValueError: 如果模板渲染失败
        """
        template = self._get_template()

        # 构建模板的上下文
        context = {
            "issue": issue.to_prompt_dict(),
            "attempt": attempt,
            "turn_number": turn_number,
            "max_turns": max_turns,
            "is_first_turn": turn_number == 1,
            "is_retry": attempt is not None and attempt > 0,
        }

        try:
            return template.render(**context)
        except UndefinedError as e:
            raise ValueError(f"模板变量未定义: {e}") from e
        except Exception as e:
            raise ValueError(f"模板渲染失败: {e}") from e

    def build_continuation_prompt(
        self,
        issue: Issue,
        turn_number: int,
        max_turns: int,
    ) -> str:
        """为后续轮次构建继续提示词。

        参数:
            issue: 正在处理的问题
            turn_number: 当前轮次编号
            max_turns: 允许的最大轮次数

        返回:
            继续提示词字符串
        """
        return f"""Continuation guidance:

- The previous agent turn completed normally, but the issue is still active.
- This is continuation turn #{turn_number} of {max_turns}.
- Resume from the current workspace state instead of restarting.
- Focus on remaining work and avoid repeating completed tasks.
- Continue working on issue {issue.identifier}: {issue.title}
"""

    def get_template(self) -> str:
        """获取原始模板字符串。"""
        return self.template_str
