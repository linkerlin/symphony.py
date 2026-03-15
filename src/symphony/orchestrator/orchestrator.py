"""Symphony 的核心编排器。

管理智能体运行的轮询、分发、重试和协调。
适用于任何 LLM 提供商（OpenAI、Anthropic、DeepSeek、Gemini 等）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from symphony.agents.agent import AgentError, SymphonyAgent
from symphony.config.config import Config, ConfigError
from symphony.llm.client import LLMClient
from symphony.models.issue import Issue
from symphony.models.session import SessionState, SessionStatus
from symphony.orchestrator.state import OrchestratorState, RetryEntry, RunningEntry
from symphony.prompts.builder import PromptBuilder
from symphony.trackers.base import BaseTracker
from symphony.workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """当编排器操作失败时抛出。"""

    pass


class Orchestrator:
    """Symphony 的主编排器。

    职责：
    - 轮询 Linear 获取候选问题
    - 管理并发智能体执行
    - 处理指数退避重试
    - 协调问题状态
    - 跟踪指标并暴露状态

    适用于设置中配置的任何 LLM 提供商。
    """

    # 重试退避常量
    CONTINUATION_RETRY_DELAY_MS = 1000  # 正常继续操作的延迟为 1 秒
    FAILURE_RETRY_BASE_MS = 10000  # 失败重试的基础延迟为 10 秒

    def __init__(
        self,
        config: Config,
        tracker: BaseTracker,
        workspace_manager: WorkspaceManager,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient | None = None,
    ) -> None:
        """初始化编排器。

        参数：
            config: 配置实例
            tracker: 问题跟踪器实例
            workspace_manager: 工作空间管理器实例
            prompt_builder: 提示词构建器实例
            llm_client: 可选的 LLM 客户端（如果未提供则从配置创建）
        """
        self.config = config
        self.tracker = tracker
        self.workspace_manager = workspace_manager
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client

        self.state = OrchestratorState()
        self._running = False
        self._poll_task: asyncio.Task | None = None
        self._callbacks: list[Callable[[str, Any], None]] = []

    def add_callback(self, callback: Callable[[str, Any], None]) -> None:
        """添加状态变更事件的回调函数。

        参数：
            callback: 调用时传入 (event_type, data) 的函数
        """
        self._callbacks.append(callback)

    def _notify(self, event_type: str, data: Any) -> None:
        """通知所有回调函数有事件发生。"""
        for callback in self._callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.warning(f"回调失败: {e}")

    async def start(self) -> None:
        """启动编排器。

        初始化状态并启动轮询循环。
        """
        logger.info("启动 Symphony 编排器")

        # 验证配置
        try:
            self.config.validate()
        except ConfigError as e:
            raise OrchestratorError(f"配置无效: {e}") from e

        # 如果未提供则初始化 LLM 客户端
        if self.llm_client is None:
            llm_config = self.config.get_llm_config()
            self.llm_client = LLMClient.from_config(llm_config)
            logger.info(
                f"已初始化 LLM 客户端: 提供商={llm_config.get('provider')}, "
                f"模型={llm_config.get('model')}"
            )

        self._running = True

        # 清理终端状态工作空间
        await self._clean_terminal_workspaces()

        # 启动轮询循环
        self._poll_task = asyncio.create_task(self._poll_loop())

        logger.info("编排器已启动")

    async def stop(self) -> None:
        """停止编排器。

        取消轮询并等待运行中的智能体。
        """
        logger.info("停止 Symphony 编排器")
        self._running = False

        # 取消轮询任务
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # 取消所有运行中的智能体
        for issue_id, entry in list(self.state.running.items()):
            logger.info(f"正在取消问题 {issue_id} 的智能体")
            entry.task.cancel()

        # 等待智能体完成
        if self.state.running:
            await asyncio.gather(
                *[entry.task for entry in self.state.running.values()],
                return_exceptions=True,
            )

        # 关闭 LLM 客户端
        if self.llm_client:
            await self.llm_client.close()

        logger.info("编排器已停止")

    async def _poll_loop(self) -> None:
        """主轮询循环。"""
        logger.debug("启动轮询循环")

        # 立即执行首次 tick
        await self._tick()

        while self._running:
            try:
                # 等待轮询间隔
                await asyncio.sleep(self.state.poll_interval_ms / 1000)

                if self._running:
                    await self._tick()

            except asyncio.CancelledError:
                logger.debug("轮询循环已取消")
                break
            except Exception as e:
                logger.exception(f"轮询循环出错: {e}")

    async def _tick(self) -> None:
        """执行一次轮询/分发周期。"""
        logger.debug("轮询 tick")

        # 更新动态配置
        await self._refresh_config()

        # 协调运行中的问题
        await self._reconcile()

        # 验证配置
        try:
            self.config.validate()
        except ConfigError as e:
            logger.error(f"配置无效: {e}")
            return

        # 获取并分发候选问题
        await self._fetch_and_dispatch()

        # 通知状态更新
        self._notify("state_updated", self.state.to_snapshot())

    async def _refresh_config(self) -> None:
        """刷新动态配置。"""
        settings = self.config.settings
        self.state.poll_interval_ms = settings.polling.interval_ms
        self.state.max_concurrent_agents = settings.agent.max_concurrent_agents
        self.state.max_retry_backoff_ms = settings.agent.max_retry_backoff_ms

    async def _reconcile(self) -> None:
        """将运行中的问题与跟踪器状态进行协调。"""
        if not self.state.running:
            return

        issue_ids = list(self.state.running.keys())

        try:
            # 获取当前状态
            refreshed = await self.tracker.fetch_issue_states_by_ids(issue_ids)
            refreshed_by_id = {issue.id: issue for issue in refreshed}

            settings = self.config.settings

            for issue_id in issue_ids:
                entry = self.state.running.get(issue_id)
                if not entry:
                    continue

                refreshed_issue = refreshed_by_id.get(issue_id)

                if not refreshed_issue:
                    # 问题不再可见
                    logger.info(f"问题 {issue_id} 不再可见，停止")
                    await self._stop_issue(issue_id, cleanup=False)
                    continue

                # 检查是否为终端状态
                if settings.is_state_terminal(refreshed_issue.state):
                    logger.info(
                        f"问题 {refreshed_issue.identifier} 已进入终端状态 "
                        f"{refreshed_issue.state}，停止并清理"
                    )
                    await self._stop_issue(issue_id, cleanup=True)
                    continue

                # 检查是否不再活跃
                if not settings.is_state_active(refreshed_issue.state):
                    logger.info(
                        f"问题 {refreshed_issue.identifier} 不再活跃 "
                        f"({refreshed_issue.state})，停止"
                    )
                    await self._stop_issue(issue_id, cleanup=False)
                    continue

                # 更新问题数据
                entry.issue = refreshed_issue

        except Exception as e:
            logger.exception(f"协调失败: {e}")

    async def _fetch_and_dispatch(self) -> None:
        """获取候选问题并分发智能体。"""
        if self.state.is_at_capacity:
            logger.debug("已达容量上限，跳过分发")
            return

        try:
            # 获取候选问题
            issues = await self.tracker.fetch_candidate_issues()
            logger.debug(f"获取到 {len(issues)} 个候选问题")

            # 按分发优先级排序
            sorted_issues = self._sort_issues(issues)

            # 有空闲槽位时分发
            for issue in sorted_issues:
                if self.state.is_at_capacity:
                    break

                if self._should_dispatch(issue):
                    await self._dispatch(issue)

        except Exception as e:
            logger.exception(f"获取和分发失败: {e}")

    def _sort_issues(self, issues: list[Issue]) -> list[Issue]:
        """按分发优先级排序问题。

        优先级：
        1. 优先级（数字越小优先级越高）
        2. 创建时间（越早越优先）
        3. 标识符（字典序）

        参数：
            issues: 要排序的问题列表

        返回：
            排序后的问题列表
        """

        def sort_key(issue: Issue) -> tuple:
            # 优先级：越小越好，无优先级排最后
            priority = issue.priority if issue.priority is not None else 999
            # 创建时间：越早越好
            created = issue.created_at or datetime.max
            return (priority, created, issue.identifier)

        return sorted(issues, key=sort_key)

    def _should_dispatch(self, issue: Issue) -> bool:
        """检查是否应该分发问题。

        参数：
            issue: 要检查的问题

        返回：
            如果应该分发则返回 True
        """
        # 检查是否已被认领
        if self.state.is_issue_claimed(issue.id):
            return False

        # 检查是否已在运行
        if self.state.is_issue_running(issue.id):
            return False

        # 检查并发限制
        settings = self.config.settings
        state_limit = settings.get_max_concurrent_for_state(issue.state)
        state_count = self.state.get_running_count_for_state(issue.state)
        if state_count >= state_limit:
            logger.debug(
                f"状态 {issue.state} 已达容量上限 ({state_count}/{state_limit})"
            )
            return False

        return True

    async def _dispatch(self, issue: Issue, attempt: int | None = None) -> None:
        """为问题分发智能体。

        参数：
            issue: 要分发的问题
            attempt: 重试次数
        """
        logger.info(f"正在为 {issue.get_context_string()} 分发智能体")

        # 认领问题
        self.state.claimed.add(issue.id)

        # 如果存在则从重试队列中移除
        if issue.id in self.state.retry_attempts:
            entry = self.state.retry_attempts.pop(issue.id)
            if entry.timer_handle:
                entry.timer_handle.cancel()

        # 创建任务
        task = asyncio.create_task(
            self._run_agent(issue, attempt),
            name=f"agent-{issue.identifier}",
        )

        # 添加到运行中
        session_state = SessionState(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            llm_model=self.config.settings.llm.model,
        )
        self.state.running[issue.id] = RunningEntry(
            task=task,
            issue=issue,
            session_state=session_state,
            retry_attempt=attempt or 0,
        )

        # 设置完成回调
        task.add_done_callback(
            lambda t, iid=issue.id: asyncio.create_task(
                self._handle_agent_completion(iid, t)
            )
        )

        self._notify("agent_dispatched", {"issue_id": issue.id, "attempt": attempt})

    async def _run_agent(self, issue: Issue, attempt: int | None) -> None:
        """为问题运行智能体。

        这是实际的智能体执行协程。

        参数：
            issue: 要处理的问题
            attempt: 重试次数
        """
        logger.info(f"正在为 {issue.get_context_string()} 运行智能体")

        # 创建工作空间
        workspace_path, created = await self.workspace_manager.create_for_issue(issue)
        logger.debug(f"工作空间: {workspace_path}, 已创建: {created}")

        # 运行 before_run 钩子
        await self.workspace_manager.run_before_run_hook(workspace_path, issue)

        # 创建带工具的智能体
        from symphony.agents.tools import (
            add_comment,
            execute_command,
            get_issue,
            linear_graphql,
            read_file,
            update_issue_state,
            write_file,
        )

        tools = {
            "read_file": read_file,
            "write_file": write_file,
            "execute_command": execute_command,
            "linear_graphql": linear_graphql,
            "add_comment": add_comment,
            "update_issue_state": update_issue_state,
            "get_issue": get_issue,
        }

        agent = SymphonyAgent(
            llm_client=self.llm_client,
            prompt_builder=self.prompt_builder,
            tools=tools,
        )

        try:
            # 运行智能体
            settings = self.config.settings
            result = await agent.run(
                issue=issue,
                workspace_path=workspace_path,
                max_turns=settings.agent.max_turns,
                attempt=attempt,
            )

            # 用结果更新会话状态
            entry = self.state.running.get(issue.id)
            if entry:
                entry.session_state.turn_count = result.get("turns", 0)
                tokens = result.get("total_tokens", {})
                entry.session_state.add_usage(tokens)

            logger.info(
                f"智能体已完成 {issue.identifier}: "
                f"{result.get('turns', 0)} 轮次, "
                f"令牌数: {tokens}"
            )

        except AgentError as e:
            logger.error(f"智能体 {issue.identifier} 失败: {e}")
            raise

        except asyncio.CancelledError:
            logger.info(f"智能体 {issue.identifier} 已取消")
            raise

        finally:
            # 运行 after_run 钩子（尽力而为）
            await self.workspace_manager.run_after_run_hook(workspace_path, issue)

    async def _handle_agent_completion(
        self, issue_id: str, task: asyncio.Task
    ) -> None:
        """处理智能体任务完成。

        参数：
            issue_id: 问题 ID
            task: 已完成的任务
        """
        entry = self.state.running.pop(issue_id, None)
        if not entry:
            return

        # 更新指标
        runtime = entry.session_state.get_runtime_seconds()
        self.state.llm_totals.add_runtime(runtime)

        # 检查结果
        exception = task.exception()

        if exception is None:
            # 正常完成
            logger.info(f"智能体正常完成 {entry.issue.identifier}")
            self.state.completed.add(issue_id)

            # 安排继续检查
            self._schedule_retry(
                issue_id,
                entry.issue.identifier,
                1,  # 首次继续尝试
                is_continuation=True,
                worker_host=entry.worker_host,
                workspace_path=entry.workspace_path,
            )

        elif isinstance(exception, asyncio.CancelledError):
            # 已取消
            logger.info(f"智能体 {entry.issue.identifier} 已取消")

        else:
            # 失败
            logger.error(
                f"智能体 {entry.issue.identifier} 失败: {exception}"
            )

            # 安排重试
            next_attempt = (entry.retry_attempt or 0) + 1
            self._schedule_retry(
                issue_id,
                entry.issue.identifier,
                next_attempt,
                is_continuation=False,
                error=str(exception),
                worker_host=entry.worker_host,
                workspace_path=entry.workspace_path,
            )

        # 从已认领中移除
        self.state.claimed.discard(issue_id)

        self._notify("agent_completed", {"issue_id": issue_id, "error": str(exception) if exception else None})

    async def _stop_issue(self, issue_id: str, cleanup: bool) -> None:
        """停止运行中的问题。

        参数：
            issue_id: 要停止的问题 ID
            cleanup: 是否清理工作空间
        """
        entry = self.state.running.get(issue_id)
        if not entry:
            return

        # 取消任务
        entry.task.cancel()

        # 如果是终端状态则清理工作空间
        if cleanup and entry.workspace_path:
            try:
                await self.workspace_manager.remove_workspace(
                    entry.issue.identifier,
                    run_hook=True,
                )
            except Exception as e:
                logger.warning(f"清理工作空间失败: {e}")

    def _schedule_retry(
        self,
        issue_id: str,
        identifier: str,
        attempt: int,
        is_continuation: bool = False,
        error: str | None = None,
        worker_host: str | None = None,
        workspace_path: str | None = None,
    ) -> None:
        """为问题安排重试。

        参数：
            issue_id: 问题 ID
            identifier: 问题标识符
            attempt: 尝试次数
            is_continuation: 这是否是继续操作（非失败重试）
            error: 失败重试的错误信息
            worker_host: 工作节点主机偏好
            workspace_path: 要复用的工作空间路径
        """
        # 计算延迟
        if is_continuation and attempt == 1:
            delay_ms = self.CONTINUATION_RETRY_DELAY_MS
        else:
            # 指数退避
            power = min(attempt - 1, 10)
            delay_ms = min(
                self.FAILURE_RETRY_BASE_MS * (2 ** power),
                self.state.max_retry_backoff_ms,
            )

        delay_seconds = delay_ms / 1000

        logger.info(
            f"安排在 {delay_seconds} 秒后重试 {identifier} "
            f"(第 {attempt} 次尝试)"
        )

        # 取消现有的重试（如果有）
        existing = self.state.retry_attempts.get(issue_id)
        if existing and existing.timer_handle:
            existing.timer_handle.cancel()

        # 安排新的重试
        now = datetime.utcnow()
        due_at = now + timedelta(milliseconds=delay_ms)

        timer_handle = asyncio.get_event_loop().call_later(
            delay_seconds,
            lambda: asyncio.create_task(
                self._execute_retry(issue_id)
            ),
        )

        self.state.retry_attempts[issue_id] = RetryEntry(
            issue_id=issue_id,
            identifier=identifier,
            attempt=attempt,
            scheduled_at=now,
            due_at=due_at,
            error=error,
            worker_host=worker_host,
            workspace_path=workspace_path,
            timer_handle=timer_handle,
        )

        self.state.claimed.add(issue_id)

    async def _execute_retry(self, issue_id: str) -> None:
        """执行安排的重试。

        参数：
            issue_id: 要重试的问题 ID
        """
        entry = self.state.retry_attempts.pop(issue_id, None)
        if not entry:
            return

        logger.debug(f"执行 {entry.identifier} 的重试")

        try:
            # 获取最新问题数据
            issues = await self.tracker.fetch_candidate_issues()
            issue = next((i for i in issues if i.id == issue_id), None)

            if not issue:
                logger.info(f"问题 {entry.identifier} 不再符合条件，放弃")
                self.state.claimed.discard(issue_id)
                return

            # 检查是否仍然符合条件
            if not self._should_dispatch(issue):
                logger.debug(f"问题 {entry.identifier} 无法分发，重新安排")
                self._schedule_retry(
                    issue_id,
                    entry.identifier,
                    entry.attempt + 1,
                    error="无可用槽位",
                    worker_host=entry.worker_host,
                    workspace_path=entry.workspace_path,
                )
                return

            # 分发
            await self._dispatch(issue, attempt=entry.attempt)

        except Exception as e:
            logger.exception(f"重试执行失败: {e}")
            self.state.claimed.discard(issue_id)

    async def _clean_terminal_workspaces(self) -> None:
        """清理终端状态问题的工作空间。"""
        try:
            settings = self.config.settings
            terminal_issues = await self.tracker.fetch_issues_by_states(
                list(settings.tracker.terminal_states)
            )
            identifiers = [issue.identifier for issue in terminal_issues]

            await self.workspace_manager.clean_terminal_workspaces(identifiers)

        except Exception as e:
            logger.warning(f"清理终端工作空间失败: {e}")

    def get_state(self) -> OrchestratorState:
        """获取当前编排器状态。"""
        return self.state

    def get_snapshot(self) -> dict[str, Any]:
        """获取状态快照。"""
        return self.state.to_snapshot()
