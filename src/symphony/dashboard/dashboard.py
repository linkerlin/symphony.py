"""Symphony 终端仪表板。

使用 rich 库显示智能体和 LLM 使用情况的实时状态。
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
    """Symphony 终端仪表板。

    显示内容：
    - 运行中的智能体及其状态
    - LLM 令牌使用统计
    - 重试队列
    - 系统状态
    """

    def __init__(
        self,
        orchestrator: Orchestrator,
        config: Config,
        refresh_interval: float = 1.0,
    ) -> None:
        """初始化仪表板。

        参数：
            orchestrator: 要监控的协调器实例
            config: 配置实例
            refresh_interval: 刷新间隔（秒）
        """
        self.orchestrator = orchestrator
        self.config = config
        self.refresh_interval = refresh_interval
        self.console = Console()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动仪表板显示。"""
        if self._running:
            return

        self._running = True
        logger.info("正在启动仪表板")

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
            logger.exception(f"仪表板错误: {e}")
        finally:
            self._running = False

    def stop(self) -> None:
        """停止仪表板。"""
        self._running = False
        logger.info("仪表板已停止")

    def _render(self) -> Layout:
        """渲染仪表板布局。"""
        layout = Layout()

        # 分割为页眉、主体和页脚
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )

        # 将主体分割为左右两部分
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )

        # 渲染各个区域
        layout["header"].update(self._render_header())
        layout["left"].update(self._render_agents())
        layout["right"].update(self._render_stats())
        layout["footer"].update(self._render_footer())

        return layout

    def _render_header(self) -> Panel:
        """渲染页眉区域。"""
        state = self.orchestrator.get_state()
        settings = self.config.settings

        llm_info = f"{settings.llm.provider.value}/{settings.llm.model}"
        project = settings.tracker.project_slug or "N/A"

        text = Text()
        text.append("🎼 ", style="bold magenta")
        text.append("Symphony", style="bold cyan")
        text.append(f" | LLM: {llm_info}", style="dim")
        text.append(f" | 项目: {project}", style="dim")
        text.append(f" | 槽位: {state.available_slots}/{state.max_concurrent_agents}", style="green")

        return Panel(text, border_style="cyan")

    def _render_agents(self) -> Panel:
        """渲染运行中的智能体区域。"""
        state = self.orchestrator.get_state()

        if not state.running:
            return Panel(
                Text("无活动智能体", style="dim"),
                title="[bold blue]运行中的智能体[/bold blue]",
                border_style="blue",
            )

        table = Table(
            show_header=True,
            header_style="bold",
            expand=True,
            box=None,
        )
        table.add_column("事项", style="cyan", width=15)
        table.add_column("状态", style="yellow", width=12)
        table.add_column("轮次", justify="right", width=6)
        table.add_column("令牌数", justify="right", width=10)
        table.add_column("运行时间", justify="right", width=10)
        table.add_column("状态信息", style="green")

        for entry in state.running.values():
            issue = entry.issue
            session = entry.session_state

            runtime = session.get_runtime_seconds()
            runtime_str = f"{int(runtime // 60)}分 {int(runtime % 60)}秒"

            tokens = session.llm_usage.total_tokens
            tokens_str = f"{tokens:,}" if tokens > 0 else "-"

            status = session.last_event or "运行中"
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
            title=f"[bold blue]运行中的智能体 ({len(state.running)})[/bold blue]",
            border_style="blue",
        )

    def _render_stats(self) -> Panel:
        """渲染统计信息区域。"""
        state = self.orchestrator.get_state()
        totals = state.llm_totals

        # LLM 使用情况
        usage_table = Table(show_header=False, box=None, expand=True)
        usage_table.add_column("指标", style="cyan")
        usage_table.add_column("数值", justify="right")

        usage_table.add_row("提示令牌数", f"{totals.prompt_tokens:,}")
        usage_table.add_row("补全令牌数", f"{totals.completion_tokens:,}")
        usage_table.add_row("总令牌数", f"{totals.total_tokens:,}")

        hours = int(totals.seconds_running // 3600)
        minutes = int((totals.seconds_running % 3600) // 60)
        usage_table.add_row("运行时间", f"{hours}小时 {minutes}分")

        # 队列信息
        queue_table = Table(show_header=False, box=None, expand=True)
        queue_table.add_column("队列", style="cyan")
        queue_table.add_column("数量", justify="right")

        queue_table.add_row("运行中", str(len(state.running)))
        queue_table.add_row("重试中", str(len(state.retry_attempts)))
        queue_table.add_row("已认领", str(len(state.claimed)))
        queue_table.add_row("已完成", str(len(state.completed)))

        # 组合显示
        content = Group(
            Text("LLM 使用情况", style="bold yellow"),
            usage_table,
            Text(""),
            Text("队列状态", style="bold yellow"),
            queue_table,
        )

        return Panel(content, title="[bold green]统计信息[/bold green]", border_style="green")

    def _render_footer(self) -> Panel:
        """渲染页脚区域。"""
        state = self.orchestrator.get_state()

        # 重试队列信息
        retry_texts = []
        for entry in list(state.retry_attempts.values())[:3]:
            due = max(0, int(entry.due_in_seconds))
            retry_texts.append(f"{entry.identifier} 将在 {due} 秒后重试")

        text = Text()
        text.append(f"⏳ 下次刷新: {int(self.refresh_interval)}秒 | ", style="dim")

        if retry_texts:
            text.append("重试队列: " + ", ".join(retry_texts), style="yellow")
        else:
            text.append("无重试队列", style="dim")

        return Panel(text, border_style="dim")

    async def run_in_background(self) -> None:
        """在后台与协调器一起运行仪表板。"""
        dashboard_task = asyncio.create_task(self.start())

        try:
            # 等待协调器停止
            while self.orchestrator._running:
                await asyncio.sleep(0.5)
        finally:
            self.stop()
            try:
                await asyncio.wait_for(dashboard_task, timeout=2.0)
            except asyncio.TimeoutError:
                dashboard_task.cancel()
