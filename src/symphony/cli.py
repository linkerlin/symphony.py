"""Command-line interface for Symphony.

Provides the main entry point for running Symphony.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click
import structlog

from symphony.config.config import Config, ConfigError
from symphony.orchestrator.orchestrator import Orchestrator, OrchestratorError
from symphony.prompts.builder import PromptBuilder
from symphony.trackers.linear import LinearTracker
from symphony.workspace.manager import WorkspaceManager

# Configure logging
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
    """Set up logging configuration.

    Args:
        logs_root: Directory for log files
        verbose: Enable verbose logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@click.command()
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
def main(
    workflow_file: Path,
    logs_root: Path | None,
    port: int | None,
    verbose: bool,
) -> None:
    """Symphony - Agent Orchestration System.

    WORKFLOW_FILE is the path to your WORKFLOW.md configuration file.
    Defaults to ./WORKFLOW.md if not specified.
    """
    setup_logging(logs_root=str(logs_root) if logs_root else None, verbose=verbose)

    logger.info("Starting Symphony", workflow_file=str(workflow_file))

    # Load configuration
    try:
        config = Config.from_file(workflow_file)
        Config.set_instance(config)
    except ConfigError as e:
        logger.error("Configuration error", error=str(e))
        sys.exit(1)

    settings = config.settings

    # Override port if specified
    if port is not None:
        settings.server.port = port

    # Create tracker
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

    # Create workspace manager
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

    # Create prompt builder
    prompt_builder = PromptBuilder.from_workflow(workflow_file)

    # Create orchestrator
    orchestrator = Orchestrator(
        config=config,
        tracker=tracker,
        workspace_manager=workspace_manager,
        prompt_builder=prompt_builder,
        agent_factory=lambda: None,  # TODO: Implement agent factory
    )

    # Set up signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler(sig: int) -> None:
        logger.info("Received signal", signal=sig)
        asyncio.create_task(orchestrator.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # Run orchestrator
    try:
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


if __name__ == "__main__":
    main()
