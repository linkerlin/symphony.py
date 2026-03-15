"""Core orchestrator for Symphony.

Manages polling, dispatch, retries, and reconciliation of agent runs.
Works with any LLM provider (OpenAI, Anthropic, DeepSeek, Gemini, etc.)
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
    """Raised when orchestrator operation fails."""

    pass


class Orchestrator:
    """Main orchestrator for Symphony.

    Responsibilities:
    - Poll Linear for candidate issues
    - Manage concurrent agent execution
    - Handle retries with exponential backoff
    - Reconcile issue states
    - Track metrics and expose state

    Works with any LLM provider configured in settings.
    """

    # Retry backoff constants
    CONTINUATION_RETRY_DELAY_MS = 1000  # 1 second for normal continuation
    FAILURE_RETRY_BASE_MS = 10000  # 10 seconds base for failure retry

    def __init__(
        self,
        config: Config,
        tracker: BaseTracker,
        workspace_manager: WorkspaceManager,
        prompt_builder: PromptBuilder,
        llm_client: LLMClient | None = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config: Configuration instance
            tracker: Issue tracker instance
            workspace_manager: Workspace manager instance
            prompt_builder: Prompt builder instance
            llm_client: Optional LLM client (created from config if not provided)
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
        """Add a callback for state change events.

        Args:
            callback: Function to call with (event_type, data)
        """
        self._callbacks.append(callback)

    def _notify(self, event_type: str, data: Any) -> None:
        """Notify all callbacks of an event."""
        for callback in self._callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.warning(f"Callback failed: {e}")

    async def start(self) -> None:
        """Start the orchestrator.

        Initializes state and starts the polling loop.
        """
        logger.info("Starting Symphony orchestrator")

        # Validate configuration
        try:
            self.config.validate()
        except ConfigError as e:
            raise OrchestratorError(f"Invalid configuration: {e}") from e

        # Initialize LLM client if not provided
        if self.llm_client is None:
            llm_config = self.config.get_llm_config()
            self.llm_client = LLMClient.from_config(llm_config)
            logger.info(
                f"Initialized LLM client: provider={llm_config.get('provider')}, "
                f"model={llm_config.get('model')}"
            )

        self._running = True

        # Clean up terminal workspaces
        await self._clean_terminal_workspaces()

        # Start polling loop
        self._poll_task = asyncio.create_task(self._poll_loop())

        logger.info("Orchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator.

        Cancels polling and waits for running agents.
        """
        logger.info("Stopping Symphony orchestrator")
        self._running = False

        # Cancel polling task
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # Cancel all running agents
        for issue_id, entry in list(self.state.running.items()):
            logger.info(f"Cancelling agent for issue {issue_id}")
            entry.task.cancel()

        # Wait for agents to finish
        if self.state.running:
            await asyncio.gather(
                *[entry.task for entry in self.state.running.values()],
                return_exceptions=True,
            )

        # Close LLM client
        if self.llm_client:
            await self.llm_client.close()

        logger.info("Orchestrator stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        logger.debug("Starting poll loop")

        # Initial tick immediately
        await self._tick()

        while self._running:
            try:
                # Wait for poll interval
                await asyncio.sleep(self.state.poll_interval_ms / 1000)

                if self._running:
                    await self._tick()

            except asyncio.CancelledError:
                logger.debug("Poll loop cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in poll loop: {e}")

    async def _tick(self) -> None:
        """Execute one poll/dispatch cycle."""
        logger.debug("Poll tick")

        # Update dynamic configuration
        await self._refresh_config()

        # Reconcile running issues
        await self._reconcile()

        # Validate configuration
        try:
            self.config.validate()
        except ConfigError as e:
            logger.error(f"Configuration invalid: {e}")
            return

        # Fetch and dispatch candidate issues
        await self._fetch_and_dispatch()

        # Notify state update
        self._notify("state_updated", self.state.to_snapshot())

    async def _refresh_config(self) -> None:
        """Refresh dynamic configuration."""
        settings = self.config.settings
        self.state.poll_interval_ms = settings.polling.interval_ms
        self.state.max_concurrent_agents = settings.agent.max_concurrent_agents
        self.state.max_retry_backoff_ms = settings.agent.max_retry_backoff_ms

    async def _reconcile(self) -> None:
        """Reconcile running issues with tracker state."""
        if not self.state.running:
            return

        issue_ids = list(self.state.running.keys())

        try:
            # Fetch current states
            refreshed = await self.tracker.fetch_issue_states_by_ids(issue_ids)
            refreshed_by_id = {issue.id: issue for issue in refreshed}

            settings = self.config.settings

            for issue_id in issue_ids:
                entry = self.state.running.get(issue_id)
                if not entry:
                    continue

                refreshed_issue = refreshed_by_id.get(issue_id)

                if not refreshed_issue:
                    # Issue no longer visible
                    logger.info(f"Issue {issue_id} no longer visible, stopping")
                    await self._stop_issue(issue_id, cleanup=False)
                    continue

                # Check if terminal
                if settings.is_state_terminal(refreshed_issue.state):
                    logger.info(
                        f"Issue {refreshed_issue.identifier} moved to terminal state "
                        f"{refreshed_issue.state}, stopping and cleaning up"
                    )
                    await self._stop_issue(issue_id, cleanup=True)
                    continue

                # Check if no longer active
                if not settings.is_state_active(refreshed_issue.state):
                    logger.info(
                        f"Issue {refreshed_issue.identifier} no longer active "
                        f"({refreshed_issue.state}), stopping"
                    )
                    await self._stop_issue(issue_id, cleanup=False)
                    continue

                # Update issue data
                entry.issue = refreshed_issue

        except Exception as e:
            logger.exception(f"Reconciliation failed: {e}")

    async def _fetch_and_dispatch(self) -> None:
        """Fetch candidate issues and dispatch agents."""
        if self.state.is_at_capacity:
            logger.debug("At capacity, skipping dispatch")
            return

        try:
            # Fetch candidate issues
            issues = await self.tracker.fetch_candidate_issues()
            logger.debug(f"Fetched {len(issues)} candidate issues")

            # Sort for dispatch priority
            sorted_issues = self._sort_issues(issues)

            # Dispatch while slots available
            for issue in sorted_issues:
                if self.state.is_at_capacity:
                    break

                if self._should_dispatch(issue):
                    await self._dispatch(issue)

        except Exception as e:
            logger.exception(f"Fetch and dispatch failed: {e}")

    def _sort_issues(self, issues: list[Issue]) -> list[Issue]:
        """Sort issues by dispatch priority.

        Priority:
        1. Priority (lower number = higher priority)
        2. Created at (older first)
        3. Identifier (lexicographic)

        Args:
            issues: List of issues to sort

        Returns:
            Sorted list of issues
        """

        def sort_key(issue: Issue) -> tuple:
            # Priority: lower is better, missing priority sorts last
            priority = issue.priority if issue.priority is not None else 999
            # Created at: older is better
            created = issue.created_at or datetime.max
            return (priority, created, issue.identifier)

        return sorted(issues, key=sort_key)

    def _should_dispatch(self, issue: Issue) -> bool:
        """Check if an issue should be dispatched.

        Args:
            issue: Issue to check

        Returns:
            True if issue should be dispatched
        """
        # Check if already claimed
        if self.state.is_issue_claimed(issue.id):
            return False

        # Check if already running
        if self.state.is_issue_running(issue.id):
            return False

        # Check concurrency limits
        settings = self.config.settings
        state_limit = settings.get_max_concurrent_for_state(issue.state)
        state_count = self.state.get_running_count_for_state(issue.state)
        if state_count >= state_limit:
            logger.debug(
                f"State {issue.state} at capacity ({state_count}/{state_limit})"
            )
            return False

        return True

    async def _dispatch(self, issue: Issue, attempt: int | None = None) -> None:
        """Dispatch an agent for an issue.

        Args:
            issue: Issue to dispatch
            attempt: Retry attempt number
        """
        logger.info(f"Dispatching agent for {issue.get_context_string()}")

        # Claim the issue
        self.state.claimed.add(issue.id)

        # Remove from retry queue if present
        if issue.id in self.state.retry_attempts:
            entry = self.state.retry_attempts.pop(issue.id)
            if entry.timer_handle:
                entry.timer_handle.cancel()

        # Create task
        task = asyncio.create_task(
            self._run_agent(issue, attempt),
            name=f"agent-{issue.identifier}",
        )

        # Add to running
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

        # Set up completion callback
        task.add_done_callback(
            lambda t, iid=issue.id: asyncio.create_task(
                self._handle_agent_completion(iid, t)
            )
        )

        self._notify("agent_dispatched", {"issue_id": issue.id, "attempt": attempt})

    async def _run_agent(self, issue: Issue, attempt: int | None) -> None:
        """Run agent for an issue.

        This is the actual agent execution coroutine.

        Args:
            issue: Issue to process
            attempt: Retry attempt number
        """
        logger.info(f"Running agent for {issue.get_context_string()}")

        # Create workspace
        workspace_path, created = await self.workspace_manager.create_for_issue(issue)
        logger.debug(f"Workspace: {workspace_path}, created: {created}")

        # Run before_run hook
        await self.workspace_manager.run_before_run_hook(workspace_path, issue)

        # Create agent with tools
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
            # Run agent
            settings = self.config.settings
            result = await agent.run(
                issue=issue,
                workspace_path=workspace_path,
                max_turns=settings.agent.max_turns,
                attempt=attempt,
            )

            # Update session state with results
            entry = self.state.running.get(issue.id)
            if entry:
                entry.session_state.turn_count = result.get("turns", 0)
                tokens = result.get("total_tokens", {})
                entry.session_state.add_usage(tokens)

            logger.info(
                f"Agent completed for {issue.identifier}: "
                f"{result.get('turns', 0)} turns, "
                f"tokens: {tokens}"
            )

        except AgentError as e:
            logger.error(f"Agent failed for {issue.identifier}: {e}")
            raise

        except asyncio.CancelledError:
            logger.info(f"Agent cancelled for {issue.identifier}")
            raise

        finally:
            # Run after_run hook (best effort)
            await self.workspace_manager.run_after_run_hook(workspace_path, issue)

    async def _handle_agent_completion(
        self, issue_id: str, task: asyncio.Task
    ) -> None:
        """Handle agent task completion.

        Args:
            issue_id: Issue ID
            task: Completed task
        """
        entry = self.state.running.pop(issue_id, None)
        if not entry:
            return

        # Update metrics
        runtime = entry.session_state.get_runtime_seconds()
        self.state.llm_totals.add_runtime(runtime)

        # Check result
        exception = task.exception()

        if exception is None:
            # Normal completion
            logger.info(f"Agent completed normally for {entry.issue.identifier}")
            self.state.completed.add(issue_id)

            # Schedule continuation check
            self._schedule_retry(
                issue_id,
                entry.issue.identifier,
                1,  # First continuation attempt
                is_continuation=True,
                worker_host=entry.worker_host,
                workspace_path=entry.workspace_path,
            )

        elif isinstance(exception, asyncio.CancelledError):
            # Cancelled
            logger.info(f"Agent cancelled for {entry.issue.identifier}")

        else:
            # Failed
            logger.error(
                f"Agent failed for {entry.issue.identifier}: {exception}"
            )

            # Schedule retry
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

        # Remove from claimed
        self.state.claimed.discard(issue_id)

        self._notify("agent_completed", {"issue_id": issue_id, "error": str(exception) if exception else None})

    async def _stop_issue(self, issue_id: str, cleanup: bool) -> None:
        """Stop a running issue.

        Args:
            issue_id: Issue ID to stop
            cleanup: Whether to clean up workspace
        """
        entry = self.state.running.get(issue_id)
        if not entry:
            return

        # Cancel task
        entry.task.cancel()

        # Clean up workspace if terminal
        if cleanup and entry.workspace_path:
            try:
                await self.workspace_manager.remove_workspace(
                    entry.issue.identifier,
                    run_hook=True,
                )
            except Exception as e:
                logger.warning(f"Failed to clean workspace: {e}")

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
        """Schedule a retry for an issue.

        Args:
            issue_id: Issue ID
            identifier: Issue identifier
            attempt: Attempt number
            is_continuation: Whether this is a continuation (not a failure retry)
            error: Error message for failure retries
            worker_host: Worker host preference
            workspace_path: Workspace path to reuse
        """
        # Calculate delay
        if is_continuation and attempt == 1:
            delay_ms = self.CONTINUATION_RETRY_DELAY_MS
        else:
            # Exponential backoff
            power = min(attempt - 1, 10)
            delay_ms = min(
                self.FAILURE_RETRY_BASE_MS * (2 ** power),
                self.state.max_retry_backoff_ms,
            )

        delay_seconds = delay_ms / 1000

        logger.info(
            f"Scheduling retry for {identifier} in {delay_seconds}s "
            f"(attempt {attempt})"
        )

        # Cancel existing retry if any
        existing = self.state.retry_attempts.get(issue_id)
        if existing and existing.timer_handle:
            existing.timer_handle.cancel()

        # Schedule new retry
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
        """Execute a scheduled retry.

        Args:
            issue_id: Issue ID to retry
        """
        entry = self.state.retry_attempts.pop(issue_id, None)
        if not entry:
            return

        logger.debug(f"Executing retry for {entry.identifier}")

        try:
            # Fetch fresh issue data
            issues = await self.tracker.fetch_candidate_issues()
            issue = next((i for i in issues if i.id == issue_id), None)

            if not issue:
                logger.info(f"Issue {entry.identifier} no longer eligible, dropping")
                self.state.claimed.discard(issue_id)
                return

            # Check if still eligible
            if not self._should_dispatch(issue):
                logger.debug(f"Issue {entry.identifier} not dispatchable, rescheduling")
                self._schedule_retry(
                    issue_id,
                    entry.identifier,
                    entry.attempt + 1,
                    error="No available slots",
                    worker_host=entry.worker_host,
                    workspace_path=entry.workspace_path,
                )
                return

            # Dispatch
            await self._dispatch(issue, attempt=entry.attempt)

        except Exception as e:
            logger.exception(f"Retry execution failed: {e}")
            self.state.claimed.discard(issue_id)

    async def _clean_terminal_workspaces(self) -> None:
        """Clean up workspaces for terminal issues."""
        try:
            settings = self.config.settings
            terminal_issues = await self.tracker.fetch_issues_by_states(
                list(settings.tracker.terminal_states)
            )
            identifiers = [issue.identifier for issue in terminal_issues]

            await self.workspace_manager.clean_terminal_workspaces(identifiers)

        except Exception as e:
            logger.warning(f"Failed to clean terminal workspaces: {e}")

    def get_state(self) -> OrchestratorState:
        """Get current orchestrator state."""
        return self.state

    def get_snapshot(self) -> dict[str, Any]:
        """Get state snapshot."""
        return self.state.to_snapshot()
