"""Symphony - 智能体编排系统 (Python 版)。

Symphony 将项目工作转化为独立的、自主的实现运行，
让团队能够管理工作，而不是监督编码智能体。

示例:
    >>> from symphony import Symphony
    >>> symphony = Symphony.from_workflow("WORKFLOW.md")
    >>> await symphony.start()
"""

__version__ = "0.1.0"
__all__ = ["Symphony", "__version__"]

from symphony.orchestrator.orchestrator import Orchestrator as Symphony
