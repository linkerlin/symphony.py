"""Symphony 工作流文件加载器。

解析带有 YAML 前置内容和 Markdown 正文的 WORKFLOW.md 文件。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WorkflowLoadResult:
    """加载工作流文件的结果。

    属性：
        front_matter: 解析后的 YAML 前置内容，以字典形式表示
        prompt_template: Markdown 正文字符串
        raw_content: 原始文件内容
        error: 如果加载失败，则为错误消息
    """

    front_matter: dict[str, Any] | None = None
    prompt_template: str = ""
    raw_content: str = ""
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """检查工作流是否加载成功。"""
        return self.error is None

    @property
    def prompt(self) -> str:
        """prompt_template 的别名。"""
        return self.prompt_template


class WorkflowLoader:
    """WORKFLOW.md 文件的加载器。

    解析带有可选 YAML 前置内容的文件，前置内容由 --- 分隔，
    以及 Markdown 正文。

    示例：
        >>> loader = WorkflowLoader()
        >>> result = loader.load("WORKFLOW.md")
        >>> print(result.front_matter.get("tracker", {}).get("kind"))
        >>> print(result.prompt_template)
    """

    # 匹配 YAML 前置内容的正则表达式
    # 匹配开头的 ---，然后匹配下一个 --- 之前的内容
    FRONT_MATTER_PATTERN = re.compile(
        r"^---\s*\n"  # 开头的 ---
        r"(.*?)"  # 前置内容（非贪婪）
        r"\n---\s*\n"  # 结束的 ---
        r"(.*)$",  # 其余内容（markdown 正文）
        re.DOTALL,
    )

    def load(self, path: str | Path) -> WorkflowLoadResult:
        """加载并解析工作流文件。

        参数：
            path: 工作流文件的路径

        返回：
            包含解析内容或错误的 WorkflowLoadResult
        """
        path = Path(path)

        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return WorkflowLoadResult(
                error=f"未找到工作流文件: {path}"
            )
        except UnicodeDecodeError as e:
            return WorkflowLoadResult(
                error=f"解码工作流文件失败: {e}"
            )
        except Exception as e:
            return WorkflowLoadResult(
                error=f"读取工作流文件失败: {e}"
            )

        return self.parse(content)

    def parse(self, content: str) -> WorkflowLoadResult:
        """解析工作流内容字符串。

        参数：
            content: 工作流文件内容

        返回：
            包含解析内容或错误的 WorkflowLoadResult
        """
        # 尝试匹配前置内容模式
        match = self.FRONT_MATTER_PATTERN.match(content)

        if match:
            front_matter_text = match.group(1)
            body_text = match.group(2)

            # 解析 YAML 前置内容
            try:
                front_matter = yaml.safe_load(front_matter_text)
                if front_matter is None:
                    front_matter = {}
                elif not isinstance(front_matter, dict):
                    return WorkflowLoadResult(
                        raw_content=content,
                        error="工作流前置内容必须是 YAML 映射（字典）",
                    )
            except yaml.YAMLError as e:
                return WorkflowLoadResult(
                    raw_content=content,
                    error=f"解析 YAML 前置内容失败: {e}",
                )
        else:
            # 没有前置内容，整个内容就是正文
            front_matter = {}
            body_text = content

        # 清理正文：去除首尾空白
        body_text = body_text.strip()

        return WorkflowLoadResult(
            front_matter=front_matter,
            prompt_template=body_text,
            raw_content=content,
        )

    def load_prompt_only(self, path: str | Path) -> str:
        """仅从工作流文件加载提示模板。

        参数：
            path: 工作流文件的路径

        返回：
            提示模板字符串

        抛出：
            FileNotFoundError: 如果文件不存在
        """
        result = self.load(path)
        if result.error:
            raise ValueError(result.error)
        return result.prompt_template


def load_workflow(path: str | Path) -> WorkflowLoadResult:
    """加载工作流文件的便捷函数。

    参数：
        path: 工作流文件的路径

    返回：
        包含解析内容的 WorkflowLoadResult
    """
    loader = WorkflowLoader()
    return loader.load(path)
