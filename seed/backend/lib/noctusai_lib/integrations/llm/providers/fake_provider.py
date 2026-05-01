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
from typing import Any, Deque, Iterable, List, Optional, Union


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
        stream_responses: Optional[Iterable[List[str]]] = None,
    ) -> None:
        self._chat: Deque[str] = deque(chat_responses or [])
        self._embeddings: Deque[List[float]] = deque(embedding_responses or [])
        self._transcriptions: Deque[str] = deque(transcription_responses or [])
        self._visions: Deque[str] = deque(vision_responses or [])
        # Each stream_response is a list of chunks — e.g. [["Hel", "lo", " world"]].
        # The outer deque.popleft() returns one full scripted stream per call.
        self._streams: Deque[List[str]] = deque(stream_responses or [])

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
        image: Union[bytes, str],
        prompt: str,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> str:
        self._record(
            "analyze_image",
            image_type=type(image).__name__,
            prompt=prompt,
            model=model,
            api_key=api_key,
        )
        if self._visions:
            return self._visions.popleft()
        return f"[FAKE] default vision response for prompt: {prompt!r}"

    async def chat_completion_stream(
        self,
        messages: list[dict],
        *,
        model: str,
        api_key: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
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
        for chunk in chunks:
            yield chunk

    async def close(self) -> None:
        # Nothing to close; FakeProvider holds no resources.
        self._record("close")
