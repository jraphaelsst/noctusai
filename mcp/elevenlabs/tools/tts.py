"""elevenlabs.tts.synthesize — text to speech with word timings.

SPENDS CREDITS ⇒ confirm-gated. Without `confirm` it returns an estimate
(characters × the model's `character_cost_multiplier`, per `GET /v1/models`)
and the current balance, and calls nothing that costs. Order of guards,
all BEFORE any spend: per-call char cap → output-path guard → balance.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..paths import ensure_not_committable, slugify
from ..settings import get_settings
from ..types import SynthesizeInput, SynthesizeOutput
from ._common import ctx

logger = logging.getLogger(__name__)

_EXT = {"mp3": "mp3", "wav": "wav", "pcm": "pcm", "opus": "opus", "ulaw": "ulaw", "alaw": "alaw"}
_ZERO_RETENTION_HINT = (
    " | enable_logging=false (zero retention) is documented as enterprise-only. If your plan "
    "does not include it, retry with zero_retention=false (or ELEVENLABS_ZERO_RETENTION=false) "
    "to ACCEPT ElevenLabs request retention — a deliberate privacy decision."
)


def _words(alignment: Optional[dict]) -> list[dict]:
    """Group the character-level alignment into whitespace-separated words."""
    if not alignment:
        return []
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    out: list[dict] = []
    cur: list[int] = []

    def flush():
        if cur:
            out.append({"word": "".join(chars[i] for i in cur),
                        "start": starts[cur[0]], "end": ends[cur[-1]]})
            cur.clear()

    for i, ch in enumerate(chars):
        if i >= len(starts) or i >= len(ends):
            break
        if ch.isspace():
            flush()
        else:
            cur.append(i)
    flush()
    return out


def _duration(alignment: Optional[dict], fmt: str, nbytes: int) -> tuple[Optional[float], Optional[str]]:
    ends = (alignment or {}).get("character_end_times_seconds") or []
    if ends:
        return round(float(ends[-1]), 3), "alignment"
    m = re.match(r"^(mp3|opus)_\d+_(\d+)$", fmt)  # constant-bitrate codecs
    if m and int(m.group(2)) > 0:
        return round(nbytes * 8 / (int(m.group(2)) * 1000), 3), "estimated_from_bitrate"
    return None, None


def _target_path(inp: SynthesizeInput) -> Path:
    s = get_settings()
    ext = _EXT.get(inp.output_format.split("_")[0], "bin")
    if inp.output_path:
        p = ensure_not_committable(inp.output_path, what="output_path")
        if p.exists():
            raise api.RefusedError(f"output_path {str(p)!r} already exists; refusing to overwrite.")
        return p
    base = ensure_not_committable(
        str(s.default_output_dir.expanduser().resolve() / date.today().isoformat()),
        what="default output dir (ELEVENLABS_OUTPUT_DIR)")
    stem, n = slugify(inp.text), 0
    while True:
        p = base / f"{stem}{'' if n == 0 else f'-{n}'}.{ext}"
        if not p.exists():
            return p
        n += 1


def _model_info(model_id: str) -> Optional[dict]:
    try:
        d = api.request_json("GET", "/v1/models", **ctx())
    except api.ElevenLabsApiError:
        return None
    for m in d if isinstance(d, list) else []:
        if isinstance(m, dict) and m.get("model_id") == model_id:
            return m
    return None


def _credits(chars: int, model: Optional[dict]) -> Optional[float]:
    rates = (model or {}).get("model_rates") or {}
    mult = rates.get("character_cost_multiplier")
    if mult is None:
        return None
    return round(chars * float(mult) * float(rates.get("cost_discount_multiplier", 1) or 1), 2)


async def synthesize(args: dict) -> dict:
    inp = SynthesizeInput(**args)
    s = get_settings()
    n = len(inp.text)

    def err(e: Exception, **kw) -> dict:
        return SynthesizeOutput(error=typed_error(e), characters=n, **kw).model_dump()

    if n > s.max_chars_cap:
        return err(api.RefusedError(
            f"text is {n} chars, over the per-call cap ELEVENLABS_MAX_CHARS={s.max_chars_cap}. "
            "Split the text or raise the cap deliberately. NO call was made."))

    try:
        model = _model_info(inp.model_id)
        max_len = (model or {}).get("maximum_text_length_per_request")
        if isinstance(max_len, int) and n > max_len:
            return err(api.RefusedError(
                f"text is {n} chars; model {inp.model_id} accepts at most {max_len} per request."))
        sub = api.request_json("GET", "/v1/user/subscription", **ctx())
    except api.ElevenLabsApiError as e:
        return err(e)
    sub = sub if isinstance(sub, dict) else {}
    used, limit = sub.get("character_count"), sub.get("character_limit")
    remaining = limit - used if isinstance(used, int) and isinstance(limit, int) else None
    est = _credits(n, model)
    balance = {"tier": sub.get("tier"), "remaining": remaining, "character_limit": limit}

    if not inp.confirm:
        return SynthesizeOutput(
            characters=n,
            estimate={"characters": n, "model_id": inp.model_id, "estimated_credits": est,
                      "basis": "characters x model_rates.character_cost_multiplier (GET /v1/models)"
                      if est is not None else "multiplier unavailable — assume ~1 credit/char",
                      "max_text_length_per_request": max_len},
            balance=balance,
            error=typed_error(api.ConfirmationRequiredError(
                "elevenlabs.tts.synthesize", "spends ElevenLabs credits")),
        ).model_dump()

    if est is not None and remaining is not None and est > remaining:
        return err(api.RefusedError(
            f"estimated {est} credits exceeds the remaining balance {remaining}. NO call was made."),
            balance=balance)

    try:
        target = _target_path(inp)
    except api.ElevenLabsApiError as e:
        return err(e)

    body: dict = {"text": inp.text, "model_id": inp.model_id}
    if inp.voice_settings:
        body["voice_settings"] = inp.voice_settings.model_dump(exclude_none=True)
    if inp.language_code:
        body["language_code"] = inp.language_code
    if inp.seed is not None:
        body["seed"] = inp.seed
    zero = s.zero_retention if inp.zero_retention is None else inp.zero_retention
    path = f"/v1/text-to-speech/{inp.voice_id}" + ("/with-timestamps" if inp.timestamps else "")
    try:
        raw, hdrs = api.request_bytes(
            "POST", path, body=body,
            params={"output_format": inp.output_format,
                    "enable_logging": "false" if zero else None}, **ctx())
    except api.ElevenLabsApiError as e:
        if zero and e.status in (400, 401, 403, 422):
            e = api.ElevenLabsApiError(str(e) + _ZERO_RETENTION_HINT, status=e.status)
        return err(e, balance=balance)

    alignment = None
    try:
        if inp.timestamps:
            payload = json.loads(raw.decode("utf-8"))
            audio = base64.b64decode(payload["audio_base64"])
            alignment = payload.get("alignment") or payload.get("normalized_alignment")
        else:
            payload, audio = {}, raw
    except (ValueError, KeyError) as e:
        return err(api.ElevenLabsApiError(f"unexpected TTS response shape ({type(e).__name__})", status=502))

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(audio)
    words = _words(alignment)
    timings_path = None
    if inp.timestamps:
        timings_path = target.with_suffix(".timings.json")
        timings_path.write_text(json.dumps({
            "audio_file": target.name, "model_id": inp.model_id, "voice_id": inp.voice_id,
            "words": words, "alignment": payload.get("alignment"),
            "normalized_alignment": payload.get("normalized_alignment"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    dur, dur_src = _duration(alignment, inp.output_format, len(audio))
    hdr_cost = hdrs.get("x-character-count") or hdrs.get("character-cost")
    if hdr_cost and hdr_cost.isdigit():
        billed, src = int(hdr_cost), "response_header"
    elif est is not None:
        billed, src = int(round(est)), "estimated_from_model_multiplier"
    else:
        billed, src = None, "unavailable"
    logger.info("tts ok: %d chars -> %d bytes", n, len(audio))  # never log text or key
    return SynthesizeOutput(
        generated=True, audio_path=str(target), timings_path=str(timings_path) if timings_path else None,
        duration_seconds=dur, duration_source=dur_src, characters=n,
        characters_billed=billed, characters_billed_source=src,
        request_id=hdrs.get("request-id"), bytes_written=len(audio),
        word_count=len(words) if inp.timestamps else None, balance=balance,
    ).model_dump()


HANDLERS = {"elevenlabs.tts.synthesize": synthesize}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [Tool(
        name="elevenlabs.tts.synthesize",
        description="Text to speech (pt-BR needs a multilingual model). SPENDS CREDITS — confirm=true "
        "required; without it returns a credit estimate + balance. Writes audio (+ word-timings JSON) to "
        "output_path or the noc-level private dir; refuses repo paths that git does not ignore; "
        "per-call cap ELEVENLABS_MAX_CHARS.",
        inputSchema=SynthesizeInput.model_json_schema())]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
