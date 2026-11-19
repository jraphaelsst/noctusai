"""Pydantic In/Out schemas for the ElevenLabs connector tools."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

_VOICE_ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False/omitted returns status 412 and "
        "performs NO side-effect (for TTS: an estimate + current balance instead)."
    ),
)


def check_voice_id(v: str) -> str:
    if not _VOICE_ID.match(v or ""):
        raise ValueError("voice_id must be 6-64 chars of [A-Za-z0-9_-]")
    return v


class _Err(BaseModel):
    error: Optional[dict] = None


# ─── user.usage ──────────────────────────────────────────────────────────


class UsageInput(BaseModel):
    """Subscription tier + character/credit balance. PURE read."""


class UsageOutput(_Err):
    tier: Optional[str] = None
    status: Optional[str] = None
    character_count: Optional[int] = Field(None, description="Used in the current period.")
    character_limit: Optional[int] = None
    remaining: Optional[int] = None
    next_reset_unix: Optional[int] = None
    voice_slots_used: Optional[int] = None
    voice_limit: Optional[int] = None
    can_use_instant_voice_cloning: Optional[bool] = None


# ─── model.list ──────────────────────────────────────────────────────────


class ModelListInput(BaseModel):
    tts_only: bool = Field(True, description="Only models that can do text-to-speech.")
    language: Optional[str] = Field(
        None, description="Keep models supporting this language_id (e.g. 'pt')."
    )


class ModelListOutput(_Err):
    models: List[dict] = Field(default_factory=list)


# ─── voice.list / voice.get ──────────────────────────────────────────────


class VoiceListInput(BaseModel):
    search: Optional[str] = Field(None, description="Name/description/label filter.")
    voice_type: Optional[str] = Field(
        None, description="personal | community | default | workspace | non-default | "
        "non-community | saved. Omit for everything the account can use.")
    category: Optional[str] = Field(None, description="premade | cloned | generated | professional")
    page_size: int = Field(30, ge=1, le=100)
    next_page_token: Optional[str] = None
    include_library: bool = Field(
        False, description="Also search the public Voice Library (shared voices) — "
        "`GET /v1/shared-voices` — for the same `search` text.")


class VoiceListOutput(_Err):
    voices: List[dict] = Field(default_factory=list)
    has_more: Optional[bool] = None
    next_page_token: Optional[str] = None
    library_voices: List[dict] = Field(default_factory=list)
    library_error: Optional[dict] = None


class VoiceGetInput(BaseModel):
    voice_id: str

    @field_validator("voice_id")
    @classmethod
    def _vid(cls, v: str) -> str:
        return check_voice_id(v)


class VoiceGetOutput(_Err):
    voice: Optional[dict] = None


# ─── tts.synthesize ──────────────────────────────────────────────────────


class VoiceSettings(BaseModel):
    stability: Optional[float] = Field(None, ge=0, le=1)
    similarity_boost: Optional[float] = Field(None, ge=0, le=1)
    style: Optional[float] = Field(None, ge=0, le=1)
    speed: Optional[float] = Field(None, ge=0.5, le=2.0)
    use_speaker_boost: Optional[bool] = None


class SynthesizeInput(BaseModel):
    """Text to speech. SPENDS CREDITS — confirm-gated."""

    text: str = Field(..., min_length=1)
    voice_id: str
    model_id: str = Field("eleven_multilingual_v2", description="Use elevenlabs.model.list; pt-BR needs a multilingual model.")
    voice_settings: Optional[VoiceSettings] = None
    output_format: str = Field("mp3_44100_128", description="codec_samplerate_bitrate, e.g. mp3_44100_128, wav_44100 (tier-gated).")
    output_path: Optional[str] = Field(
        None, description="ABSOLUTE file path to write. Omit => <ELEVENLABS_OUTPUT_DIR or "
        "~/.noctusai/private/elevenlabs>/<YYYY-MM-DD>/<slug>.<ext>. Refused if inside the repo and not git-ignored.")
    language_code: Optional[str] = Field(None, description="ISO 639-1; ignored by multilingual_v2.")
    seed: Optional[int] = Field(None, ge=0, le=4294967295)
    timestamps: bool = Field(True, description="Use the with-timestamps endpoint and save word timings JSON next to the audio.")
    zero_retention: Optional[bool] = Field(
        None, description="Override ELEVENLABS_ZERO_RETENTION for this call (enable_logging=false needs an enterprise plan).")
    confirm: bool = _CONFIRM

    @field_validator("voice_id")
    @classmethod
    def _vid(cls, v: str) -> str:
        return check_voice_id(v)

    @field_validator("model_id")
    @classmethod
    def _m(cls, v: str) -> str:
        if not _MODEL_ID.match(v):
            raise ValueError("invalid model_id")
        return v

    @field_validator("output_format")
    @classmethod
    def _f(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_]{5,32}$", v):
            raise ValueError("invalid output_format")
        return v


class SynthesizeOutput(_Err):
    generated: bool = False
    audio_path: Optional[str] = None
    timings_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    duration_source: Optional[str] = None
    characters: Optional[int] = None
    characters_billed: Optional[int] = None
    characters_billed_source: Optional[str] = None
    request_id: Optional[str] = None
    bytes_written: Optional[int] = None
    word_count: Optional[int] = None
    # estimate path (confirm=false)
    estimate: Optional[Dict[str, Any]] = None
    balance: Optional[Dict[str, Any]] = None


# ─── voice.clone_instant / voice.delete ──────────────────────────────────


class CloneInput(BaseModel):
    """Instant voice clone. Needs documented consent; confirm-gated."""

    name: str = Field(..., min_length=1, max_length=100)
    sample_paths: List[str] = Field(..., min_length=1, description="ABSOLUTE paths of audio samples, outside the repo (or git-ignored).")
    consent_reference: str = Field(
        "", description="REQUIRED. Path/ID of the signed consent of the person whose voice this is. "
        "A real person's voice needs their documented consent.")
    description: Optional[str] = None
    labels: Optional[Dict[str, str]] = Field(None, description="language/accent/gender/age")
    remove_background_noise: bool = False
    confirm: bool = _CONFIRM


class CloneOutput(_Err):
    cloned: bool = False
    voice_id: Optional[str] = None
    requires_verification: Optional[bool] = None
    library_voice_match: Optional[dict] = None
    consent_reference: Optional[str] = None


class VoiceDeleteInput(BaseModel):
    """Delete a voice (honour a revoked consent). Irreversible; confirm-gated."""

    voice_id: str
    confirm: bool = _CONFIRM

    @field_validator("voice_id")
    @classmethod
    def _vid(cls, v: str) -> str:
        return check_voice_id(v)


class VoiceDeleteOutput(_Err):
    deleted: bool = False
    voice_id: Optional[str] = None
    status: Optional[str] = None
