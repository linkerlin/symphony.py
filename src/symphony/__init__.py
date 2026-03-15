"""Symphony - Agent Orchestration System (Python Edition).

Symphony turns project work into isolated, autonomous implementation runs,
allowing teams to manage work instead of supervising coding agents.

Example:
    >>> from symphony import Symphony
    >>> symphony = Symphony.from_workflow("WORKFLOW.md")
    >>> await symphony.start()
"""

__version__ = "0.1.0"
__all__ = ["Symphony", "__version__"]

from symphony.orchestrator.orchestrator import Orchestrator as Symphony
