"""Symphony 智能体实现。

使用 LLMClient 处理多轮对话的问题。
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
    """当智能体执行失败时抛出。"""

    pass


class SymphonyAgent:
    """用于处理 Linear 问题的 Symphony 智能体。

    使用 LLMClient 进行支持工具的多轮对话。

    示例:
        >>> agent = SymphonyAgent(llm_client, prompt_builder)
        >>> result = await agent.run(issue, workspace_path, max_turns=20)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        tools: dict[str, callable] | None = None,
    ) -> None:
        """初始化智能体。

        参数:
            llm_client: 用于补全的 LLM 客户端
            prompt_builder: 用于生成提示词的提示词构建器
            tools: 可选的工具函数字典
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
        """在问题上运行智能体。

        参数:
            issue: 要处理的问题
            workspace_path: 工作空间目录路径
            max_turns: 最大对话轮数
            attempt: 重试尝试次数

        返回:
            包含执行结果的字典
        """
        logger.info(f"正在为 {issue.identifier} 启动智能体运行")

        # 初始化对话
        self.messages = []

        # 构建初始提示词
        system_prompt = self._build_system_prompt(workspace_path)
        user_prompt = self.prompt_builder.build_prompt(issue, attempt, turn_number=1)

        self.messages.append(Message(role="system", content=system_prompt))
        self.messages.append(Message(role="user", content=user_prompt))

        turn_count = 0
        total_tokens = {"prompt": 0, "completion": 0}

        while turn_count < max_turns:
            turn_count += 1
            logger.debug(f"第 {turn_count}/{max_turns} 轮")

            try:
                # 获取 LLM 响应
                response = await self.llm_client.complete(self.messages)

                # 跟踪令牌使用量
                usage = response.usage
                total_tokens["prompt"] += usage.get("prompt_tokens", 0)
                total_tokens["completion"] += usage.get("completion_tokens", 0)

                # 将助手响应添加到对话
                self.messages.append(
                    Message(role="assistant", content=response.content)
                )

                # 检查智能体是否想要使用工具
                tool_calls = self._extract_tool_calls(response.content)

                if tool_calls:
                    # 执行工具
                    tool_results = await self._execute_tools(tool_calls, workspace_path)

                    # 将工具结果添加到对话
                    for result in tool_results:
                        self.messages.append(
                            Message(
                                role="user",
                                content=f"工具结果: {result}",
                            )
                        )
                else:
                    # 没有工具调用，检查是否完成
                    if self._is_done(response.content):
                        logger.info(f"智能体在第 {turn_count} 轮后完成")
                        break

                    # 继续对话
                    self.messages.append(
                        Message(
                            role="user",
                            content="继续处理任务。"
                                    "如有需要请使用工具，或指示何时完成。",
                        )
                    )

            except Exception as e:
                logger.exception(f"第 {turn_count} 轮失败: {e}")
                raise AgentError(f"智能体执行在第 {turn_count} 轮失败: {e}") from e

        return {
            "success": True,
            "turns": turn_count,
            "total_tokens": total_tokens,
            "messages": self._messages_to_dicts(),
        }

    def _build_system_prompt(self, workspace_path: Path) -> str:
        """构建带上下文的系统提示词。"""
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
        """从 LLM 响应中提取工具调用。"""
        tool_calls = []

        # 查找工具调用块
        import re
        pattern = r'```tool\s*\n(.*?)\n```'
        matches = re.findall(pattern, content, re.DOTALL)

        for match in matches:
            try:
                tool_call = json.loads(match.strip())
                if "name" in tool_call and "arguments" in tool_call:
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                logger.warning(f"解析工具调用失败: {match}")

        return tool_calls

    async def _execute_tools(
        self,
        tool_calls: list[dict[str, Any]],
        workspace_path: Path,
    ) -> list[str]:
        """执行工具调用。"""
        results = []

        for call in tool_calls:
            tool_name = call.get("name")
            arguments = call.get("arguments", {})

            if tool_name in self.tools:
                try:
                    # 将工作空间添加到参数
                    arguments["_workspace"] = str(workspace_path)

                    result = await self.tools[tool_name](**arguments)
                    results.append(json.dumps({"success": True, "result": result}))
                except Exception as e:
                    results.append(json.dumps({"success": False, "error": str(e)}))
            else:
                results.append(json.dumps({"success": False, "error": f"未知工具: {tool_name}"}))

        return results

    def _is_done(self, content: str) -> bool:
        """检查智能体是否指示任务完成。"""
        # 查找完成标记
        done_markers = [
            "task completed",
            "finished",
            "done",
            "completed successfully",
        ]
        content_lower = content.lower()
        return any(marker in content_lower for marker in done_markers)

    def _messages_to_dicts(self) -> list[dict[str, str]]:
        """将消息转换为字典。"""
        return [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
        ]

    async def run_turn(self) -> str:
        """运行单轮并返回响应内容。"""
        response = await self.llm_client.complete(self.messages)
        self.messages.append(Message(role="assistant", content=response.content))
        return response.content
