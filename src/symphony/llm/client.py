"""Symphony 的 LLM 客户端。

与提供商无关的 LLM 客户端，支持多个后端。
使用 httpx 进行异步 HTTP 请求。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

import httpx

from symphony.llm.providers import ProviderType, get_provider_defaults

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """聊天消息。"""

    role: Literal["system", "user", "assistant", "function"]
    content: str
    name: str | None = None  # 用于函数消息
    function_call: dict[str, Any] | None = None  # 用于助手函数调用


@dataclass
class LLMResponse:
    """LLM 的响应。"""

    content: str
    role: str = "assistant"
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class LLMStreamChunk:
    """流式 LLM 响应的一个数据块。"""

    content: str
    is_finished: bool = False
    finish_reason: str | None = None


class LLMError(Exception):
    """当 LLM 请求失败时抛出。"""

    pass


class LLMClient:
    """与提供商无关的 LLM 客户端。

    支持 OpenAI、Anthropic、DeepSeek、Gemini 和 Azure OpenAI。

    示例:
        >>> client = LLMClient.from_config({
        ...     "provider": "openai",
        ...     "api_key": "sk-...",
        ...     "model": "gpt-4"
        ... })
        >>> response = await client.complete([
        ...     Message(role="system", content="你是一个有帮助的助手。"),
        ...     Message(role="user", content="你好！")
        ... ])
    """

    def __init__(
        self,
        provider: ProviderType | str,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: int = 120,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> None:
        """初始化 LLM 客户端。

        Args:
            provider: LLM 提供商名称
            api_key: 提供商的 API 密钥
            model: 模型名称（如果未指定则使用提供商默认值）
            base_url: API 的自定义基础 URL
            temperature: 采样温度（0-2）
            max_tokens: 生成的最大令牌数
            timeout: 请求超时时间（秒）
            max_retries: 失败请求的最大重试次数
            **kwargs: 额外的提供商特定选项
        """
        self.provider = ProviderType(provider) if isinstance(provider, str) else provider
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.kwargs = kwargs

        # 获取提供商默认值
        defaults = get_provider_defaults(self.provider)
        self.model = model or defaults.get("model", "gpt-4")
        self.base_url = base_url or defaults.get("base_url")
        self.temperature = temperature
        self.max_tokens = max_tokens

        # 提供商特定设置
        self.supports_system = defaults.get("supports_system_message", True)
        self.supports_functions = defaults.get("supports_functions", True)

        # 设置 HTTP 客户端
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=self._get_headers(),
        )

        logger.debug(
            f"已初始化 LLM 客户端: provider={self.provider.value}, "
            f"model={self.model}"
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> LLMClient:
        """从配置字典创建 LLM 客户端。

        Args:
            config: 包含 provider、api_key 等键的配置字典

        Returns:
            配置好的 LLMClient
        """
        return cls(**config)

    def _get_headers(self) -> dict[str, str]:
        """获取 API 请求的 HTTP 头。"""
        if self.provider == ProviderType.OPENAI:
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        elif self.provider == ProviderType.ANTHROPIC:
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        elif self.provider == ProviderType.DEEPSEEK:
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        elif self.provider == ProviderType.GEMINI:
            return {
                "Content-Type": "application/json",
            }
        elif self.provider == ProviderType.AZURE:
            return {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        else:
            return {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

    def _get_api_url(self) -> str:
        """获取 API 端点 URL。"""
        if self.provider == ProviderType.OPENAI:
            base = self.base_url or "https://api.openai.com/v1"
            return f"{base}/chat/completions"
        elif self.provider == ProviderType.ANTHROPIC:
            base = self.base_url or "https://api.anthropic.com"
            return f"{base}/v1/messages"
        elif self.provider == ProviderType.DEEPSEEK:
            base = self.base_url or "https://api.deepseek.com"
            return f"{base}/chat/completions"
        elif self.provider == ProviderType.GEMINI:
            # Gemini 使用不同的 URL 格式
            base = self.base_url or "https://generativelanguage.googleapis.com/v1"
            return f"{base}/models/{self.model}:generateContent?key={self.api_key}"
        elif self.provider == ProviderType.AZURE:
            if not self.base_url:
                raise LLMError("Azure OpenAI 需要提供 base_url（端点）")
            return f"{self.base_url}/openai/deployments/{self.model}/chat/completions?api-version=2024-02-01"
        else:
            raise LLMError(f"未知的提供商: {self.provider}")

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """格式化消息以用于 API 请求。"""
        if self.provider == ProviderType.ANTHROPIC:
            # Anthropic 使用不同的格式
            formatted = []
            for msg in messages:
                if msg.role == "system":
                    # Anthropic 单独处理系统消息
                    continue
                formatted.append({
                    "role": msg.role,
                    "content": msg.content,
                })
            return formatted
        elif self.provider == ProviderType.GEMINI:
            # Gemini 使用另一种格式
            contents = []
            for msg in messages:
                if msg.role == "system":
                    # Gemini 不直接支持系统消息
                    continue
                role = "user" if msg.role in ("user", "function") else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })
            return contents
        else:
            # OpenAI 兼容格式
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({"name": msg.name} if msg.name else {}),
                }
                for msg in messages
            ]

    def _build_payload(self, messages: list[Message], **kwargs: Any) -> dict[str, Any]:
        """构建 API 请求负载。"""
        formatted = self._format_messages(messages)

        if self.provider == ProviderType.ANTHROPIC:
            # 提取系统消息
            system_msg = None
            for msg in messages:
                if msg.role == "system":
                    system_msg = msg.content
                    break

            payload = {
                "model": self.model,
                "messages": formatted,
                "max_tokens": self.max_tokens or 4096,
                "temperature": self.temperature,
            }
            if system_msg:
                payload["system"] = system_msg
            if self.max_tokens:
                payload["max_tokens"] = self.max_tokens

        elif self.provider == ProviderType.GEMINI:
            # Gemini 格式
            payload = {
                "contents": formatted,
                "generationConfig": {
                    "temperature": self.temperature,
                },
            }
            if self.max_tokens:
                payload["generationConfig"]["maxOutputTokens"] = self.max_tokens

        else:
            # OpenAI 兼容格式
            payload = {
                "model": self.model,
                "messages": formatted,
                "temperature": self.temperature,
            }
            if self.max_tokens:
                payload["max_tokens"] = self.max_tokens

        # 合并额外的 kwargs
        payload.update(kwargs)
        return payload

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """解析 API 响应。"""
        if self.provider == ProviderType.ANTHROPIC:
            content = data.get("content", [{}])[0].get("text", "")
            usage = data.get("usage", {})
            return LLMResponse(
                content=content,
                role="assistant",
                finish_reason=data.get("stop_reason"),
                usage={
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                },
                raw_response=data,
            )

        elif self.provider == ProviderType.GEMINI:
            candidates = data.get("candidates", [{}])[0]
            content = candidates.get("content", {}).get("parts", [{}])[0].get("text", "")
            usage = data.get("usageMetadata", {})
            return LLMResponse(
                content=content,
                role="assistant",
                usage={
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                },
                raw_response=data,
            )

        else:
            # OpenAI 兼容格式
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            usage = data.get("usage", {})
            return LLMResponse(
                content=message.get("content", ""),
                role=message.get("role", "assistant"),
                finish_reason=choice.get("finish_reason"),
                usage=usage,
                raw_response=data,
            )

    async def complete(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> LLMResponse:
        """向 LLM 发送补全请求。

        Args:
            messages: 对话的消息列表
            **kwargs: 传递给 API 的额外参数

        Returns:
            包含生成内容的 LLMResponse

        Raises:
            LLMError: 如果请求失败
        """
        url = self._get_api_url()
        payload = self._build_payload(messages, **kwargs)

        for attempt in range(self.max_retries):
            try:
                response = await self._client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return self._parse_response(data)

            except httpx.HTTPStatusError as e:
                logger.warning(f"LLM 请求失败（第 {attempt + 1} 次尝试）: {e}")
                if attempt == self.max_retries - 1:
                    raise LLMError(f"LLM 请求失败: {e.response.text}") from e

            except Exception as e:
                logger.warning(f"LLM 请求错误（第 {attempt + 1} 次尝试）: {e}")
                if attempt == self.max_retries - 1:
                    raise LLMError(f"LLM 请求失败: {e}") from e

        raise LLMError("超过最大重试次数")

    async def stream(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        """从 LLM 流式获取补全结果。

        Args:
            messages: 对话的消息列表
            **kwargs: 额外的参数

        Yields:
            包含内容块的 LLMStreamChunk

        Raises:
            LLMError: 如果请求失败
        """
        url = self._get_api_url()
        payload = self._build_payload(messages, **kwargs)
        payload["stream"] = True

        try:
            async with self._client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data = line[6:]  # 移除 "data: " 前缀
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                        if self.provider == ProviderType.ANTHROPIC:
                            delta = chunk.get("delta", {})
                            content = delta.get("text", "")
                            if content:
                                yield LLMStreamChunk(content=content)
                        else:
                            choices = chunk.get("choices", [{}])
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield LLMStreamChunk(content=content)
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            raise LLMError(f"流式传输失败: {e}") from e

        yield LLMStreamChunk(content="", is_finished=True)

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        await self._client.aclose()

    def __repr__(self) -> str:
        """字符串表示。"""
        return f"LLMClient(provider={self.provider.value}, model={self.model})"
