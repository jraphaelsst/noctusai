"""
GeminiProvider — real implementation backed by `google-genai`.

Supports:
  - Chat: via `client.aio.models.generate_content(...)`
  - Embeddings: via `client.aio.models.embed_content(model=..., contents=...)`
  - Vision: multimodal `generate_content` with image `Part`
  - Audio: multimodal input (Gemini doesn't do Whisper-style transcription;
    we send audio bytes + a transcribe prompt to the model. Works for most
    clean speech-to-text tasks.)

Translation notes (OpenAI-shaped → Gemini):
  - `system` messages are fed via the `system_instruction` config parameter.
  - `user`/`assistant` messages become alternating `role="user"`/`"model"`
    `Content` entries. Gemini uses `"model"` where OpenAI uses `"assistant"`.

SDK notes (google-genai):
  - Uses a client-centric approach: `genai.Client(api_key=...)`.
  - Async calls go through `client.aio.models.*`.
  - Configuration is passed via `types.GenerateContentConfig`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Union

from google import genai
from google.genai import types

from ..exceptions import LLMAPIError, LLMNotConfigured
from ..registry import register

logger = logging.getLogger(__name__)


def _translate_messages(messages: list[dict]) -> tuple[str, list[types.Content]]:
    """Split `system` out, rename `assistant` → `model` for the rest.

    Returns (system_instruction_text, list_of_Content_objects).
    """
    system_parts: list[str] = []
    rest: list[types.Content] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        if isinstance(content, str):
            rest.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=content)]))
        elif isinstance(content, list):
            # Already in block form — pass through as-is (callers doing vision
            # should build Gemini-shaped content parts themselves).
            rest.append(types.Content(role=gemini_role, parts=content))
    return "\n\n".join(system_parts), rest


class GeminiProvider:
    """Real Gemini provider — chat, embeddings, vision, audio."""

    name = "gemini"

    def __init__(self) -> None:
        # Per-key cache of Client instances. The new SDK is client-centric,
        # so we create one Client per API key and cache it.
        self._clients: dict[str, genai.Client] = {}

    def _get_client(self, api_key: str) -> genai.Client:
        if not api_key:
            raise LLMNotConfigured("gemini")
        if api_key not in self._clients:
            self._clients[api_key] = genai.Client(api_key=api_key)
        return self._clients[api_key]

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

        client = self._get_client(api_key)
        system_instr, conversation = _translate_messages(messages)

        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        if system_instr:
            config_kwargs["system_instruction"] = system_instr
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        ):
            config_kwargs["response_mime_type"] = "application/json"

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=conversation,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = getattr(response, "text", "") or ""
            usage = getattr(response, "usage_metadata", None)
            await record_usage(
                provider="gemini",
                model=model,
                operation="chat",
                org_id=org_id,
                prompt_tokens=getattr(usage, "prompt_token_count", None),
                completion_tokens=getattr(usage, "candidates_token_count", None),
                total_tokens=getattr(usage, "total_token_count", None),
            )
            return text.strip()
        except Exception as exc:
            logger.error("Gemini chat_completion failed: %s", exc)
            raise LLMAPIError("gemini", str(exc)) from exc

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

        client = self._get_client(api_key)
        try:
            response = await client.aio.models.embed_content(
                model=model,
                contents=text,
            )
            embedding = response.embeddings[0].values
            await record_usage(
                provider="gemini",
                model=model,
                operation="embedding",
                org_id=org_id,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
            )
            return list(embedding)
        except Exception as exc:
            logger.error("Gemini generate_embedding failed: %s", exc)
            raise LLMAPIError("gemini", str(exc)) from exc

    async def transcribe_audio(
        self,
        audio: bytes,
        *,
        model: str,
        api_key: str,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Gemini audio input — passes the audio bytes + a prompt to a
        multimodal chat model. Not a dedicated transcription API; accuracy
        depends on the model's audio competence. For production speech-to-text
        prefer OpenAI Whisper.
        """
        from ..usage import record_usage

        client = self._get_client(api_key)
        prompt = kwargs.pop(
            "prompt",
            "Transcreva o áudio em português, sem comentários adicionais.",
        )
        mime_type = kwargs.pop("mime_type", "audio/ogg")

        try:
            audio_part = types.Part.from_bytes(data=audio, mime_type=mime_type)
            text_part = types.Part.from_text(text=prompt)
            response = await client.aio.models.generate_content(
                model=model,
                contents=[audio_part, text_part],
            )
            text = getattr(response, "text", "") or ""
            usage = getattr(response, "usage_metadata", None)
            await record_usage(
                provider="gemini",
                model=model,
                operation="audio",
                org_id=org_id,
                prompt_tokens=getattr(usage, "prompt_token_count", None),
                completion_tokens=getattr(usage, "candidates_token_count", None),
                total_tokens=getattr(usage, "total_token_count", None),
            )
            return text.strip()
        except Exception as exc:
            logger.error("Gemini transcribe_audio failed: %s", exc)
            raise LLMAPIError("gemini", str(exc)) from exc

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

        client = self._get_client(api_key)
        if isinstance(image, bytes):
            mime_type = kwargs.pop("mime_type", "image/jpeg")
            image_part = types.Part.from_bytes(data=image, mime_type=mime_type)
        else:
            # URL image — Gemini SDK doesn't fetch URLs directly; the caller
            # would need to download first. We surface that contract clearly.
            raise LLMAPIError(
                "gemini",
                "URL images not supported in Gemini analyze_image — download first and pass bytes.",
            )

        try:
            text_part = types.Part.from_text(text=prompt)
            response = await client.aio.models.generate_content(
                model=model,
                contents=[image_part, text_part],
            )
            text = getattr(response, "text", "") or ""
            usage = getattr(response, "usage_metadata", None)
            await record_usage(
                provider="gemini",
                model=model,
                operation="vision",
                org_id=org_id,
                prompt_tokens=getattr(usage, "prompt_token_count", None),
                completion_tokens=getattr(usage, "candidates_token_count", None),
                total_tokens=getattr(usage, "total_token_count", None),
            )
            return text.strip()
        except Exception as exc:
            logger.error("Gemini analyze_image failed: %s", exc)
            raise LLMAPIError("gemini", str(exc)) from exc

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
        """Stream via `client.aio.models.generate_content_stream(...)`.

        Each `chunk.text` is the incremental delta. Usage metadata arrives
        on the final chunk (the SDK aggregates it); we record once at end.
        """
        from ..usage import record_usage

        client = self._get_client(api_key)
        system_instr, conversation = _translate_messages(messages)

        config_kwargs: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            config_kwargs["max_output_tokens"] = max_tokens
        if system_instr:
            config_kwargs["system_instruction"] = system_instr
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        ):
            config_kwargs["response_mime_type"] = "application/json"

        prompt_tokens = completion_tokens = total_tokens = None
        try:
            response_stream = await client.aio.models.generate_content_stream(
                model=model,
                contents=conversation,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            async for chunk in response_stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
                usage = getattr(chunk, "usage_metadata", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_token_count", None)
                    completion_tokens = getattr(usage, "candidates_token_count", None)
                    total_tokens = getattr(usage, "total_token_count", None)
        except Exception as exc:
            logger.error("Gemini chat_completion_stream failed: %s", exc)
            raise LLMAPIError("gemini", str(exc)) from exc

        await record_usage(
            provider="gemini",
            model=model,
            operation="chat",
            org_id=org_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    async def close(self) -> None:  # pragma: no cover — no resources to release
        self._clients.clear()


register("gemini", GeminiProvider)
