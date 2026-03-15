"""Symphony Agent implementation.

Uses LLMClient to process issues with multi-turn conversations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from symphony.llm.client import LLMClient, Message
from symphony.models.issue import Issue
from symphony.prompts.builder import PromptBuilder

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Raised when agent execution fails."""

    pass


class SymphonyAgent:
    """Symphony Agent for processing Linear issues.

    Uses LLMClient for multi-turn conversations with tool support.

    Example:
        >>> agent = SymphonyAgent(llm_client, prompt_builder)
        >>> result = await agent.run(issue, workspace_path, max_turns=20)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        tools: dict[str, callable] | None = None,
    ) -> None:
        """Initialize agent.

        Args:
            llm_client: LLM client for completions
            prompt_builder: Prompt builder for generating prompts
            tools: Optional dict of tool functions
        """
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
        self.tools = tools or {}
        self.messages: list[Message] = []

    async def run(
        self,
        issue: Issue,
        workspace_path: Path,
        max_turns: int = 20,
        attempt: int | None = None,
    ) -> dict[str, Any]:
        """Run agent on an issue.

        Args:
            issue: Issue to process
            workspace_path: Workspace directory path
            max_turns: Maximum conversation turns
            attempt: Retry attempt number

        Returns:
            Dict with execution results
        """
        logger.info(f"Starting agent run for {issue.identifier}")

        # Initialize conversation
        self.messages = []

        # Build initial prompt
        system_prompt = self._build_system_prompt(workspace_path)
        user_prompt = self.prompt_builder.build_prompt(issue, attempt, turn_number=1)

        self.messages.append(Message(role="system", content=system_prompt))
        self.messages.append(Message(role="user", content=user_prompt))

        turn_count = 0
        total_tokens = {"prompt": 0, "completion": 0}

        while turn_count < max_turns:
            turn_count += 1
            logger.debug(f"Turn {turn_count}/{max_turns}")

            try:
                # Get LLM response
                response = await self.llm_client.complete(self.messages)

                # Track tokens
                usage = response.usage
                total_tokens["prompt"] += usage.get("prompt_tokens", 0)
                total_tokens["completion"] += usage.get("completion_tokens", 0)

                # Add assistant response to conversation
                self.messages.append(
                    Message(role="assistant", content=response.content)
                )

                # Check if agent wants to use tools
                tool_calls = self._extract_tool_calls(response.content)

                if tool_calls:
                    # Execute tools
                    tool_results = await self._execute_tools(tool_calls, workspace_path)

                    # Add tool results to conversation
                    for result in tool_results:
                        self.messages.append(
                            Message(
                                role="user",
                                content=f"Tool result: {result}",
                            )
                        )
                else:
                    # No tool calls, check if done
                    if self._is_done(response.content):
                        logger.info(f"Agent completed after {turn_count} turns")
                        break

                    # Continue conversation
                    self.messages.append(
                        Message(
                            role="user",
                            content="Continue working on the task. "
                                    "Use tools if needed, or indicate when done.",
                        )
                    )

            except Exception as e:
                logger.exception(f"Turn {turn_count} failed: {e}")
                raise AgentError(f"Agent execution failed at turn {turn_count}: {e}") from e

        return {
            "success": True,
            "turns": turn_count,
            "total_tokens": total_tokens,
            "messages": self._messages_to_dicts(),
        }

    def _build_system_prompt(self, workspace_path: Path) -> str:
        """Build system prompt with context."""
        return f"""You are a software engineering agent working on a Linear issue.

Workspace: {workspace_path}

You have access to tools:
- read_file(file_path): Read file content from workspace
- write_file(file_path, content): Write content to file
- execute_command(command, timeout=60): Execute shell command
- linear_graphql(query, variables=None): Execute GraphQL queries against Linear
- add_comment(issue_id, body): Add a comment to a Linear issue
- get_issue(issue_id): Get Linear issue details
- update_issue_state(issue_id, state_id): Update issue state

Guidelines:
1. Work autonomously - do not ask the user for input
2. Use tools to gather information and make changes
3. Make incremental progress and track your work
4. When finished, summarize what was done
5. Report any blockers that prevent completion

Always use tools through the proper format:
```tool
{{"name": "tool_name", "arguments": {{...}}}}
```
"""

    def _extract_tool_calls(self, content: str) -> list[dict[str, Any]]:
        """Extract tool calls from LLM response."""
        tool_calls = []

        # Look for tool call blocks
        import re
        pattern = r'```tool\s*\n(.*?)\n```'
        matches = re.findall(pattern, content, re.DOTALL)

        for match in matches:
            try:
                tool_call = json.loads(match.strip())
                if "name" in tool_call and "arguments" in tool_call:
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool call: {match}")

        return tool_calls

    async def _execute_tools(
        self,
        tool_calls: list[dict[str, Any]],
        workspace_path: Path,
    ) -> list[str]:
        """Execute tool calls."""
        results = []

        for call in tool_calls:
            tool_name = call.get("name")
            arguments = call.get("arguments", {})

            if tool_name in self.tools:
                try:
                    # Add workspace to arguments
                    arguments["_workspace"] = str(workspace_path)

                    result = await self.tools[tool_name](**arguments)
                    results.append(json.dumps({"success": True, "result": result}))
                except Exception as e:
                    results.append(json.dumps({"success": False, "error": str(e)}))
            else:
                results.append(json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}))

        return results

    def _is_done(self, content: str) -> bool:
        """Check if agent indicates task completion."""
        # Look for completion indicators
        done_markers = [
            "task completed",
            "finished",
            "done",
            "completed successfully",
        ]
        content_lower = content.lower()
        return any(marker in content_lower for marker in done_markers)

    def _messages_to_dicts(self) -> list[dict[str, str]]:
        """Convert messages to dicts."""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
        ]

    async def run_turn(self) -> str:
        """Run a single turn and return response content."""
        response = await self.llm_client.complete(self.messages)
        self.messages.append(Message(role="assistant", content=response.content))
        return response.content
