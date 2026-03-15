"""Configuration loading and management for Symphony.

Provides functionality to load configuration from WORKFLOW.md files,
environment variables, and .env files.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from symphony.config.schema import SymphonyConfig
from symphony.workflow.loader import WorkflowLoader

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class Config:
    """Configuration manager for Symphony.

    This class manages loading and accessing Symphony configuration.
    It supports loading from:
    1. .env files (automatically loaded from current/workflow directory)
    2. Environment variables
    3. WORKFLOW.md files with YAML front matter

    Configuration precedence (highest to lowest):
    1. Explicit values in WORKFLOW.md
    2. Environment variables
    3. .env file values
    4. Default values

    Example:
        >>> # .env file
        >>> OPENAI_API_KEY=sk-...
        >>> OPENAI_BASE_URL=https://api.openai.com/v1
        >>> OPENAI_MODEL=gpt-4
        >>>
        >>> # Python
        >>> config = Config.from_file("WORKFLOW.md")
        >>> print(config.settings.llm.api_key)  # From .env
        >>> config.validate()  # Raises ConfigError if invalid
    """

    _instance: Config | None = None
    _settings: SymphonyConfig | None = None
    _workflow_path: Path | None = None

    def __init__(self, settings: SymphonyConfig, workflow_path: Path | None = None) -> None:
        """Initialize configuration with settings.

        Args:
            settings: Validated configuration object
            workflow_path: Path to the workflow file (for reloads)
        """
        self._settings = settings
        self._workflow_path = workflow_path

    @classmethod
    def load_env_files(cls, workflow_path: str | Path | None = None) -> None:
        """Load .env files from standard locations.

        Loads from (in order):
        1. Directory containing workflow file
        2. Current working directory
        3. User home directory (~/.symphony.env)

        Args:
            workflow_path: Optional path to workflow file to find its directory
        """
        loaded = []

        # 1. Workflow directory
        if workflow_path:
            workflow_dir = Path(workflow_path).parent
            env_file = workflow_dir / ".env"
            if env_file.exists():
                load_dotenv(env_file, override=False)
                loaded.append(str(env_file))

        # 2. Current working directory
        cwd_env = Path.cwd() / ".env"
        if cwd_env.exists() and cwd_env not in [Path(p) for p in loaded]:
            load_dotenv(cwd_env, override=False)
            loaded.append(str(cwd_env))

        # 3. User home directory
        home_env = Path.home() / ".symphony.env"
        if home_env.exists():
            load_dotenv(home_env, override=False)
            loaded.append(str(home_env))

        if loaded:
            logger.debug(f"Loaded env files: {loaded}")

    @classmethod
    def from_file(cls, path: str | Path, load_env: bool = True) -> Config:
        """Load configuration from a WORKFLOW.md file.

        Args:
            path: Path to WORKFLOW.md file
            load_env: Whether to load .env files before parsing

        Returns:
            Config instance with loaded settings

        Raises:
            ConfigError: If file cannot be read or parsed
        """
        path = Path(path)

        if not path.exists():
            raise ConfigError(f"Workflow file not found: {path}")

        # Load .env files first
        if load_env:
            cls.load_env_files(path)

        try:
            loader = WorkflowLoader()
            result = loader.load(path)

            if result.error:
                raise ConfigError(f"Failed to load workflow: {result.error}")

            # Parse YAML front matter into config
            config_data = result.front_matter or {}
            
            # Create settings - environment variables will be picked up
            # automatically by the model validators
            settings = SymphonyConfig.model_validate(config_data)

            config = cls(settings, workflow_path=path)
            logger.info(f"Loaded configuration from {path}")
            return config

        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in workflow file: {e}") from e
        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {e}") from e

    @classmethod
    def from_dict(cls, data: dict[str, Any], load_env: bool = True) -> Config:
        """Create configuration from a dictionary.

        Args:
            data: Configuration dictionary
            load_env: Whether to load .env files

        Returns:
            Config instance
        """
        if load_env:
            cls.load_env_files()

        settings = SymphonyConfig.model_validate(data)
        return cls(settings)

    @classmethod
    def from_env(cls) -> Config:
        """Create configuration purely from environment variables.

        This creates a config with default values, which will be
        overridden by environment variables during validation.

        Returns:
            Config instance
        """
        cls.load_env_files()
        settings = SymphonyConfig()  # Will pick up env vars in validators
        return cls(settings)

    @classmethod
    def get_instance(cls) -> Config:
        """Get the global configuration instance.

        Returns:
            The current global Config instance

        Raises:
            RuntimeError: If no configuration has been loaded
        """
        if cls._instance is None:
            raise RuntimeError(
                "Configuration not loaded. Call Config.from_file() first."
            )
        return cls._instance

    @classmethod
    def set_instance(cls, config: Config) -> None:
        """Set the global configuration instance.

        Args:
            config: Config instance to set as global
        """
        cls._instance = config
        cls._settings = config.settings

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the global configuration instance."""
        cls._instance = None
        cls._settings = None

    @property
    def settings(self) -> SymphonyConfig:
        """Get the current configuration settings."""
        if self._settings is None:
            raise RuntimeError("Configuration not loaded")
        return self._settings

    @property
    def workflow_path(self) -> Path | None:
        """Get the path to the workflow file."""
        return self._workflow_path

    def validate(self) -> None:
        """Validate the current configuration.

        Performs semantic validation beyond schema validation.

        Raises:
            ConfigError: If configuration is invalid
        """
        settings = self.settings

        # Validate LLM configuration
        if not settings.llm.api_key:
            raise ConfigError(
                "LLM API key is required. "
                "Set llm.api_key in WORKFLOW.md, "
                "or set OPENAI_API_KEY / ANTHROPIC_API_KEY / etc. environment variable, "
                "or add to .env file."
            )

        # Validate tracker configuration
        if settings.tracker.kind == "linear":
            if not settings.tracker.api_key:
                raise ConfigError(
                    "Linear API key is required. "
                    "Set tracker.api_key in WORKFLOW.md or LINEAR_API_KEY environment variable."
                )
            if not settings.tracker.project_slug:
                raise ConfigError(
                    "Linear project slug is required. "
                    "Set tracker.project_slug in WORKFLOW.md."
                )

        # Validate workspace root is valid path
        try:
            Path(settings.workspace.root).resolve()
        except Exception as e:
            raise ConfigError(f"Invalid workspace root path: {e}")

        logger.debug("Configuration validation passed")

    def is_valid(self) -> bool:
        """Check if configuration is valid without raising.

        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            self.validate()
            return True
        except ConfigError:
            return False

    def reload(self) -> Config:
        """Reload configuration from the workflow file.

        Returns:
            New Config instance with reloaded settings

        Raises:
            ConfigError: If reload fails
            RuntimeError: If no workflow path is set
        """
        if self._workflow_path is None:
            raise RuntimeError("Cannot reload: no workflow file path set")

        return self.from_file(self._workflow_path)

    def get_poll_interval_ms(self) -> int:
        """Get effective poll interval in milliseconds."""
        return self.settings.polling.interval_ms

    def get_max_concurrent_agents(self) -> int:
        """Get effective max concurrent agents."""
        return self.settings.agent.max_concurrent_agents

    def get_workspace_root(self) -> Path:
        """Get workspace root as resolved Path."""
        return Path(self.settings.workspace.root).expanduser().resolve()

    def get_llm_config(self) -> dict[str, Any]:
        """Get LLM client configuration dictionary."""
        return self.settings.get_llm_client_config()

    def __repr__(self) -> str:
        """String representation of Config."""
        path_str = f" path={self._workflow_path}" if self._workflow_path else ""
        return f"Config({path_str})"


# Convenience function for accessing global config
def get_config() -> SymphonyConfig:
    """Get the global configuration settings.

    Returns:
        SymphonyConfig instance

    Raises:
        RuntimeError: If configuration not loaded
    """
    return Config.get_instance().settings


def get_llm_config() -> dict[str, Any]:
    """Get LLM client configuration from global config.

    Returns:
        Dictionary with LLM configuration
    """
    return Config.get_instance().get_llm_config()
