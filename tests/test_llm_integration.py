"""Integration tests for LLM client with real API calls.

These tests make actual API calls to verify LLM connectivity and response handling.
They use fast/cheap models to minimize cost and execution time.
"""

from __future__ import annotations

import pytest

from symphony.llm.client import LLMClient, Message
from symphony.config.schema import LLMConfig


@pytest.mark.llm
@pytest.mark.timeout(10)
class TestLLMClientIntegration:
    """Integration tests for LLM client with real APIs."""
    
    async def test_basic_completion(self, fast_llm_client: LLMClient):
        """Test basic completion with real API."""
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Say 'hello' and nothing else."),
        ]
        
        response = await fast_llm_client.complete(messages)
        
        assert response.content is not None
        assert len(response.content) > 0
        assert "hello" in response.content.lower()
        assert response.usage.total_tokens > 0
        print(f"Response: {response.content[:100]}")
        print(f"Tokens: {response.usage}")
    
    async def test_completion_with_temperature_zero(self, fast_llm_client: LLMClient):
        """Test that temperature=0 gives consistent results."""
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="What is 2+2? Answer with just the number."),
        ]
        
        # Make two calls with temperature=0
        response1 = await fast_llm_client.complete(messages)
        response2 = await fast_llm_client.complete(messages)
        
        # Both should contain "4"
        assert "4" in response1.content
        assert "4" in response2.content
    
    async def test_token_usage_tracking(self, fast_llm_client: LLMClient):
        """Test that token usage is properly tracked."""
        messages = [
            Message(role="system", content="You are helpful."),
            Message(role="user", content="Hi"),
        ]
        
        response = await fast_llm_client.complete(messages)
        
        assert response.usage.prompt_tokens > 0
        assert response.usage.completion_tokens > 0
        assert response.usage.total_tokens > 0
        assert response.usage.total_tokens == (
            response.usage.prompt_tokens + response.usage.completion_tokens
        )
    
    async def test_max_tokens_limit(self, test_settings):
        """Test that max_tokens is respected."""
        # Create client with very low token limit
        config = test_settings.llm.model_copy()
        config.max_tokens = 10
        
        client = LLMClient.from_config(config)
        
        try:
            messages = [
                Message(role="user", content="Write a long story about a cat."),
            ]
            
            response = await client.complete(messages)
            
            # Response should be truncated due to token limit
            assert response.usage.completion_tokens <= 15  # Allow some buffer
        finally:
            await client.close()
    
    async def test_system_message_handling(self, fast_llm_client: LLMClient):
        """Test that system messages are properly handled."""
        messages = [
            Message(
                role="system",
                content="You only respond with YES or NO."
            ),
            Message(role="user", content="Is the sky blue?"),
        ]
        
        response = await fast_llm_client.complete(messages)
        
        # Should follow system instruction
        content_upper = response.content.upper()
        assert "YES" in content_upper or "NO" in content_upper
    
    async def test_multi_turn_conversation(self, fast_llm_client: LLMClient):
        """Test multi-turn conversation."""
        messages = [
            Message(role="user", content="My name is Alice."),
        ]
        
        response1 = await fast_llm_client.complete(messages)
        messages.append(Message(role="assistant", content=response1.content))
        messages.append(Message(role="user", content="What is my name?"))
        
        response2 = await fast_llm_client.complete(messages)
        
        # Should remember the name
        assert "Alice" in response2.content


@pytest.mark.llm
@pytest.mark.timeout(10)
class TestLLMProviderConnectivity:
    """Tests for verifying connectivity to different LLM providers."""
    
    async def test_openai_connectivity(self):
        """Test OpenAI API connectivity."""
        import os
        
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")
        
        config = LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            max_tokens=50,
        )
        
        client = LLMClient.from_config(config)
        try:
            response = await client.complete([
                Message(role="user", content="Say 'OpenAI OK'")
            ])
            assert "OpenAI" in response.content or "OK" in response.content
        finally:
            await client.close()
    
    async def test_anthropic_connectivity(self):
        """Test Anthropic API connectivity."""
        import os
        
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        config = LLMConfig(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            max_tokens=50,
        )
        
        client = LLMClient.from_config(config)
        try:
            response = await client.complete([
                Message(role="user", content="Say 'Anthropic OK'")
            ])
            assert "Anthropic" in response.content or "OK" in response.content
        finally:
            await client.close()


@pytest.mark.llm
@pytest.mark.timeout(5)
class TestLLMErrorHandling:
    """Tests for LLM error handling with real APIs."""
    
    async def test_invalid_api_key(self):
        """Test handling of invalid API key."""
        config = LLMConfig(
            provider="openai",
            api_key="invalid_key_for_testing",
            model="gpt-4o-mini",
        )
        
        client = LLMClient.from_config(config)
        
        try:
            with pytest.raises(Exception) as exc_info:
                await client.complete([Message(role="user", content="Hi")])
            
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["auth", "key", "invalid", "unauthorized"])
        finally:
            await client.close()
