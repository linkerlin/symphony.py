"""Prompt builder for Symphony.

Builds agent prompts from workflow templates and issue data.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import StrictUndefined, Template, UndefinedError

from symphony.models.issue import Issue
from symphony.workflow.loader import WorkflowLoader

logger = logging.getLogger(__name__)


# Default prompt template if workflow has empty body
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
    """Builds prompts from templates and issue data.

    Uses Jinja2 for template rendering with strict variable checking.
    """

    def __init__(self, template: str | None = None) -> None:
        """Initialize prompt builder.

        Args:
            template: Jinja2 template string, or None to use default
        """
        self.template_str = template or DEFAULT_PROMPT_TEMPLATE
        self._template: Template | None = None

    @classmethod
    def from_workflow(cls, workflow_path: str | Path) -> "PromptBuilder":
        """Create builder from workflow file.

        Args:
            workflow_path: Path to WORKFLOW.md file

        Returns:
            Configured PromptBuilder
        """
        loader = WorkflowLoader()
        result = loader.load(workflow_path)

        if result.error:
            logger.warning(f"Failed to load workflow, using default: {result.error}")
            return cls()

        template = result.prompt_template
        if not template or not template.strip():
            logger.debug("Empty prompt template, using default")
            return cls()

        return cls(template)

    def _get_template(self) -> Template:
        """Get or compile Jinja2 template."""
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
        """Build prompt for an issue.

        Args:
            issue: Issue to build prompt for
            attempt: Retry attempt number (None for first run)
            turn_number: Current turn number (1-based)
            max_turns: Maximum turns allowed

        Returns:
            Rendered prompt string

        Raises:
            ValueError: If template rendering fails
        """
        template = self._get_template()

        # Build context for template
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
            raise ValueError(f"Template variable undefined: {e}") from e
        except Exception as e:
            raise ValueError(f"Template rendering failed: {e}") from e

    def build_continuation_prompt(
        self,
        issue: Issue,
        turn_number: int,
        max_turns: int,
    ) -> str:
        """Build continuation prompt for subsequent turns.

        Args:
            issue: Issue being processed
            turn_number: Current turn number
            max_turns: Maximum turns allowed

        Returns:
            Continuation prompt string
        """
        return f"""Continuation guidance:

- The previous agent turn completed normally, but the issue is still active.
- This is continuation turn #{turn_number} of {max_turns}.
- Resume from the current workspace state instead of restarting.
- Focus on remaining work and avoid repeating completed tasks.
- Continue working on issue {issue.identifier}: {issue.title}
"""

    def get_template(self) -> str:
        """Get the raw template string."""
        return self.template_str
