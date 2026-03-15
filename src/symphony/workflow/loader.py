"""Workflow file loader for Symphony.

Parses WORKFLOW.md files with YAML front matter and Markdown body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WorkflowLoadResult:
    """Result of loading a workflow file.

    Attributes:
        front_matter: Parsed YAML front matter as dict
        prompt_template: Markdown body as string
        raw_content: Original file content
        error: Error message if loading failed
    """

    front_matter: dict[str, Any] | None = None
    prompt_template: str = ""
    raw_content: str = ""
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """Check if workflow was loaded successfully."""
        return self.error is None

    @property
    def prompt(self) -> str:
        """Alias for prompt_template."""
        return self.prompt_template


class WorkflowLoader:
    """Loader for WORKFLOW.md files.

    Parses files with optional YAML front matter delimited by ---
    and a Markdown body.

    Example:
        >>> loader = WorkflowLoader()
        >>> result = loader.load("WORKFLOW.md")
        >>> print(result.front_matter.get("tracker", {}).get("kind"))
        >>> print(result.prompt_template)
    """

    # Regex to match YAML front matter
    # Matches --- at start, then content until next ---
    FRONT_MATTER_PATTERN = re.compile(
        r"^---\s*\n"  # Opening ---
        r"(.*?)"  # Front matter content (non-greedy)
        r"\n---\s*\n"  # Closing ---
        r"(.*)$",  # Rest of content (markdown body)
        re.DOTALL,
    )

    def load(self, path: str | Path) -> WorkflowLoadResult:
        """Load and parse a workflow file.

        Args:
            path: Path to the workflow file

        Returns:
            WorkflowLoadResult with parsed content or error
        """
        path = Path(path)

        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return WorkflowLoadResult(
                error=f"Workflow file not found: {path}"
            )
        except UnicodeDecodeError as e:
            return WorkflowLoadResult(
                error=f"Failed to decode workflow file: {e}"
            )
        except Exception as e:
            return WorkflowLoadResult(
                error=f"Failed to read workflow file: {e}"
            )

        return self.parse(content)

    def parse(self, content: str) -> WorkflowLoadResult:
        """Parse workflow content string.

        Args:
            content: Workflow file content

        Returns:
            WorkflowLoadResult with parsed content or error
        """
        # Try to match front matter pattern
        match = self.FRONT_MATTER_PATTERN.match(content)

        if match:
            front_matter_text = match.group(1)
            body_text = match.group(2)

            # Parse YAML front matter
            try:
                front_matter = yaml.safe_load(front_matter_text)
                if front_matter is None:
                    front_matter = {}
                elif not isinstance(front_matter, dict):
                    return WorkflowLoadResult(
                        raw_content=content,
                        error="Workflow front matter must be a YAML mapping (dictionary)",
                    )
            except yaml.YAMLError as e:
                return WorkflowLoadResult(
                    raw_content=content,
                    error=f"Failed to parse YAML front matter: {e}",
                )
        else:
            # No front matter, entire content is the body
            front_matter = {}
            body_text = content

        # Clean up body: trim whitespace
        body_text = body_text.strip()

        return WorkflowLoadResult(
            front_matter=front_matter,
            prompt_template=body_text,
            raw_content=content,
        )

    def load_prompt_only(self, path: str | Path) -> str:
        """Load only the prompt template from a workflow file.

        Args:
            path: Path to the workflow file

        Returns:
            Prompt template string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        result = self.load(path)
        if result.error:
            raise ValueError(result.error)
        return result.prompt_template


def load_workflow(path: str | Path) -> WorkflowLoadResult:
    """Convenience function to load a workflow file.

    Args:
        path: Path to the workflow file

    Returns:
        WorkflowLoadResult with parsed content
    """
    loader = WorkflowLoader()
    return loader.load(path)
