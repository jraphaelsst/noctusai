"""
AnthropicProvider — real implementation backed by the `anthropic` SDK.

Chat + vision hit the Messages API (`client.messages.create`). Embeddings
and audio transcription are not supported by Anthropic — those methods
raise `ProviderNotImplemented` with a clear explanation pointing callers at
OpenAI / another provider.

Translation notes (OpenAI-shaped → Anthropic):
  - OpenAI's `system` role entries become Anthropic's top-level `system=`
    parameter. Any `system` messages in the list get concatenated.
  - Remaining user/assistant messages pass through unchanged — including any
    `cache_control` markers on their content blocks (`chat.
    build_cached_messages` never sets those today, but a caller hand-building
    messages can, and passthrough already preserves them for free).
  - A `system` message carrying a top-level `cache_control` key (the marker
    `chat.build_cached_messages` sets) is translated into Anthropic's
    content-block system shape — `[{"type": "text", "text": ..., "cache_control":
    {...}}]` — so the Anthropic SDK actually receives the breakpoint. A plain
    system message (no `cache_control`) still collapses to a single string,
    matching the pre-existing wire shape for every non-caching caller.
  - Vision: images are passed as content blocks inside the user message
    per the Anthropic spec (`{"type": "image", "source": {...}}`).

Client pooling mirrors the OpenAI provider — one `AsyncAnthropic` per
unique API key so multi-tenant processes don't churn connections.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional, Sequence, Union

from anthropic import AsyncAnthropic, APIError as AnthropicAPIError, APIStatusError

from ..exceptions import (
    LLMAPIError,
    LLMNotConfigured,
    ProviderNotImplemented,
    ProviderQuotaExhausted,
)
from ..registry import register
from ..stream_types import StreamOutcome
from ..tool_calling import ChatMessage, ChatToolsResponse, ToolCall, ToolSpec, build_usage
from ..vision_types import VisionResult

logger = logging.getLogger(__name__)

# Default max_tokens for Anthropic's Messages API (SDK requires it — unlike
# OpenAI which defaults). Pick a reasonable upper bound per the chat context.
_DEFAULT_MAX_TOKENS = 4096

#: Anthropic's documented per-image size ceiling for a vision content block
#: (base64-encoded bytes, i.e. what `analyze_image`'s `source.data` above
#: actually sends) — see the Vision guide's "Image requirements": an image
#: over this size is REJECTED (`request_too_large`, HTTP 413), not
#: downscaled server-side. A caller that rasterizes a page before sending it
#: (`documents.transcription.LadderDocumentTranscriber`) must stay under
#: this itself; the SDK gives no client-side pre-check.
#:
#: 🔴 MEASURED, NOT GUESSED: a naive global render-DPI bump to 400 on the
#: `identity-vision-render-dpi` finding (2026-09-23) 413'd a 2-page
#: certidão at this exact boundary — see
#: `documents.transcription.identity_document_render_dpi_policy`.
MAX_IMAGE_BYTES = 5 * 1024 * 1024


#: Anthropic reports an empty prepaid balance as HTTP 400
#: `invalid_request_error` whose message says the credit balance is too low
#: (newer API versions also use a `billing_error` type). It is permanent
#: until someone tops up, exactly like OpenAI's `insufficient_quota`.
_CREDIT_MARKERS = ("credit balance is too low", "billing_error")


def is_quota_exhausted(exc: BaseException) -> bool:
    """True when Anthropic refused for lack of credit (billing, not a rate limit)."""
    if not isinstance(exc, APIStatusError):
        return False
    if exc.status_code not in (400, 402, 403):
        return False
    body = exc.body if isinstance(exc.body, dict) else {}
    inner = body.get("error") if isinstance(body.get("error"), dict) else body
    haystack = " ".join(
        str(v) for v in (str(exc), inner.get("type"), inner.get("message")) if v
    ).lower()
    return any(marker in haystack for marker in _CREDIT_MARKERS)


def _to_llm_error(exc: AnthropicAPIError) -> LLMAPIError:
    if is_quota_exhausted(exc):
        return ProviderQuotaExhausted("anthropic", str(exc))
    return LLMAPIError("anthropic", str(exc))


def _split_system_and_messages(
    messages: list[dict],
) -> tuple[Union[str, list[dict]], list[dict]]:
    """Anthropic expects `system` as a top-level parameter, not a role.

    Concatenates all `system` messages (preserving order) and returns the
    rest. If there are no system messages, returns an empty string.

    🔴 Preserves `cache_control`. `chat.build_cached_messages(...,
    provider="anthropic")` marks its system message with a top-level
    `{"cache_control": {"type": "ephemeral"}}` key — a seed-internal
    convention, not itself valid Anthropic wire shape (Anthropic only
    recognizes `cache_control` INSIDE a system content block, never as a
    sibling of `role`/`content`). Before this function threaded that
    convention through, every Anthropic call silently dropped the marker:
    it read only `content` (str or list-of-blocks text), so a cached system
    message and an uncached one produced the identical plain string — no
    Anthropic consumer ever got a cache write, let alone a cache hit.

    When ANY system message (or one of its content blocks, for the
    already-block-shaped case) carries `cache_control`, the return value
    switches to Anthropic's content-block system shape — a list of
    `{"type": "text", "text": ..., "cache_control": {...}}` (or bare
    `{"type": "text", "text": ...}` for parts with no marker) — so the
    breakpoint reaches the SDK. Callers that never opt into caching keep
    getting the original plain string; `chat_completion`'s `system=... or
    ""` fallback treats an empty list the same as `""`.
    """
    system_parts: list[str] = []
    system_blocks: list[dict] = []
    needs_block_shape = False
    rest: list[dict] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            msg_cache_control = msg.get("cache_control")
            if isinstance(content, str):
                system_parts.append(content)
                block: dict = {"type": "text", "text": content}
                if msg_cache_control:
                    block["cache_control"] = msg_cache_control
                    needs_block_shape = True
                system_blocks.append(block)
            elif isinstance(content, list):
                # Content blocks; concat the text-block strings, and carry
                # forward any block-level cache_control the caller already set.
                for b in content:
                    if b.get("type") != "text":
                        continue
                    text = b.get("text", "")
                    system_parts.append(text)
                    block = {"type": "text", "text": text}
                    block_cache_control = b.get("cache_control")
                    if block_cache_control:
                        block["cache_control"] = block_cache_control
                        needs_block_shape = True
                    system_blocks.append(block)
        else:
            rest.append(msg)
    if needs_block_shape:
        return [b for b in system_blocks if b.get("text")], rest
    return "\n\n".join(p for p in system_parts if p), rest


# ── tool calling (chat_with_tools) — pure wire mapping ───────────────────────

_ANTHROPIC_FINISH = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
}


def to_anthropic_messages(
    messages: Sequence[ChatMessage],
) -> tuple[Union[str, list[dict]], list[dict]]:
    """Normalized messages → (`system`, Anthropic `messages`).

    System messages go through `_split_system_and_messages` (so a
    `cache=True` system message keeps its `cache_control` breakpoint).
    An assistant turn becomes text + `tool_use` blocks; consecutive `tool`
    messages merge into ONE user message of `tool_result` blocks (the API
    requires every result of an assistant turn in a single user turn).
    """
    system_dicts: list[dict] = []
    convo: list[dict] = []
    for m in messages:
        if m.role == "system":
            d: dict = {"role": "system", "content": m.content or ""}
            if m.cache:
                d["cache_control"] = {"type": "ephemeral"}
            system_dicts.append(d)
        elif m.role == "user":
            convo.append({"role": "user", "content": m.content or ""})
        elif m.role == "assistant":
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append({"type": "tool_use", "id": tc.call_id, "name": tc.name, "input": tc.arguments})
            convo.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
        else:  # tool
            block: dict = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or ""}
            if m.is_error:
                block["is_error"] = True
            prev = convo[-1] if convo else None
            if prev and prev["role"] == "user" and isinstance(prev["content"], list) and all(
                b.get("type") == "tool_result" for b in prev["content"]
            ):
                prev["content"].append(block)
            else:
                convo.append({"role": "user", "content": [block]})
    system, _ = _split_system_and_messages(system_dicts)
    return system, convo


def to_anthropic_tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]


def _anthropic_tool_choice(tool_choice: str) -> dict[str, Any]:
    return {
        "auto": {"type": "auto"},
        "none": {"type": "none"},
        "required": {"type": "any"},
    }.get(tool_choice) or {"type": "tool", "name": tool_choice}


def build_anthropic_request(
    messages: Sequence[ChatMessage],
    tools: Sequence[ToolSpec],
    *,
    model: str,
    max_tokens: Optional[int] = None,
    tool_choice: str = "auto",
) -> dict[str, Any]:
    """The exact kwargs sent to `client.messages.create` (no `temperature`:
    the SDK dropped it, see `chat_completion`)."""
    system, convo = to_anthropic_messages(messages)
    payload: dict[str, Any] = {
        "model": model,
        "system": system or "",
        "messages": convo,
        "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
    }
    if tools:
        payload["tools"] = to_anthropic_tools(tools)
        if tool_choice != "auto":
            payload["tool_choice"] = _anthropic_tool_choice(tool_choice)
    return payload


def parse_anthropic_response(response: Any, *, model: str) -> ChatToolsResponse:
    """Anthropic Messages response (SDK object) → `ChatToolsResponse`."""
    texts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        kind = getattr(block, "type", None)
        if kind == "tool_use":
            args = getattr(block, "input", None)
            calls.append(ToolCall(block.id, block.name, args if isinstance(args, dict) else {}))
        elif getattr(block, "text", None):
            texts.append(block.text)
    usage = getattr(response, "usage", None)
    finish = _ANTHROPIC_FINISH.get(getattr(response, "stop_reason", None) or "end_turn", "other")
    if calls:
        finish = "tool_calls"
    return ChatToolsResponse(
        text="\n".join(texts).strip(),
        tool_calls=tuple(calls),
        usage=build_usage(
            "anthropic",
            model,
            prompt_tokens=getattr(usage, "input_tokens", None),
            completion_tokens=getattr(usage, "output_tokens", None),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", None),
        ),
        finish_reason=finish,
        model_version=getattr(response, "model", None),
        content_raw="\n".join(texts) if texts else None,
    )


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
        #
        # `system_prompt` is now either a plain string OR a list of Anthropic
        # content blocks (the cache_control breakpoint case) — handle both so
        # a cached call doesn't crash trying to `str + list`.
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        ):
            json_instruction = (
                "Return your response as a valid JSON object. No prose outside the JSON."
            )
            if isinstance(system_prompt, list):
                # Append as an uncached trailing block — appending after the
                # cached block(s) keeps their content (and thus the cache
                # breakpoint) stable across calls; this instruction text is
                # cheap and doesn't need its own cache_control.
                system_prompt = [*system_prompt, {"type": "text", "text": json_instruction}]
            else:
                system_prompt = (
                    (system_prompt + "\n\n" if system_prompt else "") + json_instruction
                )

        try:
            response = await client.messages.create(
                model=model,
                system=system_prompt or "",
                messages=conversation,
                max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                # No `temperature`: the anthropic SDK 1.x removed it from
                # messages.create() (TypeError) and current models reject it.
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
                cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None),
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None),
            )
            return content
        except AnthropicAPIError as exc:
            logger.error("Anthropic chat_completion failed: %s", exc)
            raise _to_llm_error(exc) from exc

    async def chat_with_tools(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,  # noqa: ARG002 — SDK 1.x has no temperature
        max_tokens: Optional[int] = None,
        tool_choice: str = "auto",
        org_id: Optional[str] = None,
    ) -> ChatToolsResponse:
        """One tool-calling turn (see `tool_calling.chat_with_tools`)."""
        from ..usage import record_usage

        client = self._client_for(api_key)
        payload = build_anthropic_request(
            messages, tools, model=model, max_tokens=max_tokens, tool_choice=tool_choice
        )
        try:
            response = await client.messages.create(**payload)
        except AnthropicAPIError as exc:
            logger.error("Anthropic chat_with_tools failed: %s", exc)
            raise _to_llm_error(exc) from exc
        parsed = parse_anthropic_response(response, model=model)
        u = parsed.usage
        await record_usage(
            provider="anthropic",
            model=model,
            operation="chat",
            org_id=org_id,
            prompt_tokens=u.prompt_tokens,
            completion_tokens=u.completion_tokens,
            total_tokens=(u.prompt_tokens or 0) + (u.completion_tokens or 0)
            if u.prompt_tokens is not None or u.completion_tokens is not None else None,
            cache_creation_input_tokens=u.cache_creation_tokens,
            cache_read_input_tokens=u.cache_read_tokens,
            model_version=parsed.model_version,
        )
        return parsed

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
        image: Union[bytes, str, Sequence[Union[bytes, str]]],
        prompt: str,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        return_metadata: bool = False,
        **kwargs: Any,
    ) -> Union[str, VisionResult]:
        from ..usage import record_usage

        client = self._client_for(api_key)

        # Build the Anthropic content-block shape for the user message.
        #
        # A LIST of images is one subject in order (the bands of one page —
        # `documents.vision_tiling`): each is labelled "Image k:" before its
        # block, the form the vision guide recommends for several images
        # ("introduce each one with a short text label"), and the prompt
        # comes after them all (images-before-text is the guide's preferred
        # order). Each image is resized independently against the model's
        # native limits, so N bands keep N times the pixels of one image.
        def _bloco(img: Union[bytes, str]) -> dict[str, Any]:
            if isinstance(img, bytes):
                # Detect mime with a best-effort header sniff; default jpeg.
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _sniff_image_mime(img),
                        "data": base64.b64encode(img).decode("ascii"),
                    },
                }
            # Anthropic supports URL images in recent SDK versions via type=url.
            return {"type": "image", "source": {"type": "url", "url": img}}

        content: list[dict[str, Any]] = []
        if isinstance(image, (list, tuple)):
            for i, img in enumerate(image, 1):
                content.append({"type": "text", "text": f"Image {i}:"})
                content.append(_bloco(img))
        else:
            content.append(_bloco(image))
        content.append({"type": "text", "text": prompt})
        user_message = {"role": "user", "content": content}

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
            texto = "\n".join(parts).strip()
            if return_metadata:
                stop_reason = getattr(response, "stop_reason", None)
                return VisionResult(
                    text=texto,
                    truncated=stop_reason == "max_tokens",
                    stop_reason=stop_reason,
                )
            return texto
        except AnthropicAPIError as exc:
            logger.error("Anthropic analyze_image failed: %s", exc)
            raise _to_llm_error(exc) from exc

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
        outcome: Optional[StreamOutcome] = None,
        **kwargs: Any,
    ):
        """Stream via Anthropic's `messages.stream(...)` context manager.

        Each text delta is yielded as it arrives. Usage counts are available
        on the final `message` object — recorded once at end-of-stream.

        `system_prompt` is either a plain string or the cache_control
        content-block list from `_split_system_and_messages`; `or ""` treats
        an empty list the same as an empty string (both mean "no system").

        Cache token counts: the SDK's streaming accumulator (`anthropic.lib.
        streaming._messages`) merges `cache_creation_input_tokens` /
        `cache_read_input_tokens` into the running usage snapshot as they
        arrive on `message_start` / `message_delta` events, so
        `get_final_message().usage` already carries the fully-accumulated
        values — no separate `message_start` listener needed.
        """
        from ..usage import record_usage

        client = self._client_for(api_key)
        system_prompt, conversation = _split_system_and_messages(messages)

        prompt_tokens = completion_tokens = total_tokens = None
        cache_creation_input_tokens = cache_read_input_tokens = None
        try:
            async with client.messages.stream(
                model=model,
                system=system_prompt or "",
                messages=conversation,
                max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
                # No `temperature`: removed from messages.stream() in SDK 1.x.
                **kwargs,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    if text_chunk:
                        yield text_chunk
                final_message = await stream.get_final_message()
                if outcome is not None:
                    stop_reason = getattr(final_message, "stop_reason", None)
                    outcome.stop_reason = stop_reason
                    outcome.truncated = stop_reason == "max_tokens"
                usage = getattr(final_message, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "input_tokens", None)
                    completion_tokens = getattr(usage, "output_tokens", None)
                    if prompt_tokens is not None and completion_tokens is not None:
                        total_tokens = prompt_tokens + completion_tokens
                    cache_creation_input_tokens = getattr(usage, "cache_creation_input_tokens", None)
                    cache_read_input_tokens = getattr(usage, "cache_read_input_tokens", None)
        except AnthropicAPIError as exc:
            logger.error("Anthropic chat_completion_stream failed: %s", exc)
            raise _to_llm_error(exc) from exc

        await record_usage(
            provider="anthropic",
            model=model,
            operation="chat",
            org_id=org_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
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
