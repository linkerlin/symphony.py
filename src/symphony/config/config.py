"""Symphony 配置加载和管理。

提供从 WORKFLOW.md 文件、环境变量和 .env 文件加载配置的功能。
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
    """配置无效或无法加载时抛出。"""

    pass


class Config:
    """Symphony 配置管理器。

    此类负责加载和访问 Symphony 配置。
    支持从以下位置加载：
    1. .env 文件（自动从当前/工作流目录加载）
    2. 环境变量
    3. 带有 YAML front matter 的 WORKFLOW.md 文件

    配置优先级（从高到低）：
    1. WORKFLOW.md 中的显式值
    2. 环境变量
    3. .env 文件值
    4. 默认值

    示例：
        >>> # .env 文件
        >>> OPENAI_API_KEY=sk-...
        >>> OPENAI_BASE_URL=https://api.openai.com/v1
        >>> OPENAI_MODEL=gpt-4
        >>>
        >>> # Python
        >>> config = Config.from_file("WORKFLOW.md")
        >>> print(config.settings.llm.api_key)  # 来自 .env
        >>> config.validate()  # 如果无效则抛出 ConfigError
    """

    _instance: Config | None = None
    _settings: SymphonyConfig | None = None
    _workflow_path: Path | None = None

    def __init__(self, settings: SymphonyConfig, workflow_path: Path | None = None) -> None:
        """使用配置初始化。

        Args:
            settings: 已验证的配置对象
            workflow_path: 工作流文件路径（用于重新加载）
        """
        self._settings = settings
        self._workflow_path = workflow_path

    @classmethod
    def load_env_files(cls, workflow_path: str | Path | None = None) -> None:
        """从标准位置加载 .env 文件。

        按顺序加载：
        1. 工作流文件所在目录
        2. 当前工作目录
        3. 用户主目录 (~/.symphony.env)

        Args:
            workflow_path: 可选的工作流文件路径，用于查找其所在目录
        """
        loaded = []

        # 1. 工作流目录
        if workflow_path:
            workflow_dir = Path(workflow_path).parent
            env_file = workflow_dir / ".env"
            if env_file.exists():
                load_dotenv(env_file, override=False)
                loaded.append(str(env_file))

        # 2. 当前工作目录
        cwd_env = Path.cwd() / ".env"
        if cwd_env.exists() and cwd_env not in [Path(p) for p in loaded]:
            load_dotenv(cwd_env, override=False)
            loaded.append(str(cwd_env))

        # 3. 用户主目录
        home_env = Path.home() / ".symphony.env"
        if home_env.exists():
            load_dotenv(home_env, override=False)
            loaded.append(str(home_env))

        if loaded:
            logger.debug(f"Loaded env files: {loaded}")

    @classmethod
    def from_file(cls, path: str | Path, load_env: bool = True) -> Config:
        """从 WORKFLOW.md 文件加载配置。

        Args:
            path: WORKFLOW.md 文件路径
            load_env: 是否在解析前加载 .env 文件

        Returns:
            带有已加载配置的 Config 实例

        Raises:
            ConfigError: 如果文件无法读取或解析
        """
        path = Path(path)

        if not path.exists():
            raise ConfigError(f"Workflow file not found: {path}")

        # 首先加载 .env 文件
        if load_env:
            cls.load_env_files(path)

        try:
            loader = WorkflowLoader()
            result = loader.load(path)

            if result.error:
                raise ConfigError(f"Failed to load workflow: {result.error}")

            # 将 YAML front matter 解析为配置
            config_data = result.front_matter or {}
            
            # 创建设置 - 环境变量将被模型验证器自动获取
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
        """从字典创建配置。

        Args:
            data: 配置字典
            load_env: 是否加载 .env 文件

        Returns:
            Config 实例
        """
        if load_env:
            cls.load_env_files()

        settings = SymphonyConfig.model_validate(data)
        return cls(settings)

    @classmethod
    def from_env(cls) -> Config:
        """纯粹从环境变量创建配置。

        这将创建一个带有默认值的配置，
        在验证期间会被环境变量覆盖。

        Returns:
            Config 实例
        """
        cls.load_env_files()
        settings = SymphonyConfig()  # 将在验证器中获取环境变量
        return cls(settings)

    @classmethod
    def get_instance(cls) -> Config:
        """获取全局配置实例。

        Returns:
            当前全局 Config 实例

        Raises:
            RuntimeError: 如果尚未加载配置
        """
        if cls._instance is None:
            raise RuntimeError(
                "Configuration not loaded. Call Config.from_file() first."
            )
        return cls._instance

    @classmethod
    def set_instance(cls, config: Config) -> None:
        """设置全局配置实例。

        Args:
            config: 要设置为全局的 Config 实例
        """
        cls._instance = config
        cls._settings = config.settings

    @classmethod
    def reset_instance(cls) -> None:
        """重置全局配置实例。"""
        cls._instance = None
        cls._settings = None

    @property
    def settings(self) -> SymphonyConfig:
        """获取当前配置设置。"""
        if self._settings is None:
            raise RuntimeError("Configuration not loaded")
        return self._settings

    @property
    def workflow_path(self) -> Path | None:
        """获取工作流文件路径。"""
        return self._workflow_path

    def validate(self) -> None:
        """验证当前配置。

        执行模式验证之外的语义验证。

        Raises:
            ConfigError: 如果配置无效
        """
        settings = self.settings

        # 验证 LLM 配置
        if not settings.llm.api_key:
            raise ConfigError(
                "LLM API key is required. "
                "Set llm.api_key in WORKFLOW.md, "
                "or set OPENAI_API_KEY / ANTHROPIC_API_KEY / etc. environment variable, "
                "or add to .env file."
            )

        # 验证 tracker 配置
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

        # 验证工作区根路径是有效路径
        try:
            Path(settings.workspace.root).resolve()
        except Exception as e:
            raise ConfigError(f"Invalid workspace root path: {e}")

        logger.debug("Configuration validation passed")

    def is_valid(self) -> bool:
        """检查配置是否有效，不抛出异常。

        Returns:
            配置有效返回 True，否则返回 False
        """
        try:
            self.validate()
            return True
        except ConfigError:
            return False

    def reload(self) -> Config:
        """从工作流文件重新加载配置。

        Returns:
            带有重新加载设置的新 Config 实例

        Raises:
            ConfigError: 如果重新加载失败
            RuntimeError: 如果未设置工作流路径
        """
        if self._workflow_path is None:
            raise RuntimeError("Cannot reload: no workflow file path set")

        return self.from_file(self._workflow_path)

    def get_poll_interval_ms(self) -> int:
        """获取有效的轮询间隔（毫秒）。"""
        return self.settings.polling.interval_ms

    def get_max_concurrent_agents(self) -> int:
        """获取有效的最大并发代理数。"""
        return self.settings.agent.max_concurrent_agents

    def get_workspace_root(self) -> Path:
        """获取解析后的工作区根路径。"""
        return Path(self.settings.workspace.root).expanduser().resolve()

    def get_llm_config(self) -> dict[str, Any]:
        """获取 LLM 客户端配置字典。"""
        return self.settings.get_llm_client_config()

    def __repr__(self) -> str:
        """Config 的字符串表示。"""
        path_str = f" path={self._workflow_path}" if self._workflow_path else ""
        return f"Config({path_str})"


# 访问全局配置的便捷函数
def get_config() -> SymphonyConfig:
    """获取全局配置设置。

    Returns:
        SymphonyConfig 实例

    Raises:
        RuntimeError: 如果配置未加载
    """
    return Config.get_instance().settings


def get_llm_config() -> dict[str, Any]:
    """从全局配置获取 LLM 客户端配置。

    Returns:
        LLM 配置字典
    """
    return Config.get_instance().get_llm_config()
