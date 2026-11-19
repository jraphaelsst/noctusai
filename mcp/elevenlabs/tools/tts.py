"""elevenlabs.tts.synthesize — text to speech with word timings.

SPENDS CREDITS ⇒ confirm-gated. Without `confirm` it returns an estimate
(characters × the model's `character_cost_multiplier`, per `GET /v1/models`)
and the current balance, and calls nothing that costs. Order of guards,
all BEFORE any spend (guards live in the seed adapter): per-call char cap → model max → balance → output-path guard.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from noctusai_lib.integrations.tts import ElevenLabsTtsClient, TtsError, TtsRefused

from ..paths import ensure_not_committable, slugify
from ..seed_shell import OPERATOR_CONSENT_REF, KitTransport, OperatorConsent
from ..settings import get_settings
from ..types import SynthesizeInput, SynthesizeOutput
from ._common import ctx

logger = logging.getLogger(__name__)

_EXT = {"mp3": "mp3", "wav": "wav", "pcm": "pcm", "opus": "opus", "ulaw": "ulaw", "alaw": "alaw"}
# seed vocabulary -> the wire labels this tool has always returned
_DUR_SRC = {"alinhamento": "alignment", "estimado_bitrate": "estimated_from_bitrate"}
_BILL_SRC = {"estimado_multiplicador": "estimated_from_model_multiplier", "indisponivel": "unavailable"}


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


async def synthesize(args: dict) -> dict:
    inp = SynthesizeInput(**args)
    s = get_settings()
    n = len(inp.text)

    def err(e: Exception, **kw) -> dict:
        if getattr(e, "codigo", None) == "texto_excede_limite":  # name the connector's knob
            e = TtsRefused(f"{e} (per-call cap = ELEVENLABS_MAX_CHARS={s.max_chars_cap})", codigo=e.codigo)
        return SynthesizeOutput(error=typed_error(e), characters=n, **kw).model_dump()

    if not s.configured:  # same typed 424 as every other tool, no HTTP
        return err(api.ElevenLabsApiError(
            "ElevenLabs connector not configured — set ELEVENLABS_API_KEY in "
            "mcp/elevenlabs/.env (or the environment).", status=424))
    client = ElevenLabsTtsClient(
        s.api_key, out_dir=s.default_output_dir, consent=OperatorConsent(), max_chars=s.max_chars_cap,
        zero_retention=s.zero_retention, transport=KitTransport(ctx), timeout=s.timeout_seconds)

    try:
        pf = client.preflight(inp.text, inp.model_id)
    except TtsError as e:
        return err(e)
    balance = {"tier": pf.tier, "remaining": pf.saldo, "character_limit": pf.limite}

    if not inp.confirm:
        return SynthesizeOutput(
            characters=n,
            estimate={"characters": n, "model_id": inp.model_id, "estimated_credits": pf.creditos_max,
                      "basis": pf.basis, "max_text_length_per_request": pf.max_texto_por_chamada},
            balance=balance,
            error=typed_error(api.ConfirmationRequiredError(
                "elevenlabs.tts.synthesize", "spends ElevenLabs credits")),
        ).model_dump()

    try:
        target = _target_path(inp)
        res = client.synthesize(
            inp.text, inp.voice_id, inp.model_id, consent_ref=OPERATOR_CONSENT_REF,
            voice_settings=inp.voice_settings.model_dump(exclude_none=True) if inp.voice_settings else None,
            output_format=inp.output_format, language_code=inp.language_code, seed=inp.seed,
            timestamps=inp.timestamps, output_path=str(target), zero_retention=inp.zero_retention, preflight=pf)
    except (TtsError, api.ElevenLabsApiError) as e:
        return err(e, balance=balance)
    return SynthesizeOutput(
        generated=True, audio_path=res.audio_path, timings_path=res.timings_path,
        duration_seconds=res.audio_s, duration_source=_DUR_SRC.get(res.audio_s_fonte, res.audio_s_fonte),
        characters=n, characters_billed=res.creditos_cobrados,
        characters_billed_source=_BILL_SRC.get(res.creditos_fonte, res.creditos_fonte),
        request_id=res.request_id, bytes_written=Path(res.audio_path).stat().st_size,
        word_count=len(res.timings) if inp.timestamps else None, balance=balance,
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
