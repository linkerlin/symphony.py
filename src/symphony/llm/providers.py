"""LLM 提供商类型和配置。

定义支持的 LLM 提供商及其默认配置。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ProviderType(str, Enum):
    """支持的 LLM 提供商类型。"""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    AZURE = "azure"


# 每个提供商的默认配置
PROVIDER_DEFAULTS: dict[ProviderType, dict[str, Any]] = {
    ProviderType.OPENAI: {
        "base_url": None,
        "model": "gpt-4",
        "supports_system_message": True,
        "supports_functions": True,
        "supports_json_mode": True,
    },
    ProviderType.ANTHROPIC: {
        "base_url": "https://api.anthropic.com",
        "model": "claude-3-sonnet-20240229",
        "supports_system_message": True,
        "supports_functions": True,
        "supports_json_mode": False,
    },
    ProviderType.DEEPSEEK: {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "supports_system_message": True,
        "supports_functions": True,
        "supports_json_mode": True,
    },
    ProviderType.GEMINI: {
        "base_url": "https://generativelanguage.googleapis.com",
        "model": "gemini-pro",
        "supports_system_message": False,  # Gemini 使用不同的格式
        "supports_functions": True,
        "supports_json_mode": False,
    },
    ProviderType.AZURE: {
        "base_url": None,  # 必须提供
        "model": "gpt-4",
        "supports_system_message": True,
        "supports_functions": True,
        "supports_json_mode": True,
    },
}

# 每个提供商的环境变量映射
PROVIDER_ENV_VARS: dict[ProviderType, dict[str, str]] = {
    ProviderType.OPENAI: {
        "api_key": "OPENAI_API_KEY",
        "base_url": "OPENAI_BASE_URL",
        "model": "OPENAI_MODEL",
    },
    ProviderType.ANTHROPIC: {
        "api_key": "ANTHROPIC_API_KEY",
        "base_url": "ANTHROPIC_BASE_URL",
        "model": "ANTHROPIC_MODEL",
    },
    ProviderType.DEEPSEEK: {
        "api_key": "DEEPSEEK_API_KEY",
        "base_url": "DEEPSEEK_BASE_URL",
        "model": "DEEPSEEK_MODEL",
    },
    ProviderType.GEMINI: {
        "api_key": "GEMINI_API_KEY",
        "base_url": "GEMINI_BASE_URL",
        "model": "GEMINI_MODEL",
    },
    ProviderType.AZURE: {
        "api_key": "AZURE_OPENAI_API_KEY",
        "base_url": "AZURE_OPENAI_ENDPOINT",
        "model": "AZURE_OPENAI_MODEL",
    },
}


def get_provider_defaults(provider: ProviderType) -> dict[str, Any]:
    """获取提供商的默认配置。

    Args:
        provider: 提供商类型

    Returns:
        包含默认配置的字典
    """
    return PROVIDER_DEFAULTS.get(provider, {}).copy()


def get_provider_env_vars(provider: ProviderType) -> dict[str, str]:
    """获取提供商的环境变量名称。

    Args:
        provider: 提供商类型

    Returns:
        将配置键映射到环境变量名称的字典
    """
    return PROVIDER_ENV_VARS.get(provider, {}).copy()
