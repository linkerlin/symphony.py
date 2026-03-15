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

from symphony.cli_commands import doctor_command, init_command, validate_command
from symphony.config.config import Config, ConfigError
from symphony.dashboard.dashboard import Dashboard
from symphony.llm.client import LLMClient
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


@click.group()
@click.version_option(version="0.1.0", prog_name="symphony")
def cli():
    """Symphony - Agent Orchestration System (LLM Provider Agnostic).
    
    Quick start: symphony init
    
    Run: symphony run WORKFLOW.md
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
    """Run Symphony orchestrator.

    WORKFLOW_FILE is the path to your WORKFLOW.md configuration file.
    Defaults to ./WORKFLOW.md if not specified.

    Configuration priority:
    1. WORKFLOW.md settings
    2. Environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
    3. .env file
    4. Default values

    Supported LLM providers: openai, anthropic, deepseek, gemini, azure
    """
    setup_logging(logs_root=str(logs_root) if logs_root else None, verbose=verbose)

    logger.info("Starting Symphony", workflow_file=str(workflow_file))

    # Load .env file if specified or load defaults
    if env_file:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        logger.debug(f"Loaded env file: {env_file}")

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

    # Log LLM configuration (without API key)
    logger.info(
        "LLM Configuration",
        provider=settings.llm.provider,
        model=settings.llm.model,
        base_url=settings.llm.base_url,
    )

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

    # Create LLM client
    try:
        llm_config = config.get_llm_config()
        llm_client = LLMClient.from_config(llm_config)
    except Exception as e:
        logger.error(f"Failed to create LLM client: {e}")
        sys.exit(1)

    # Create orchestrator
    orchestrator = Orchestrator(
        config=config,
        tracker=tracker,
        workspace_manager=workspace_manager,
        prompt_builder=prompt_builder,
        llm_client=llm_client,
    )

    # Set up signal handlers
    loop = asyncio.get_event_loop()

    def signal_handler(sig: int) -> None:
        logger.info("Received signal", signal=sig)
        asyncio.create_task(orchestrator.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # Run orchestrator (with optional dashboard)
    try:
        if dashboard:
            # Run with dashboard
            dashboard_ui = Dashboard(
                orchestrator=orchestrator,
                config=config,
                refresh_interval=1.0,
            )
            loop.run_until_complete(orchestrator.start())
            loop.run_until_complete(dashboard_ui.run_in_background())
        else:
            # Run without dashboard
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


# Add subcommands
cli.add_command(init_command)
cli.add_command(validate_command)
cli.add_command(doctor_command)
cli.add_command(run_command)

# Backwards compatibility: main = run_command
main = cli


if __name__ == "__main__":
    cli()
