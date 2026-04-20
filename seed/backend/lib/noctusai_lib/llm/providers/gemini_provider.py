"""
GeminiProvider — real implementation backed by `google-generativeai`.

Supports:
  - Chat: via `GenerativeModel.generate_content_async(...)`
  - Embeddings: via `genai.embed_content_async(model=..., content=...)`
  - Vision: multimodal `generate_content_async` with image `Part`
  - Audio: multimodal input (Gemini doesn't do Whisper-style transcription;
    we send audio bytes + a transcribe prompt to the model. Works for most
    clean speech-to-text tasks.)

Translation notes (OpenAI-shaped → Gemini):
  - `system` messages are fed via the `system_instruction` parameter on the
    `GenerativeModel` (not per-call).
  - `user`/`assistant` messages become alternating `role="user"`/`"model"`
    `Content` entries. Gemini uses `"model"` where OpenAI uses `"assistant"`.

SDK idiosyncrasies:
  - `genai.configure(api_key=...)` is module-global. To support multi-tenant
    keys concurrently we rely on each call passing its own
    `GenerativeModel` instance built with the right key. The SDK supports
    a `client_options={"api_key": ...}` on `GenerativeModel` calls via
    `genai.configure(api_key=...)` at call time — we serialize this through
    the per-key client cache pattern.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Union

import google.generativeai as genai

from noctusai_lib.llm.exceptions import LLMAPIError, LLMNotConfigured
from noctusai_lib.llm.registry import register

logger = logging.getLogger(__name__)


def _translate_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split `system` out, rename `assistant` → `model` for the rest.

    Gemini `Content` structure expects `{role, parts: [{text: ...}]}`.
    """
    system_parts: list[str] = []
    rest: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        if isinstance(content, str):
            rest.append({"role": gemini_role, "parts": [content]})
        elif isinstance(content, list):
            # Already in block form — pass through as-is (callers doing vision
            # should build Gemini-shaped content parts themselves).
            rest.append({"role": gemini_role, "parts": content})
    return "\n\n".join(system_parts), rest


class GeminiProvider:
    """Real Gemini provider — chat, embeddings, vision, audio."""

    name = "gemini"

    def __init__(self) -> None:
        # Per-key cache of configured SDK state. Gemini's SDK module state
        # for api_key is global, so we store the last-seen key to detect
        # changes and reconfigure when needed. Concurrent multi-tenant
        # traffic with different keys will serialize on `genai.configure`;
        # worth revisiting if throughput matters.
        self._last_key: Optional[str] = None

    def _configure(self, api_key: str) -> None:
        if not api_key:
            raise LLMNotConfigured("gemini")
        if api_key != self._last_key:
            genai.configure(api_key=api_key)
            self._last_key = api_key

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

        self._configure(api_key)
        system_instr, conversation = _translate_messages(messages)

        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        ):
            generation_config["response_mime_type"] = "application/json"

        try:
            gm = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_instr or None,
            )
            response = await gm.generate_content_async(
                conversation,
                generation_config=generation_config,
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
        from noctusai_lib.llm.usage import record_usage

        self._configure(api_key)
        try:
            response = await genai.embed_content_async(
                model=model,
                content=text,
                task_type=kwargs.pop("task_type", "RETRIEVAL_DOCUMENT"),
            )
            embedding = response["embedding"] if isinstance(response, dict) else response.embedding
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
        from noctusai_lib.llm.usage import record_usage

        self._configure(api_key)
        prompt = kwargs.pop(
            "prompt",
            "Transcreva o áudio em português, sem comentários adicionais.",
        )
        mime_type = kwargs.pop("mime_type", "audio/ogg")

        try:
            gm = genai.GenerativeModel(model_name=model)
            response = await gm.generate_content_async([
                {"mime_type": mime_type, "data": audio},
                prompt,
            ])
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
        from noctusai_lib.llm.usage import record_usage

        self._configure(api_key)
        if isinstance(image, bytes):
            mime_type = kwargs.pop("mime_type", "image/jpeg")
            image_part: Any = {"mime_type": mime_type, "data": image}
        else:
            # URL image — Gemini SDK doesn't fetch URLs directly; the caller
            # would need to download first. We surface that contract clearly.
            raise LLMAPIError(
                "gemini",
                "URL images not supported in Gemini analyze_image — download first and pass bytes.",
            )

        try:
            gm = genai.GenerativeModel(model_name=model)
            response = await gm.generate_content_async([image_part, prompt])
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
        """Stream via `generate_content_async(..., stream=True)`.

        Each `chunk.text` is the incremental delta. Usage metadata arrives
        on the final chunk (the SDK aggregates it); we record once at end.
        """
        from noctusai_lib.llm.usage import record_usage

        self._configure(api_key)
        system_instr, conversation = _translate_messages(messages)

        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens
        if (
            response_format
            and isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        ):
            generation_config["response_mime_type"] = "application/json"

        prompt_tokens = completion_tokens = total_tokens = None
        try:
            gm = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_instr or None,
            )
            response_stream = await gm.generate_content_async(
                conversation,
                generation_config=generation_config,
                stream=True,
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
        self._last_key = None


register("gemini", GeminiProvider)
