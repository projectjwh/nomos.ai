"""Unified LLM client abstraction — supports Anthropic Claude and local Ollama (Llama).

All AI-calling modules use this client instead of importing anthropic directly.
The provider is selected via the PHD_LLM_PROVIDER config setting.

Supported providers:
  - "anthropic" (default): Uses the Anthropic SDK with Claude models
  - "ollama": Uses a local Ollama instance running Llama or any GGUF model
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from phd_platform.config import get_settings


# ---------------------------------------------------------------------------
# Unified response types (match Anthropic's shape so callers don't change)
# ---------------------------------------------------------------------------
@dataclass
class ContentBlock:
    text: str
    type: str = "text"


@dataclass
class LLMResponse:
    content: list[ContentBlock] = field(default_factory=list)
    model: str = ""
    stop_reason: str = "end_turn"


# ---------------------------------------------------------------------------
# Unified message interface
# ---------------------------------------------------------------------------
class LLMMessages:
    """Common interface for messages.create() across providers."""

    async def create(
        self,
        *,
        model: str = "",
        max_tokens: int = 4096,
        system: str = "",
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------
class AnthropicMessages(LLMMessages):
    def __init__(self) -> None:
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic()

    async def create(
        self,
        *,
        model: str = "",
        max_tokens: int = 4096,
        system: str = "",
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        settings = get_settings()
        call_kwargs: dict[str, Any] = {
            "model": model or settings.anthropic_model,
            "max_tokens": max_tokens,
            "messages": messages or [],
        }
        if system:
            call_kwargs["system"] = system

        response = await self._client.messages.create(**call_kwargs)
        return LLMResponse(
            content=[ContentBlock(text=block.text) for block in response.content],
            model=response.model,
            stop_reason=response.stop_reason or "end_turn",
        )


# ---------------------------------------------------------------------------
# Ollama (local Llama) provider
# ---------------------------------------------------------------------------
class OllamaMessages(LLMMessages):
    """Calls a local Ollama instance via its HTTP API.

    Ollama runs at http://localhost:11434 by default.
    Install: https://ollama.com
    Pull a model: ollama pull llama3.1:8b
    """

    def __init__(self) -> None:
        import httpx
        settings = get_settings()
        self._http = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=120.0,
        )

    async def create(
        self,
        *,
        model: str = "",
        max_tokens: int = 4096,
        system: str = "",
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        settings = get_settings()
        model = model or settings.ollama_model

        # Build Ollama chat messages (OpenAI-compatible format)
        ollama_messages: list[dict] = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        for msg in (messages or []):
            ollama_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        response = await self._http.post(
            "/api/chat",
            json={
                "model": model,
                "messages": ollama_messages,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7,
                },
            },
        )
        response.raise_for_status()
        data = response.json()

        text = data.get("message", {}).get("content", "")
        return LLMResponse(
            content=[ContentBlock(text=text)],
            model=model,
            stop_reason="end_turn",
        )

    async def close(self) -> None:
        await self._http.aclose()


# ---------------------------------------------------------------------------
# Offline provider (no LLM — returns empty responses)
# ---------------------------------------------------------------------------
class OfflineMessages(LLMMessages):
    """Stub provider for fully offline operation.

    Returns a message explaining that no LLM is configured.
    The caller (placement, assessment) should use the question bank
    and local grader instead of calling the LLM.
    """

    async def create(
        self,
        *,
        model: str = "",
        max_tokens: int = 4096,
        system: str = "",
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return LLMResponse(
            content=[ContentBlock(text='{"score": 0.5, "feedback": "Offline mode — use local grader for evaluation.", "weakness_areas": []}')],
            model="offline",
            stop_reason="end_turn",
        )


# ---------------------------------------------------------------------------
# Unified client
# ---------------------------------------------------------------------------
class LLMClient:
    """Drop-in replacement for AsyncAnthropic — routes to configured provider.

    Usage is identical to the Anthropic SDK:
        client = LLMClient()
        response = await client.messages.create(
            model="...", max_tokens=4096, messages=[...]
        )
        text = response.content[0].text

    Providers:
        "anthropic" — Claude API (needs ANTHROPIC_API_KEY)
        "ollama"    — Local Ollama instance (needs ollama running)
        "none"      — Fully offline (returns stub responses)
    """

    def __init__(self, provider: str | None = None):
        settings = get_settings()
        self._provider = provider or settings.llm_provider

        if self._provider == "ollama":
            self.messages: LLMMessages = OllamaMessages()
        elif self._provider == "none":
            self.messages = OfflineMessages()
        elif self._provider == "anthropic":
            self.messages = AnthropicMessages()
        else:
            # Default to offline if unknown provider
            self.messages = OfflineMessages()

    @property
    def is_offline(self) -> bool:
        return isinstance(self.messages, OfflineMessages)


def get_llm_client(provider: str | None = None) -> LLMClient:
    """Factory function for creating the LLM client."""
    return LLMClient(provider=provider)
