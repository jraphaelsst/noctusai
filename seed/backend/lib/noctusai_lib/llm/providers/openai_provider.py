"""
OpenAIProvider — real implementation backed by the `openai` Python SDK.

This provider is stateless: no API key is baked in. The high-level LLM entry
points in `noctusai_lib.llm.chat` / `embeddings` / `audio` / `vision` resolve
the key via `LLMConfig.key_provider("openai", org_id)` and pass it per call.

Client pooling: we keep **one** `AsyncOpenAI` client instance for cases where
no key is passed (unusual), and create per-call clients when a specific key
is supplied. Per-call clients let us serve multiple orgs concurrently with
different keys from a single process.

Errors from the SDK surface as `LLMAPIError`. Missing keys surface as
`LLMNotConfigured`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Union

from openai import AsyncOpenAI
from openai import OpenAIError

from noctusai_lib.llm.exceptions import LLMAPIError, LLMNotConfigured
from noctusai_lib.llm.registry import register

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """Real OpenAI provider using the official `openai` SDK."""

    name = "openai"

    def __init__(self) -> None:
        # Per-key client cache so concurrent orgs share pools when they share a key.
        self._clients: dict[str, AsyncOpenAI] = {}

    def _client_for(self, api_key: str) -> AsyncOpenAI:
        if not api_key:
            raise LLMNotConfigured("openai")
        client = self._clients.get(api_key)
        if client is None:
            client = AsyncOpenAI(api_key=api_key)
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
        from noctusai_lib.llm.usage import record_usage

        client = self._client_for(api_key)
        try:
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            if response_format is not None:
                payload["response_format"] = response_format
            payload.update(kwargs)
            response = await client.chat.completions.create(**payload)
            content = response.choices[0].message.content or ""
            usage = getattr(response, "usage", None)
            await record_usage(
                provider="openai",
                model=model,
                operation="chat",
                org_id=org_id,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
            return content.strip()
        except OpenAIError as exc:
            logger.error("OpenAI chat_completion failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

    async def generate_embedding(
        self,
        text: str,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> list[float]:
        from noctusai_lib.llm.usage import record_usage

        client = self._client_for(api_key)
        try:
            response = await client.embeddings.create(
                model=model,
                input=text,
                **kwargs,
            )
            usage = getattr(response, "usage", None)
            await record_usage(
                provider="openai",
                model=model,
                operation="embedding",
                org_id=org_id,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=None,
                total_tokens=getattr(usage, "total_tokens", None),
            )
            return response.data[0].embedding
        except OpenAIError as exc:
            logger.error("OpenAI generate_embedding failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Whisper transcription. `audio` is the raw bytes of an audio file.

        The SDK expects a file-like object; we wrap the bytes in a BytesIO
        and give it a name so the multipart upload works.
        """
        import io
        from noctusai_lib.llm.usage import record_usage

        client = self._client_for(api_key)
        try:
            buf = io.BytesIO(audio)
            buf.name = kwargs.pop("filename", "audio.mp3")
            response = await client.audio.transcriptions.create(
                model=model,
                file=buf,
                **kwargs,
            )
            # Whisper doesn't return token counts — record a call with None.
            # The usage sink sees the operation happened; cost stays zero.
            await record_usage(
                provider="openai",
                model=model,
                operation="audio",
                org_id=org_id,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )
            return (response.text or "").strip()
        except OpenAIError as exc:
            logger.error("OpenAI transcribe_audio failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

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
        """Vision chat. `image` accepts either a URL string or raw bytes.

        Bytes are base64-encoded into a data URL. Uses the chat completions
        endpoint with a multi-modal user message per the OpenAI Vision spec.
        """
        import base64
        from noctusai_lib.llm.usage import record_usage

        client = self._client_for(api_key)
        if isinstance(image, bytes):
            b64 = base64.b64encode(image).decode("ascii")
            image_url = f"data:image/jpeg;base64,{b64}"
        else:
            image_url = image

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                **kwargs,
            )
            usage = getattr(response, "usage", None)
            await record_usage(
                provider="openai",
                model=model,
                operation="vision",
                org_id=org_id,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
            return (response.choices[0].message.content or "").strip()
        except OpenAIError as exc:
            logger.error("OpenAI analyze_image failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

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
        """Stream chat completion via the OpenAI `stream=True` mode.

        Yields text deltas as they arrive. Usage is still recorded at the end
        of the stream (the SDK exposes `response.usage` on the final chunk
        when `stream_options={"include_usage": True}` is set; we request it).
        """
        from noctusai_lib.llm.usage import record_usage

        client = self._client_for(api_key)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(kwargs)

        prompt_tokens = completion_tokens = total_tokens = None
        try:
            stream = await client.chat.completions.create(**payload)
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", None)
                    completion_tokens = getattr(usage, "completion_tokens", None)
                    total_tokens = getattr(usage, "total_tokens", None)
        except OpenAIError as exc:
            logger.error("OpenAI chat_completion_stream failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

        await record_usage(
            provider="openai",
            model=model,
            operation="chat",
            org_id=org_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def close(self) -> None:
        """Close every cached AsyncOpenAI client. Called on app shutdown."""
        for client in self._clients.values():
            try:
                await client.close()
            except Exception as exc:  # pragma: no cover — best-effort cleanup
                logger.debug("Error closing OpenAI client: %s", exc)
        self._clients.clear()


register("openai", OpenAIProvider)
