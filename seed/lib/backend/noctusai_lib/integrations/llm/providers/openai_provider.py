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

from ..exceptions import LLMAPIError, LLMNotConfigured
from ..registry import register

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
        from ..usage import record_usage

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
                model_version=getattr(response, "model", None),
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
        from ..usage import record_usage
        from noctusai_lib.integrations import rate_limit

        client = self._client_for(api_key)
        # Pace embeds through the shared "openai_embed" bucket so a
        # cache-refresh loop can't burst into OpenAI's 429s (the SDK's own
        # retries then storm until the caller hangs — the bless-hang of
        # 2026-07-24). Async-safe; never blocks the event loop.
        await rate_limit.acquire_async("openai_embed")
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
                model_version=getattr(response, "model", None),
            )
            return response.data[0].embedding
        except OpenAIError as exc:
            logger.error("OpenAI generate_embedding failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> list[list[float]]:
        """Embed MANY texts in ONE OpenAI API call — the embeddings endpoint
        accepts an array ``input`` natively (up to 2048 items/request). This
        is the root fix for the 2026-08 pre-push retry-storm: the cache
        refresh loops used to call ``generate_embedding`` once PER CHUNK
        (508 chunks -> 508 requests, each independently paced+retried),
        which self-inflicted 429s even though the account and OpenAI itself
        were healthy throughout. One request for N chunks means N/batch_size
        requests instead of N — the caller (the embed-corpus refresh loops)
        owns the batch SIZE; this method just embeds whatever list it's
        given in a single round-trip.

        Order-preserving: OpenAI's ``/embeddings`` response is index-ordered
        to match the request's ``input`` array 1:1 (documented API
        contract) — sorted defensively here rather than trusted blindly.
        """
        from ..usage import record_usage
        from noctusai_lib.integrations import rate_limit

        if not texts:
            return []
        client = self._client_for(api_key)
        # ONE pacing token for the WHOLE batch — it is one HTTP request
        # regardless of how many texts ride inside it.
        await rate_limit.acquire_async("openai_embed")
        try:
            response = await client.embeddings.create(
                model=model,
                input=texts,
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
                model_version=getattr(response, "model", None),
            )
            ordered = sorted(response.data, key=lambda d: d.index)
            return [d.embedding for d in ordered]
        except OpenAIError as exc:
            logger.error(
                "OpenAI generate_embeddings_batch failed (%d texts): %s",
                len(texts), exc,
            )
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
        from ..usage import record_usage

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
            # `response.model` is also absent on the basic-format Whisper
            # response (only `verbose_json` carries extra fields) — the
            # `getattr` default keeps this safe either way.
            await record_usage(
                provider="openai",
                model=model,
                operation="audio",
                org_id=org_id,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                model_version=getattr(response, "model", None),
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
        from ..usage import record_usage

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
                model_version=getattr(response, "model", None),
            )
            return (response.choices[0].message.content or "").strip()
        except OpenAIError as exc:
            logger.error("OpenAI analyze_image failed: %s", exc)
            raise LLMAPIError("openai", str(exc)) from exc

    async def analyze_images(
        self,
        images: list[Union[bytes, str]],
        prompt: str,
        *,
        response_schema: dict,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        """Multi-image vision analysis constrained to a strict JSON schema.

        Unblocks S3b (the image_edit organ) and structured cost accounting:
        callers get a parsed dict guaranteed to conform to `response_schema`
        instead of free text they'd have to parse/validate themselves. Each
        entry in `images` becomes its own `image_url` content block in ONE
        user message — the model reasons over the whole set together, which
        is the point (comparing/aligning several images), not N independent
        single-image calls.

        Uses OpenAI Structured Outputs (`response_format={"type":
        "json_schema", ...}` with `"strict": True`) rather than the looser
        `{"type": "json_object"}` mode used elsewhere in the fleet — strict
        mode has the SDK/model enforce the schema server-side instead of the
        caller hoping the model's free-form JSON happens to match.

        `response_schema` is the bare JSON Schema `schema` object (no outer
        `{"type": "json_schema", ...}` envelope — this method builds that).
        An optional `schema_name` kwarg (popped before forwarding the rest
        of `**kwargs` to the SDK) names it; defaults to "image_analysis".

        Raises:
            LLMAPIError: the SDK call failed, OR the model's response body
                wasn't valid JSON (structured-output mode should prevent
                the latter, but a caller must never trust that blindly).
        """
        import json

        from ..inputs import image_bytes_to_data_url
        from ..usage import record_usage

        client = self._client_for(api_key)
        schema_name = kwargs.pop("schema_name", "image_analysis")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            if isinstance(image, bytes):
                image_url = image_bytes_to_data_url(image, "image/jpeg")
            else:
                image_url = image
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "schema": response_schema,
                        "strict": True,
                    },
                },
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
                model_version=getattr(response, "model", None),
            )
        except OpenAIError as exc:
            logger.error(
                "OpenAI analyze_images failed (%d images): %s", len(images), exc,
            )
            raise LLMAPIError("openai", str(exc)) from exc

        raw = (response.choices[0].message.content or "").strip()
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("OpenAI analyze_images returned invalid JSON: %s", exc)
            raise LLMAPIError(
                "openai", f"analyze_images returned invalid JSON: {exc}"
            ) from exc

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
        from ..usage import record_usage

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
        model_version = None
        try:
            stream = await client.chat.completions.create(**payload)
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                model_version = getattr(chunk, "model", None) or model_version
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
            model_version=model_version,
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
