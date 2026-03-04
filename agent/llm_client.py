"""Multimodal LLM client — unified OpenAI-compatible API for both cloud and local."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from core.config import LLMSettings

logger = logging.getLogger(__name__)

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class ToolCall:
    """A single tool/function call returned by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Unified response from any LLM channel."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    provider: str = ""
    model: str = ""
    raw: Any = None


class LLMClient:
    """Dual-channel multimodal LLM client.

    Both channels use the OpenAI-compatible chat completions API:

    Primary:   DashScope cloud (qwen3.5-plus via OpenAI-compatible endpoint)
    Fallback:  Ollama local    (qwen3.5:9b   via OpenAI-compatible endpoint)

    Supports multimodal input (image + text), Function Calling,
    automatic failover, and retry with exponential back-off.
    """

    def __init__(self, settings: LLMSettings):
        self._settings = settings
        self._api_key = settings.api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self._primary = settings.provider
        self._primary_model = settings.model
        self._primary_url = settings.base_url or DASHSCOPE_BASE_URL
        self._fallback = settings.fallback_provider
        self._fallback_model = settings.fallback_model
        self._fallback_url = settings.fallback_base_url
        self._max_retries = settings.max_retries
        self._timeout = settings.timeout

        self._cloud_ok = True
        self._local_ok = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send a multimodal chat request with automatic failover."""
        providers = self._ordered_providers()
        last_err: Exception | None = None

        for provider in providers:
            try:
                return await self._call_with_retry(provider, messages, tools)
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "LLM provider '%s' failed: %s — trying next", provider, exc
                )
                if provider == "dashscope":
                    self._cloud_ok = False
                else:
                    self._local_ok = False

        logger.error("All LLM providers failed. Last error: %s", last_err)
        return LLMResponse(content="", provider="none")

    async def health_check(self) -> dict[str, Any]:
        """Quick connectivity check for both providers."""
        result: dict[str, Any] = {}

        for name, base_url, model, api_key in [
            ("cloud", self._primary_url, self._primary_model, self._api_key),
            ("local", f"{self._fallback_url}/v1", self._fallback_model, "ollama"),
        ]:
            try:
                resp = await self._openai_call(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    tools=None,
                    provider_name=name,
                )
                result[name] = {"status": "ok", "latency_ms": resp.latency_ms}
            except Exception as exc:
                result[name] = {"status": "error", "error": str(exc)}

        return result

    # ------------------------------------------------------------------
    # Provider ordering
    # ------------------------------------------------------------------

    def _ordered_providers(self) -> list[str]:
        primary = self._primary
        fallback = self._fallback

        if primary == "dashscope" and not self._api_key:
            return [fallback]

        if primary == fallback:
            return [primary]

        return [primary, fallback]

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self,
        provider: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        for attempt in range(1, self._max_retries + 1):
            try:
                if provider == "dashscope":
                    return await self._call_cloud(messages, tools)
                else:
                    return await self._call_local(messages, tools)
            except Exception:
                if attempt == self._max_retries:
                    raise
                wait = min(2 ** attempt, 8)
                logger.debug(
                    "Retry %d/%d for %s in %ds",
                    attempt, self._max_retries, provider, wait,
                )
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")

    # ------------------------------------------------------------------
    # Cloud channel (DashScope OpenAI-compatible)
    # ------------------------------------------------------------------

    async def _call_cloud(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        resp = await self._openai_call(
            base_url=self._primary_url,
            api_key=self._api_key,
            model=self._primary_model,
            messages=messages,
            tools=tools,
            provider_name="cloud",
        )
        self._cloud_ok = True
        return resp

    # ------------------------------------------------------------------
    # Local channel (Ollama OpenAI-compatible)
    # ------------------------------------------------------------------

    async def _call_local(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        resp = await self._openai_call(
            base_url=f"{self._fallback_url}/v1",
            api_key="ollama",
            model=self._fallback_model,
            messages=messages,
            tools=tools,
            provider_name="local",
        )
        self._local_ok = True
        return resp

    # ------------------------------------------------------------------
    # Unified OpenAI-compatible call
    # ------------------------------------------------------------------

    async def _openai_call(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        provider_name: str,
    ) -> LLMResponse:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=self._timeout,
        )

        oai_messages = self._to_openai_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
        }
        if tools:
            kwargs["tools"] = tools

        t0 = time.perf_counter()
        response = await client.chat.completions.create(**kwargs)
        latency = (time.perf_counter() - t0) * 1000

        choice = response.choices[0]
        msg = choice.message

        content = msg.content or ""
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id or "",
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=latency,
            provider=provider_name,
            model=model,
            raw=response,
        )

    # ------------------------------------------------------------------
    # Message format converter
    # ------------------------------------------------------------------

    @staticmethod
    def _to_openai_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert internal message format to OpenAI multi-modal format.

        Both DashScope and Ollama accept this format via their
        OpenAI-compatible endpoints.
        """
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, str):
                result.append({"role": role, "content": content})
            elif isinstance(content, list):
                parts = []
                for part in content:
                    ptype = part.get("type", "text")
                    if ptype == "text":
                        parts.append({"type": "text", "text": part["text"]})
                    elif ptype == "image":
                        img_data = part.get("image", "")
                        if isinstance(img_data, bytes):
                            img_data = base64.b64encode(img_data).decode()
                        url = (
                            img_data
                            if img_data.startswith("data:")
                            else f"data:image/jpeg;base64,{img_data}"
                        )
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": url},
                            }
                        )
                result.append({"role": role, "content": parts})
            else:
                result.append({"role": role, "content": str(content)})
        return result
