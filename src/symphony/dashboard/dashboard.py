"""Terminal dashboard for Symphony.

Uses rich library to display real-time status of agents and LLM usage.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from symphony.config.config import Config
from symphony.orchestrator.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class Dashboard:
    """Terminal dashboard for Symphony.

    Displays:
    - Running agents with status
    - LLM token usage statistics
    - Retry queue
    - System status
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        config: Config,
        refresh_interval: float = 1.0,
    ) -> None:
        """Initialize dashboard.

        Args:
            orchestrator: Orchestrator instance to monitor
            config: Configuration instance
            refresh_interval: Refresh interval in seconds
        """
        self.orchestrator = orchestrator
        self.config = config
        self.refresh_interval = refresh_interval
        self.console = Console()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the dashboard display."""
        if self._running:
            return

        self._running = True
        logger.info("Starting dashboard")

        try:
            with Live(
                self._render(),
                console=self.console,
                refresh_per_second=1 / self.refresh_interval,
                screen=True,
            ) as live:
                while self._running:
                    live.update(self._render())
                    await asyncio.sleep(self.refresh_interval)
        except Exception as e:
            logger.exception(f"Dashboard error: {e}")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False
        logger.info("Dashboard stopped")

    def _render(self) -> Layout:
        """Render the dashboard layout."""
        layout = Layout()

        # Split into header, main, and footer
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )

        # Split main into left and right
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )

        # Render sections
        layout["header"].update(self._render_header())
        layout["left"].update(self._render_agents())
        layout["right"].update(self._render_stats())
        layout["footer"].update(self._render_footer())

        return layout

    def _render_header(self) -> Panel:
        """Render header section."""
        state = self.orchestrator.get_state()
        settings = self.config.settings

        llm_info = f"{settings.llm.provider.value}/{settings.llm.model}"
        project = settings.tracker.project_slug or "N/A"

        text = Text()
        text.append("🎼 ", style="bold magenta")
        text.append("Symphony", style="bold cyan")
        text.append(f" | LLM: {llm_info}", style="dim")
        text.append(f" | Project: {project}", style="dim")
        text.append(f" | Slots: {state.available_slots}/{state.max_concurrent_agents}", style="green")

        return Panel(text, border_style="cyan")

    def _render_agents(self) -> Panel:
        """Render running agents section."""
        state = self.orchestrator.get_state()

        if not state.running:
            return Panel(
                Text("No active agents", style="dim"),
                title="[bold blue]Running Agents[/bold blue]",
                border_style="blue",
            )

        table = Table(
            show_header=True,
            header_style="bold",
            expand=True,
            box=None,
        )
        table.add_column("Issue", style="cyan", width=15)
        table.add_column("State", style="yellow", width=12)
        table.add_column("Turn", justify="right", width=6)
        table.add_column("Tokens", justify="right", width=10)
        table.add_column("Runtime", justify="right", width=10)
        table.add_column("Status", style="green")

        for entry in state.running.values():
            issue = entry.issue
            session = entry.session_state

            runtime = session.get_runtime_seconds()
            runtime_str = f"{int(runtime // 60)}m {int(runtime % 60)}s"

            tokens = session.llm_usage.total_tokens
            tokens_str = f"{tokens:,}" if tokens > 0 else "-"

            status = session.last_event or "running"
            status_style = "green" if session.is_active() else "red"

            table.add_row(
                issue.identifier,
                issue.state[:12],
                str(session.turn_count),
                tokens_str,
                runtime_str,
                Text(status, style=status_style),
            )

        return Panel(
            table,
            title=f"[bold blue]Running Agents ({len(state.running)})[/bold blue]",
            border_style="blue",
        )

    def _render_stats(self) -> Panel:
        """Render statistics section."""
        state = self.orchestrator.get_state()
        totals = state.llm_totals

        # LLM Usage
        usage_table = Table(show_header=False, box=None, expand=True)
        usage_table.add_column("Metric", style="cyan")
        usage_table.add_column("Value", justify="right")

        usage_table.add_row("Prompt Tokens", f"{totals.prompt_tokens:,}")
        usage_table.add_row("Completion Tokens", f"{totals.completion_tokens:,}")
        usage_table.add_row("Total Tokens", f"{totals.total_tokens:,}")

        hours = int(totals.seconds_running // 3600)
        minutes = int((totals.seconds_running % 3600) // 60)
        usage_table.add_row("Runtime", f"{hours}h {minutes}m")

        # Queue info
        queue_table = Table(show_header=False, box=None, expand=True)
        queue_table.add_column("Queue", style="cyan")
        queue_table.add_column("Count", justify="right")

        queue_table.add_row("Running", str(len(state.running)))
        queue_table.add_row("Retrying", str(len(state.retry_attempts)))
        queue_table.add_row("Claimed", str(len(state.claimed)))
        queue_table.add_row("Completed", str(len(state.completed)))

        # Combine
        content = Group(
            Text("LLM Usage", style="bold yellow"),
            usage_table,
            Text(""),
            Text("Queue Status", style="bold yellow"),
            queue_table,
        )

        return Panel(content, title="[bold green]Statistics[/bold green]", border_style="green")

    def _render_footer(self) -> Panel:
        """Render footer section."""
        state = self.orchestrator.get_state()

        # Retry queue info
        retry_texts = []
        for entry in list(state.retry_attempts.values())[:3]:
            due = max(0, int(entry.due_in_seconds))
            retry_texts.append(f"{entry.identifier} in {due}s")

        text = Text()
        text.append(f"⏳ Next refresh: {int(self.refresh_interval)}s | ", style="dim")

        if retry_texts:
            text.append("Retrying: " + ", ".join(retry_texts), style="yellow")
        else:
            text.append("No retries queued", style="dim")

        return Panel(text, border_style="dim")

    async def run_in_background(self) -> None:
        """Run dashboard in background alongside orchestrator."""
        dashboard_task = asyncio.create_task(self.start())

        try:
            # Wait for orchestrator to stop
            while self.orchestrator._running:
                await asyncio.sleep(0.5)
        finally:
            self.stop()
            try:
                await asyncio.wait_for(dashboard_task, timeout=2.0)
            except asyncio.TimeoutError:
                dashboard_task.cancel()
