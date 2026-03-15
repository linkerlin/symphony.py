"""Configuration loading and management for Symphony.

Provides functionality to load configuration from WORKFLOW.md files,
validate settings, and access configuration at runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from symphony.config.schema import SymphonyConfig
from symphony.workflow.loader import WorkflowLoader

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class Config:
    """Configuration manager for Symphony.

    This class manages loading and accessing Symphony configuration.
    It supports loading from WORKFLOW.md files with YAML front matter.

    Example:
        >>> config = Config.from_file("WORKFLOW.md")
        >>> print(config.settings.tracker.project_slug)
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
    def from_file(cls, path: str | Path) -> Config:
        """Load configuration from a WORKFLOW.md file.

        Args:
            path: Path to WORKFLOW.md file

        Returns:
            Config instance with loaded settings

        Raises:
            ConfigError: If file cannot be read or parsed
        """
        path = Path(path)

        if not path.exists():
            raise ConfigError(f"Workflow file not found: {path}")

        try:
            loader = WorkflowLoader()
            result = loader.load(path)

            if result.error:
                raise ConfigError(f"Failed to load workflow: {result.error}")

            # Parse YAML front matter into config
            config_data = result.front_matter or {}
            settings = SymphonyConfig.model_validate(config_data)

            config = cls(settings, workflow_path=path)
            logger.info(f"Loaded configuration from {path}")
            return config

        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in workflow file: {e}") from e
        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {e}") from e

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Config instance
        """
        settings = SymphonyConfig.model_validate(data)
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

        # Validate codex command is not empty
        if not settings.codex.command or not settings.codex.command.strip():
            raise ConfigError("codex.command cannot be empty")

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
