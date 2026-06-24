"""LLM transports for the Maisha drafting layer. Each client takes a system prompt, a user
prompt, and a JSON schema, and returns the model's response **parsed as a JSON object** —
the schema is enforced by the provider's constrained-decoding feature so a malformed claim
cannot come back:

* :class:`OllamaClient` — local, the default; uses Ollama's ``format=<schema>`` structured
  output on ``/api/chat``.
* :class:`ClaudeClient` — explicit fallback (CLAUDE.md §7); forces a single tool whose
  ``input_schema`` is the claim schema, so the model must return a schema-valid tool call.
* :class:`CannedClient` — returns pre-set objects, ignoring the prompt; for tests and the
  ``off`` provider.

Clients accept an optional ``transport`` so tests can drive them with ``httpx.MockTransport``
without a live server.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx


class LLMError(RuntimeError):
    """The model was unreachable or returned something unusable. We fail loud rather than
    fabricate a claim — Mahsa never sees a number we couldn't actually obtain."""


class LLMClient(Protocol):
    async def complete(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class CannedClient:
    """Returns canned objects in order (the last one repeats). Ignores the prompt entirely.
    Used by tests and by the ``off`` provider so the rest of the pipeline can run."""

    def __init__(self, responses: list[dict[str, Any]] | dict[str, Any]) -> None:
        self._responses = responses if isinstance(responses, list) else [responses]
        if not self._responses:
            raise ValueError("CannedClient needs at least one response")
        self._i = 0

    async def complete(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        resp = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return resp


class OllamaClient:
    """Local Ollama chat with structured output (``format`` = JSON schema), temperature 0."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.0,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._transport = transport

    async def complete(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": schema,
            "options": {"temperature": self._temperature},
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMError(f"Ollama /api/chat failed: {exc}") from exc
        content = resp.json().get("message", {}).get("content", "")
        try:
            obj = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Ollama returned non-JSON content: {content[:200]!r}") from exc
        if not isinstance(obj, dict):
            raise LLMError(f"Ollama returned a non-object claim: {type(obj).__name__}")
        return obj


class ClaudeClient:
    """Anthropic Messages API fallback. Forces the ``emit_action_claim`` tool so the model
    must return a schema-valid tool input."""

    _TOOL_NAME = "emit_action_claim"

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com",
        temperature: float = 0.0,
        timeout: float = 30.0,
        max_tokens: int = 2048,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("ClaudeClient requires MAISHA_CLAUDE_API_KEY")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._transport = transport

    async def complete(self, *, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": self._TOOL_NAME,
                    "description": "Emit the structured ActionClaim for this query.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": self._TOOL_NAME},
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/v1/messages", json=payload, headers=headers
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMError(f"Claude /v1/messages failed: {exc}") from exc
        for block in resp.json().get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == self._TOOL_NAME:
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    return tool_input
        raise LLMError("Claude response had no emit_action_claim tool_use block")


def build_client(settings: Any) -> LLMClient:
    """Construct the client for the configured provider. ``off`` returns a ``CannedClient``
    that abstains, so the caller's pipeline still runs deterministically with no model."""
    provider = settings.llm_provider
    if provider == "ollama":
        return OllamaClient(
            settings.ollama_url,
            settings.ollama_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_s,
        )
    if provider == "claude":
        return ClaudeClient(
            settings.claude_model,
            settings.claude_api_key,
            base_url=settings.claude_base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_s,
        )
    if provider == "off":
        return CannedClient({"domain": "", "abstained": True})
    raise LLMError(f"unknown MAISHA_LLM_PROVIDER: {provider!r}")
