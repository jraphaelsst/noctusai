"""
High-level audio transcription entry point.

Wraps the active provider's `transcribe_audio`. Today only OpenAI has a real
body (Whisper); Anthropic / Gemini stubs raise `ProviderNotImplemented`
unless the dev guard is set. Defaults to `provider="openai"` because that's
the only real audio provider — services overriding would be rare.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.llm.client import get_llm_config, get_provider, resolve_api_key


async def transcribe_audio(
    audio: bytes,
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    org_id: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Transcribe audio bytes to text via the configured provider.

    Args:
        audio: Raw audio file bytes (mp3, wav, m4a, webm, etc.).
        model: Override the audio model. Defaults to `LLMConfig.default_audio_model`.
        provider: Override the active provider. Today only `"openai"` has a
            real body — stubs raise ProviderNotImplemented unless the dev
            flag is set.
        org_id: Scope the key resolution to a specific org.
        **kwargs: Forwarded (e.g. `filename="audio.m4a"` to set the upload name).

    Returns:
        The transcribed text.

    Raises:
        LLMNotConfigured: API key missing.
        LLMAPIError: Downstream error.
        ProviderNotImplemented: Stub provider without dev flag set.
    """
    config = get_llm_config()
    # Audio defaults to OpenAI because Whisper is the only real body today.
    # Overriding to a stub provider without the dev flag will raise loudly —
    # that's intentional.
    effective_provider = provider or config.default_provider
    effective_model = model or config.default_audio_model
    api_key = resolve_api_key(effective_provider, org_id)

    prov = get_provider(effective_provider)
    return await prov.transcribe_audio(
        audio,
        model=effective_model,
        api_key=api_key,
        org_id=org_id,
        **kwargs,
    )
