"""Symphony 的命令行界面。

提供运行 Symphony 的主要入口点。
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click
import structlog

from symphony.cli_commands import doctor_command, init_command, validate_command
from symphony.config.config import Config, ConfigError
from symphony.dashboard.dashboard import Dashboard
from symphony.llm.client import LLMClient
from symphony.orchestrator.orchestrator import Orchestrator, OrchestratorError
from symphony.prompts.builder import PromptBuilder
from symphony.trackers.linear import LinearTracker
from symphony.workspace.manager import WorkspaceManager

# 配置日志记录
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def setup_logging(logs_root: str | None = None, verbose: bool = False) -> None:
    """设置日志记录配置。

    参数:
        logs_root: 日志文件的存放目录
        verbose: 启用详细日志记录
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@click.group()
@click.version_option(version="0.1.0", prog_name="symphony")
def cli():
    """Symphony - 智能体编排系统（支持多种 LLM 提供商）。
    
    快速开始: symphony init
    
    运行: symphony run WORKFLOW.md
    """
    pass


@cli.command(name="run")
@click.argument(
    "workflow_file",
    type=click.Path(exists=True, path_type=Path),
    default=Path("WORKFLOW.md"),
)
@click.option(
    "--logs-root",
    type=click.Path(path_type=Path),
    help="Root directory for log files",
)
@click.option(
    "--port",
    type=int,
    help="HTTP API server port (overrides config)",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose logging",
)
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    help="Path to .env file (default: .env in workflow directory)",
)
@click.option(
    "--dashboard/--no-dashboard",
    default=False,
    help="Enable terminal dashboard display",
)
def run_command(
    workflow_file: Path,
    logs_root: Path | None,
    port: int | None,
    verbose: bool,
    env_file: Path | None,
    dashboard: bool,
) -> None:
    """运行 Symphony 编排器。

    WORKFLOW_FILE 是指向您的 WORKFLOW.md 配置文件的路径。
    如果未指定，默认为 ./WORKFLOW.md。

    配置优先级:
    1. WORKFLOW.md 设置
    2. 环境变量 (OPENAI_API_KEY, ANTHROPIC_API_KEY, 等)
    3. .env 文件
    4. 默认值

    支持的 LLM 提供商: openai, anthropic, deepseek, gemini, azure
    """
    setup_logging(logs_root=str(logs_root) if logs_root else None, verbose=verbose)

    logger.info("Starting Symphony", workflow_file=str(workflow_file))

    # 如果指定了 .env 文件，则加载它，否则加载默认值
    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        logger.debug(f"Loaded env file: {env_file}")

    # 加载配置
    try:
        config = Config.from_file(workflow_file)
        Config.set_instance(config)
    except ConfigError as e:
        logger.error("Configuration error", error=str(e))
        sys.exit(1)

    settings = config.settings

    # 如果指定了端口，则覆盖配置中的端口
    if port is not None:
        settings.server.port = port

    # 记录 LLM 配置（不包含 API 密钥）
    logger.info(
        "LLM Configuration",
        provider=settings.llm.provider,
        model=settings.llm.model,
        base_url=settings.llm.base_url,
    )

    # 创建追踪器
    if settings.tracker.kind == "linear":
        if not settings.tracker.api_key:
            logger.error("Linear API key not configured")
            sys.exit(1)
        if not settings.tracker.project_slug:
            logger.error("Linear project slug not configured")
            sys.exit(1)

        tracker = LinearTracker(
            api_key=settings.tracker.api_key,
            project_slug=settings.tracker.project_slug,
            endpoint=settings.tracker.endpoint,
            active_states=settings.tracker.active_states,
            terminal_states=settings.tracker.terminal_states,
            assignee=settings.tracker.assignee,
        )
    else:
        logger.error(f"Unsupported tracker kind: {settings.tracker.kind}")
        sys.exit(1)

    # 创建工作区管理器
    workspace_manager = WorkspaceManager(
        root=settings.workspace.root,
        hooks={
            "after_create": settings.hooks.after_create,
            "before_run": settings.hooks.before_run,
            "after_run": settings.hooks.after_run,
            "before_remove": settings.hooks.before_remove,
        },
        hook_timeout_ms=settings.hooks.timeout_ms,
    )

    # 创建提示词构建器
    prompt_builder = PromptBuilder.from_workflow(workflow_file)

    # 创建 LLM 客户端
    try:
        llm_config = config.get_llm_config()
        llm_client = LLMClient.from_config(llm_config)
    except Exception as e:
        logger.error(f"Failed to create LLM client: {e}")
        sys.exit(1)

    # 创建编排器
    orchestrator = Orchestrator(
        config=config,
        tracker=tracker,
        workspace_manager=workspace_manager,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
    )

    # 设置信号处理器
    loop = asyncio.get_event_loop()

    def signal_handler(sig: int) -> None:
        logger.info("Received signal", signal=sig)
        asyncio.create_task(orchestrator.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # 运行编排器（可选择是否启用仪表板）
    try:
        if dashboard:
            # 使用仪表板运行
            dashboard_ui = Dashboard(
                orchestrator=orchestrator,
                config=config,
                refresh_interval=1.0,
            )
            loop.run_until_complete(orchestrator.start())
            loop.run_until_complete(dashboard_ui.run_in_background())
        else:
            # 不使用仪表板运行
            loop.run_until_complete(orchestrator.start())
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except OrchestratorError as e:
        logger.error("Orchestrator error", error=str(e))
        sys.exit(1)
    finally:
        loop.run_until_complete(orchestrator.stop())
        loop.run_until_complete(tracker.close())

    logger.info("Symphony stopped")


# 添加子命令
cli.add_command(init_command)
cli.add_command(validate_command)
cli.add_command(doctor_command)
cli.add_command(run_command)

# 向后兼容: main = run_command
main = cli


if __name__ == "__main__":
    cli()
