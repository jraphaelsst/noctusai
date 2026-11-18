"""elevenlabs.voice.* — list/get (read), clone_instant + delete (confirm-gated)."""
from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from _kit.transport import encode_multipart

from .. import api
from ..paths import ensure_not_committable
from ..types import (
    CloneInput, CloneOutput, VoiceDeleteInput, VoiceDeleteOutput,
    VoiceGetInput, VoiceGetOutput, VoiceListInput, VoiceListOutput,
)
from ._common import ctx

logger = logging.getLogger(__name__)

_MIN_CONSENT_LEN = 6
_MAX_SAMPLE_BYTES = 25 * 1024 * 1024


def _slim_voice(v: dict) -> dict:
    return {k: v.get(k) for k in (
        "voice_id", "name", "category", "labels", "description", "preview_url",
        "is_owner", "verified_languages", "created_at_unix") if k in v}


async def voice_list(args: dict) -> dict:
    inp = VoiceListInput(**args)
    try:
        d = api.request_json("GET", "/v2/voices", params={
            "search": inp.search, "voice_type": inp.voice_type, "category": inp.category,
            "page_size": inp.page_size, "next_page_token": inp.next_page_token,
            "include_total_count": "false"}, **ctx())
    except api.ElevenLabsApiError as e:
        return VoiceListOutput(error=typed_error(e)).model_dump()
    d = d if isinstance(d, dict) else {}
    out = VoiceListOutput(
        voices=[_slim_voice(v) for v in d.get("voices") or [] if isinstance(v, dict)],
        has_more=d.get("has_more"), next_page_token=d.get("next_page_token"))
    if inp.include_library:
        try:
            lib = api.request_json("GET", "/v1/shared-voices", params={
                "search": inp.search, "category": inp.category if inp.category in
                ("professional", "famous", "high_quality") else None,
                "page_size": min(inp.page_size, 30)}, **ctx())
            out.library_voices = [
                {k: v.get(k) for k in ("voice_id", "public_owner_id", "name", "category", "language",
                                       "accent", "gender", "age", "description", "preview_url",
                                       "is_added_by_user")}
                for v in (lib or {}).get("voices") or [] if isinstance(v, dict)]
        except api.ElevenLabsApiError as e:
            out.library_error = typed_error(e)
    return out.model_dump()


async def voice_get(args: dict) -> dict:
    inp = VoiceGetInput(**args)
    try:
        d = api.request_json("GET", f"/v1/voices/{inp.voice_id}", **ctx())
    except api.ElevenLabsApiError as e:
        return VoiceGetOutput(error=typed_error(e)).model_dump()
    return VoiceGetOutput(voice=d if isinstance(d, dict) else None).model_dump()


def _refuse(out_cls, err: Exception) -> dict:
    return out_cls(error=typed_error(err)).model_dump()


async def voice_clone_instant(args: dict) -> dict:
    inp = CloneInput(**args)
    # 1. Consent first — before the confirm gate, so the message is never skipped.
    if len((inp.consent_reference or "").strip()) < _MIN_CONSENT_LEN:
        return _refuse(CloneOutput, api.RefusedError(
            "consent_reference is required: a real person's voice needs their documented consent. "
            "Pass the path/ID of the signed consent term. NO call was made."))
    if not inp.confirm:
        return _refuse(CloneOutput, api.ConfirmationRequiredError(
            "elevenlabs.voice.clone_instant",
            "uploads voice samples to ElevenLabs and creates a voice in the account"))
    try:
        files = []
        for raw in inp.sample_paths:
            p = ensure_not_committable(raw, what="voice sample")
            if not p.is_file():
                raise api.RefusedError(f"voice sample {str(p)!r} does not exist or is not a file.")
            if p.stat().st_size > _MAX_SAMPLE_BYTES:
                raise api.RefusedError(f"voice sample {p.name!r} exceeds {_MAX_SAMPLE_BYTES // 2**20} MB.")
            mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            files.append(("files", p.name, p.read_bytes(), mime))
        fields = {"name": inp.name, "description": inp.description,
                  "remove_background_noise": "true" if inp.remove_background_noise else None,
                  "labels": json.dumps(inp.labels) if inp.labels else None}
        payload, _ = api.request_bytes(
            "POST", "/v1/voices/add", raw_body=encode_multipart(fields, files), **ctx())
    except api.ElevenLabsApiError as e:
        return _refuse(CloneOutput, e)
    try:
        d = json.loads(payload.decode("utf-8") or "{}")
    except ValueError:
        return _refuse(CloneOutput, api.ElevenLabsApiError("voices/add returned non-JSON", status=502))
    logger.info("voice cloned (consent ref recorded by caller)")
    return CloneOutput(
        cloned=True, voice_id=d.get("voice_id"),
        requires_verification=d.get("requires_verification"),
        library_voice_match=d.get("library_voice_match"),
        consent_reference=inp.consent_reference).model_dump()


async def voice_delete(args: dict) -> dict:
    inp = VoiceDeleteInput(**args)
    if not inp.confirm:
        return _refuse(VoiceDeleteOutput, api.ConfirmationRequiredError(
            "elevenlabs.voice.delete", "permanently deletes the voice from the account"))
    try:
        d = api.request_json("DELETE", f"/v1/voices/{inp.voice_id}", **ctx())
    except api.ElevenLabsApiError as e:
        return _refuse(VoiceDeleteOutput, e)
    status = d.get("status") if isinstance(d, dict) else None
    return VoiceDeleteOutput(deleted=status == "ok", voice_id=inp.voice_id, status=status).model_dump()


HANDLERS = {
    "elevenlabs.voice.list": voice_list,
    "elevenlabs.voice.get": voice_get,
    "elevenlabs.voice.clone_instant": voice_clone_instant,
    "elevenlabs.voice.delete": voice_delete,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="elevenlabs.voice.list",
             description="List voices the account can use (own, cloned, saved, shared-to-account); "
             "include_library=true also searches the public Voice Library. READ-ONLY.",
             inputSchema=VoiceListInput.model_json_schema()),
        Tool(name="elevenlabs.voice.get",
             description="One voice: settings, labels, languages, sharing. READ-ONLY.",
             inputSchema=VoiceGetInput.model_json_schema()),
        Tool(name="elevenlabs.voice.clone_instant",
             description="Create an instant voice clone from sample files. REQUIRES consent_reference "
             "(documented consent of the voice's owner) AND confirm=true (412). Samples must be outside "
             "the repo (or git-ignored).",
             inputSchema=CloneInput.model_json_schema()),
        Tool(name="elevenlabs.voice.delete",
             description="Delete a voice (e.g. revoked consent). IRREVERSIBLE — confirm-gated (412).",
             inputSchema=VoiceDeleteInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
