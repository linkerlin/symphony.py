"""LLM client for Symphony.

Provider-agnostic LLM client supporting multiple backends.
Uses httpx for async HTTP requests.
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
    """A chat message."""

    role: Literal["system", "user", "assistant", "function"]
    content: str
    name: str | None = None  # For function messages
    function_call: dict[str, Any] | None = None  # For assistant function calls


@dataclass
class LLMResponse:
    """Response from LLM."""

    content: str
    role: str = "assistant"
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class LLMStreamChunk:
    """A chunk of a streaming LLM response."""

    content: str
    is_finished: bool = False
    finish_reason: str | None = None


class LLMError(Exception):
    """Raised when LLM request fails."""

    pass


class LLMClient:
    """Provider-agnostic LLM client.

    Supports OpenAI, Anthropic, DeepSeek, Gemini, and Azure OpenAI.

    Example:
        >>> client = LLMClient.from_config({
        ...     "provider": "openai",
        ...     "api_key": "sk-...",
        ...     "model": "gpt-4"
        ... })
        >>> response = await client.complete([
        ...     Message(role="system", content="You are a helpful assistant."),
        ...     Message(role="user", content="Hello!")
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
        """Initialize LLM client.

        Args:
            provider: LLM provider name
            api_key: API key for the provider
            model: Model name (uses provider default if not specified)
            base_url: Custom base URL for API
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            max_retries: Maximum retries for failed requests
            **kwargs: Additional provider-specific options
        """
        self.provider = ProviderType(provider) if isinstance(provider, str) else provider
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.kwargs = kwargs

        # Get provider defaults
        defaults = get_provider_defaults(self.provider)
        self.model = model or defaults.get("model", "gpt-4")
        self.base_url = base_url or defaults.get("base_url")
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Provider-specific settings
        self.supports_system = defaults.get("supports_system_message", True)
        self.supports_functions = defaults.get("supports_functions", True)

        # Setup HTTP client
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=self._get_headers(),
        )

        logger.debug(
            f"Initialized LLM client: provider={self.provider.value}, "
            f"model={self.model}"
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> LLMClient:
        """Create LLM client from configuration dictionary.

        Args:
            config: Configuration dict with keys like provider, api_key, etc.

        Returns:
            Configured LLMClient
        """
        return cls(**config)

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
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
        """Get API endpoint URL."""
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
            # Gemini uses a different URL format
            base = self.base_url or "https://generativelanguage.googleapis.com/v1"
            return f"{base}/models/{self.model}:generateContent?key={self.api_key}"
        elif self.provider == ProviderType.AZURE:
            if not self.base_url:
                raise LLMError("Azure OpenAI requires base_url (endpoint)")
            return f"{self.base_url}/openai/deployments/{self.model}/chat/completions?api-version=2024-02-01"
        else:
            raise LLMError(f"Unknown provider: {self.provider}")

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Format messages for API request."""
        if self.provider == ProviderType.ANTHROPIC:
            # Anthropic uses a different format
            formatted = []
            for msg in messages:
                if msg.role == "system":
                    # Anthropic handles system separately
                    continue
                formatted.append({
                    "role": msg.role,
                    "content": msg.content,
                })
            return formatted
        elif self.provider == ProviderType.GEMINI:
            # Gemini uses yet another format
            contents = []
            for msg in messages:
                if msg.role == "system":
                    # Gemini doesn't support system messages directly
                    continue
                role = "user" if msg.role in ("user", "function") else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })
            return contents
        else:
            # OpenAI-compatible format
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({"name": msg.name} if msg.name else {}),
                }
                for msg in messages
            ]

    def _build_payload(self, messages: list[Message], **kwargs: Any) -> dict[str, Any]:
        """Build API request payload."""
        formatted = self._format_messages(messages)

        if self.provider == ProviderType.ANTHROPIC:
            # Extract system message
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
            # Gemini format
            payload = {
                "contents": formatted,
                "generationConfig": {
                    "temperature": self.temperature,
                },
            }
            if self.max_tokens:
                payload["generationConfig"]["maxOutputTokens"] = self.max_tokens

        else:
            # OpenAI-compatible format
            payload = {
                "model": self.model,
                "messages": formatted,
                "temperature": self.temperature,
            }
            if self.max_tokens:
                payload["max_tokens"] = self.max_tokens

        # Merge additional kwargs
        payload.update(kwargs)
        return payload

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Parse API response."""
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
            # OpenAI-compatible format
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
        """Send completion request to LLM.

        Args:
            messages: List of messages for the conversation
            **kwargs: Additional parameters to pass to API

        Returns:
            LLMResponse with generated content

        Raises:
            LLMError: If request fails
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
                logger.warning(f"LLM request failed (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise LLMError(f"LLM request failed: {e.response.text}") from e

            except Exception as e:
                logger.warning(f"LLM request error (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise LLMError(f"LLM request failed: {e}") from e

        raise LLMError("Max retries exceeded")

    async def stream(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream completion from LLM.

        Args:
            messages: List of messages for the conversation
            **kwargs: Additional parameters

        Yields:
            LLMStreamChunk with content chunks

        Raises:
            LLMError: If request fails
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

                    data = line[6:]  # Remove "data: " prefix
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
            raise LLMError(f"Streaming failed: {e}") from e

        yield LLMChunk(content="", is_finished=True)

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()

    def __repr__(self) -> str:
        """String representation."""
        return f"LLMClient(provider={self.provider.value}, model={self.model})"
