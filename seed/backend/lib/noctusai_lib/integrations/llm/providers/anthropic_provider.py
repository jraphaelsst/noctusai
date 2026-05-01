"""
AnthropicProvider — real implementation backed by the `anthropic` SDK.

Chat + vision hit the Messages API (`client.messages.create`). Embeddings
and audio transcription are not supported by Anthropic — those methods
raise `ProviderNotImplemented` with a clear explanation pointing callers at
OpenAI / another provider.

Translation notes (OpenAI-shaped → Anthropic):
  - OpenAI's `system` role entries become Anthropic's top-level `system=`
    parameter. Any `system` messages in the list get concatenated.
  - Remaining user/assistant messages pass through unchanged.
  - Vision: images are passed as content blocks inside the user message
    per the Anthropic spec (`{"type": "image", "source": {...}}`).

Client pooling mirrors the OpenAI provider — one `AsyncAnthropic` per
unique API key so multi-tenant processes don't churn connections.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional, Union

from anthropic import AsyncAnthropic, APIError as AnthropicAPIError

from ..exceptions import LLMAPIError, LLMNotConfigured, ProviderNotImplemented
from ..registry import register

logger = logging.getLogger(__name__)

# Default max_tokens for Anthropic's Messages API (SDK requires it — unlike
# OpenAI which defaults). Pick a reasonable upper bound per the chat context.
_DEFAULT_MAX_TOKENS = 4096


def _split_system_and_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Anthropic expects `system` as a top-level parameter, not a role.

    Concatenates all `system` messages (preserving order) and returns the
    rest. If there are no system messages, returns an empty string.
    """
    system_parts: list[str] = []
    rest: list[dict] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                # Content blocks; concat the text-block strings.
                system_parts.extend(
                    b.get("text", "") for b in content if b.get("type") == "text"
                )
        else:
            rest.append(msg)
    return "\n\n".join(p for p in system_parts if p), rest


class AnthropicProvider:
    """Real Anthropic provider — chat + vision via the official SDK."""

    name = "anthropic"

    def __init__(self) -> None:
        self._clients: dict[str, AsyncAnthropic] = {}

    def _client_for(self, api_key: str) -> AsyncAnthropic:
        if not api_key:
            raise LLMNotConfigured("anthropic")
        client = self._clients.get(api_key)
        if client is None:
            client = AsyncAnthropic(api_key=api_key)
            self._clients[api_key] = client
        return client

    async def chat_completion(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        from ..usage import record_usage

        client = self._client_for(api_key)
        system_prompt, conversation = _split_system_and_messages(messages)
        # `response_format` is OpenAI-shaped — Anthropic expresses JSON mode
        # by prefixing the assistant turn with "{" or by instruction in the
        # system prompt. We honour the OpenAI hint minimally by adding a
        # "return strict JSON" instruction when response_format looks like
        # JSON. Consumers needing richer schemas should set it in-prompt.
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
            and system_prompt is not None
        ):
            system_prompt = (
                (system_prompt + "\n\n" if system_prompt else "")
                + "Return your response as a valid JSON object. No prose outside the JSON."
            )

        try:
            response = await client.messages.create(
                model=model,
                system=system_prompt or "",
                messages=conversation,
                temperature=temperature,
                max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                **kwargs,
            )
            # Anthropic returns a list of content blocks; we concatenate text.
            parts: list[str] = []
            for block in response.content:
                # SDK content-block objects expose `.text` for text blocks.
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            content = "\n".join(parts).strip()

            usage = getattr(response, "usage", None)
            await record_usage(
                provider="anthropic",
                model=model,
                operation="chat",
                org_id=org_id,
                prompt_tokens=getattr(usage, "input_tokens", None),
                completion_tokens=getattr(usage, "output_tokens", None),
                total_tokens=(
                    (getattr(usage, "input_tokens", None) or 0)
                    + (getattr(usage, "output_tokens", None) or 0)
                    if usage else None
                ),
            )
            return content
        except AnthropicAPIError as exc:
            logger.error("Anthropic chat_completion failed: %s", exc)
            raise LLMAPIError("anthropic", str(exc)) from exc

    async def generate_embedding(
        self,
        text: str,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> list[float]:
        raise ProviderNotImplemented(
            "anthropic — embeddings not supported by the Anthropic API. "
            "Use an OpenAI or Gemini embedding model instead."
        )

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        raise ProviderNotImplemented(
            "anthropic — transcription not supported by the Anthropic API. "
            "Use the OpenAI Whisper model for audio."
        )

    async def analyze_image(
        self,
        image: Union[bytes, str],
        prompt: str,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        from ..usage import record_usage

        client = self._client_for(api_key)

        # Build the Anthropic content-block shape for the user message.
        if isinstance(image, bytes):
            # Detect mime with a best-effort header sniff; default jpeg.
            media_type = _sniff_image_mime(image)
            source: dict[str, Any] = {
                "type": "base64",
                "media_type": media_type,
                "data": base64.b64encode(image).decode("ascii"),
            }
        else:
            # Anthropic supports URL images in recent SDK versions via type=url.
            source = {"type": "url", "url": image}

        user_message = {
            "role": "user",
            "content": [
                {"type": "image", "source": source},
                {"type": "text", "text": prompt},
            ],
        }

        try:
            response = await client.messages.create(
                model=model,
                messages=[user_message],
                max_tokens=kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
                **kwargs,
            )
            parts: list[str] = []
            for block in response.content:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)

            usage = getattr(response, "usage", None)
            await record_usage(
                provider="anthropic",
                model=model,
                operation="vision",
                org_id=org_id,
                prompt_tokens=getattr(usage, "input_tokens", None),
                completion_tokens=getattr(usage, "output_tokens", None),
                total_tokens=(
                    (getattr(usage, "input_tokens", None) or 0)
                    + (getattr(usage, "output_tokens", None) or 0)
                    if usage else None
                ),
            )
            return "\n".join(parts).strip()
        except AnthropicAPIError as exc:
            logger.error("Anthropic analyze_image failed: %s", exc)
            raise LLMAPIError("anthropic", str(exc)) from exc

    async def chat_completion_stream(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ):
        """Stream via Anthropic's `messages.stream(...)` context manager.

        Each text delta is yielded as it arrives. Usage counts are available
        on the final `message` object — recorded once at end-of-stream.
        """
        from ..usage import record_usage

        client = self._client_for(api_key)
        system_prompt, conversation = _split_system_and_messages(messages)

        prompt_tokens = completion_tokens = total_tokens = None
        try:
            async with client.messages.stream(
                model=model,
                system=system_prompt or "",
                messages=conversation,
                temperature=temperature,
                max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                **kwargs,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    if text_chunk:
                        yield text_chunk
                final_message = await stream.get_final_message()
                usage = getattr(final_message, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "input_tokens", None)
                    completion_tokens = getattr(usage, "output_tokens", None)
                    if prompt_tokens is not None and completion_tokens is not None:
                        total_tokens = prompt_tokens + completion_tokens
        except AnthropicAPIError as exc:
            logger.error("Anthropic chat_completion_stream failed: %s", exc)
            raise LLMAPIError("anthropic", str(exc)) from exc

        await record_usage(
            provider="anthropic",
            model=model,
            operation="chat",
            org_id=org_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def close(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception as exc:  # pragma: no cover — best-effort
                logger.debug("Error closing Anthropic client: %s", exc)
        self._clients.clear()


def _sniff_image_mime(data: bytes) -> str:
    """Best-effort MIME sniff from magic bytes. Falls back to jpeg."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"GIF8":
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


register("anthropic", AnthropicProvider)
