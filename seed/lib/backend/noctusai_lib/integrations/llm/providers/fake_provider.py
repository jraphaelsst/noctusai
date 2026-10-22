"""
FakeProvider — scripted provider for tests.

Tests construct this directly (not via the registry — tests own their
provider instance explicitly) and pass a sequence of scripted responses
for each method. Calls consume the sequence in order; after exhaustion,
a sensible default is returned.

Intentionally NOT registered. Production code paths never touch this
provider. Tests wire it into an `LLMConfig` when they need deterministic
LLM behavior without a real API.

Usage:

    fake = FakeProvider(
        chat_responses=["first reply", "second reply"],
        embedding_responses=[[0.1, 0.2, 0.3]],
    )
    config = LLMConfig(
        key_provider=lambda p, org_id=None: "fake-key",
        provider=fake,  # see client.py — Phase 3 wires this
    )
"""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Iterable, List, Optional, Sequence, Union

from ..stream_types import StreamOutcome
from ..tool_calling import ChatMessage, ChatToolsResponse, LLMUsage, ToolCall, ToolSpec
from ..vision_types import VisionResult


class FakeProvider:
    """Scripted test double. Not registered; tests use it via LLMConfig override."""

    name = "fake"

    def __init__(
        self,
        *,
        chat_responses: Optional[Iterable[str]] = None,
        embedding_responses: Optional[Iterable[List[float]]] = None,
        transcription_responses: Optional[Iterable[str]] = None,
        vision_responses: Optional[Iterable[str]] = None,
        # Aligned by call order with `vision_responses` (own deque, same
        # convention as the other scripted-response pairs on this class) —
        # a caller scripting `return_metadata=True` truncation scenarios
        # sets this; every other caller leaves it unset and gets
        # `truncated=False`, matching a real, non-truncated reply.
        vision_truncated: Optional[Iterable[bool]] = None,
        stream_responses: Optional[Iterable[List[str]]] = None,
        # Aligned by call order with `stream_responses` — same convention as
        # `vision_truncated`. Unset ⇒ every stream reports `truncated=False`.
        stream_truncated: Optional[Iterable[bool]] = None,
        # Scripted `chat_with_tools` turns, consumed in order. Each item is a
        # `ChatToolsResponse`, a `str` (a final text turn), or a list/tuple of
        # `ToolCall` (a tool-calling turn). Exhausted ⇒ a deterministic text turn.
        tool_responses: Optional[Iterable[Union[ChatToolsResponse, str, Sequence[ToolCall]]]] = None,
        # Scripted usage of `chat_completion` calls, aligned by call order: `(prompt_tokens, completion_tokens)`.
        # Real providers record a `UsageEvent` per call; the fake does too, but ONLY when scripted
        # (`usage_provider` names the provider/catalog the cost is priced against), so every existing
        # caller keeps the no-usage behaviour.
        chat_usage: Optional[Iterable[tuple[int, int]]] = None,
        usage_provider: Optional[str] = None,
    ) -> None:
        self._chat: Deque[str] = deque(chat_responses or [])
        self._embeddings: Deque[List[float]] = deque(embedding_responses or [])
        self._transcriptions: Deque[str] = deque(transcription_responses or [])
        self._visions: Deque[str] = deque(vision_responses or [])
        self._vision_truncated: Deque[bool] = deque(vision_truncated or [])
        # Each stream_response is a list of chunks — e.g. [["Hel", "lo", " world"]].
        # The outer deque.popleft() returns one full scripted stream per call.
        self._streams: Deque[List[str]] = deque(stream_responses or [])
        self._stream_truncated: Deque[bool] = deque(stream_truncated or [])
        self._tool_turns: Deque[Union[ChatToolsResponse, str, Sequence[ToolCall]]] = deque(tool_responses or [])
        self._chat_usage: Deque[tuple[int, int]] = deque(chat_usage or [])
        self._usage_provider = usage_provider

        # Call log — tests can inspect what was called, with what args.
        self.calls: list[dict] = []

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append({"method": method, **kwargs})

    async def chat_completion(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        **kwargs: Any,
    ) -> str:
        self._record(
            "chat_completion",
            messages=messages,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        if self._usage_provider is not None:
            from ..usage import record_usage

            prompt, completion = self._chat_usage.popleft() if self._chat_usage else (0, 0)
            await record_usage(
                provider=self._usage_provider, model=model, operation="chat",
                prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion,
                org_id=kwargs.get("org_id"),
            )
        if self._chat:
            return self._chat.popleft()
        return f"[FAKE] default chat response for model={model}"

    async def generate_embedding(
        self,
        text: str,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> List[float]:
        self._record("generate_embedding", text=text, model=model, api_key=api_key)
        if self._embeddings:
            return self._embeddings.popleft()
        return [0.0] * 1536  # shape-correct default matching OpenAI small

    async def generate_embeddings_batch(
        self,
        texts: List[str],
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> List[List[float]]:
        """ONE recorded call for the whole batch — mirrors OpenAIProvider's
        real batch shape so a test can assert "N texts -> 1 call" rather than
        falling back to the high-level per-item degrade path."""
        self._record(
            "generate_embeddings_batch", texts=list(texts), model=model, api_key=api_key
        )
        out: List[List[float]] = []
        for _ in texts:
            if self._embeddings:
                out.append(self._embeddings.popleft())
            else:
                out.append([0.0] * 1536)
        return out

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> str:
        self._record(
            "transcribe_audio", bytes_len=len(audio), model=model, api_key=api_key
        )
        if self._transcriptions:
            return self._transcriptions.popleft()
        return "[FAKE] default transcription"

    async def analyze_image(
        self,
        image: Union[bytes, str, Sequence[Union[bytes, str]]],
        prompt: str,
        *,
        model: str,
        api_key: str,
        return_metadata: bool = False,
        **kwargs: Any,
    ) -> Union[str, VisionResult]:
        self._record(
            "analyze_image",
            image_type=type(image).__name__,
            # How many images one call carried (the bands of one page arrive
            # as a list — `documents.vision_tiling`); 1 for a single image.
            image_count=len(image) if isinstance(image, (list, tuple)) else 1,
            prompt=prompt,
            model=model,
            api_key=api_key,
        )
        texto = (
            self._visions.popleft()
            if self._visions
            else f"[FAKE] default vision response for prompt: {prompt!r}"
        )
        if not return_metadata:
            return texto
        truncated = self._vision_truncated.popleft() if self._vision_truncated else False
        return VisionResult(text=texto, truncated=truncated, stop_reason=None)

    async def chat_completion_stream(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
        outcome: Optional[StreamOutcome] = None,
        **kwargs: Any,
    ):
        """Async generator that yields scripted chunks from `stream_responses`.

        If no streams were scripted, yields a single default chunk. The call
        is logged with full args for test inspection.
        """
        self._record(
            "chat_completion_stream",
            messages=messages,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        if self._streams:
            chunks = self._streams.popleft()
        else:
            chunks = [f"[FAKE stream] chunk for {model}"]
        truncated = self._stream_truncated.popleft() if self._stream_truncated else False
        for chunk in chunks:
            yield chunk
        if outcome is not None:
            outcome.truncated = truncated
            outcome.stop_reason = "max_tokens" if truncated else "end_turn"

    async def chat_with_tools(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        tool_choice: str = "auto",
        org_id: Optional[str] = None,
    ) -> ChatToolsResponse:
        """Deterministic, scriptable tool-calling turn (no network, no usage
        recording). The call — including the normalized messages and tool
        specs it received — is logged on `self.calls`."""
        self._record(
            "chat_with_tools",
            messages=list(messages),
            tools=list(tools),
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            org_id=org_id,
        )
        if not self._tool_turns:
            return ChatToolsResponse(text=f"[FAKE] default tool-chat response for model={model}")
        turn = self._tool_turns.popleft()
        if isinstance(turn, ChatToolsResponse):
            return turn
        if isinstance(turn, str):
            return ChatToolsResponse(text=turn, usage=LLMUsage(0, 0, 0, 0, 0.0))
        return ChatToolsResponse(
            tool_calls=tuple(turn), finish_reason="tool_calls", usage=LLMUsage(0, 0, 0, 0, 0.0)
        )

    async def close(self) -> None:
        # Nothing to close; FakeProvider holds no resources.
        self._record("close")
