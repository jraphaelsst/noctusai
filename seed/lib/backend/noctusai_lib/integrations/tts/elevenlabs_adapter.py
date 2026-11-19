"""Real ElevenLabs adapter (text-to-speech with word timings + instant clone).

The single implementation: `mcp/elevenlabs/` is a thin shell over this class.
Guards, all BEFORE any spend: consent -> per-call char cap -> model max length
-> balance. Nothing here logs the text or the key.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional

from noctusai_lib.integrations.tts.alignment import (
    creditos_cobrados,
    creditos_estimados,
    duracao,
    palavras_do_alinhamento,
)
from noctusai_lib.integrations.tts.transport import DEFAULT_BASE_URL, HttpxTransport, Transport
from noctusai_lib.integrations.tts.types import (
    CloneResult,
    ConsentChecker,
    ConsentimentoAusente,
    Preflight,
    TtsRefused,
    TtsResult,
    TtsUpstreamError,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 5000
_EXT = {"mp3": "mp3", "wav": "wav", "pcm": "pcm", "opus": "opus", "ulaw": "ulaw", "alaw": "alaw"}
_MAX_SAMPLE_BYTES = 25 * 1024 * 1024
ZERO_RETENTION_HINT = (
    " | enable_logging=false (zero retention) is documented as enterprise-only. If your plan "
    "does not include it, retry with zero_retention=false to ACCEPT ElevenLabs request retention "
    "-- a deliberate privacy decision."
)


def exigir_consentimento(consent: Optional[ConsentChecker], org: Optional[str], chave: str, consent_ref: str) -> None:
    """Shared by Real and Fake: refuse (`consentimento_ausente`) unless a reference was given AND the
    product's checker says the consent is in force. No checker = no authority to speak = refuse."""
    if not (consent_ref or "").strip() or consent is None or not consent.vigente(org, chave):
        raise ConsentimentoAusente()


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return s or "audio"


def destino(out_dir: Path, text: str, ext: str, output_path: Optional[str]) -> Path:
    if output_path:
        p = Path(output_path)
        if p.exists():
            raise TtsRefused(f"output_path {str(p)!r} already exists; refusing to overwrite.", codigo="destino_existe")
        return p
    stem, n = slug(text), 0
    while True:
        p = out_dir / f"{stem}{'' if n == 0 else f'-{n}'}.{ext}"
        if not p.exists():
            return p
        n += 1


class ElevenLabsTtsClient:
    def __init__(
        self,
        api_key: Optional[str],
        *,
        out_dir: Path,
        org_id: Optional[str] = None,
        consent: Optional[ConsentChecker] = None,
        base_url: str = DEFAULT_BASE_URL,
        max_chars: int = DEFAULT_MAX_CHARS,
        zero_retention: bool = True,
        transport: Optional[Transport] = None,
        timeout: float = 120.0,
    ) -> None:
        self._org = org_id
        self._consent = consent
        self._out_dir = Path(out_dir)
        self._max_chars = max_chars
        self._zero = zero_retention
        self._timeout = timeout
        self._t: Transport = transport or HttpxTransport(api_key, base_url=base_url)

    # ── reads ────────────────────────────────────────────────────────────
    def model_info(self, model: str) -> Optional[dict]:
        d = self._t.json("GET", "/v1/models", timeout=20.0)
        for m in d if isinstance(d, list) else []:
            if isinstance(m, dict) and m.get("model_id") == model:
                return m
        return None

    def subscription(self) -> dict:
        d = self._t.json("GET", "/v1/user/subscription", timeout=20.0)
        return d if isinstance(d, dict) else {}

    def preflight(self, text: str, model: str) -> Preflight:
        n = len(text)
        if n > self._max_chars:
            raise TtsRefused(
                f"text is {n} chars, over the per-call cap {self._max_chars}. Split the text or raise the "
                "cap deliberately. NO call was made.", codigo="texto_excede_limite")
        info = self.model_info(model)
        max_len = (info or {}).get("maximum_text_length_per_request")
        if isinstance(max_len, int) and n > max_len:
            raise TtsRefused(f"text is {n} chars; model {model} accepts at most {max_len} per request.",
                             codigo="texto_excede_modelo")
        sub = self.subscription()
        used, limit = sub.get("character_count"), sub.get("character_limit")
        saldo = limit - used if isinstance(used, int) and isinstance(limit, int) else None
        est = creditos_estimados(n, info)
        basis = ("characters x model_rates.character_cost_multiplier (GET /v1/models)" if est is not None
                 else "multiplier unavailable -- assume ~1 credit/char")
        return Preflight(n, model, est, max_len if isinstance(max_len, int) else None, saldo,
                         tier=sub.get("tier"), limite=limit if isinstance(limit, int) else None, basis=basis)

    def estimate(self, text: str, model: str) -> Optional[float]:
        """Max credits a synthesize of `text` can bill; ~1 credit/char when the model's multiplier is unknown."""
        est = creditos_estimados(len(text), self.model_info(model))
        return est if est is not None else float(len(text))

    # ── writes ───────────────────────────────────────────────────────────
    def synthesize(
        self,
        text: str,
        voice_id: str,
        model: str,
        *,
        consent_ref: str,
        voice_settings: Optional[dict] = None,
        output_format: str = "mp3_44100_128",
        language_code: Optional[str] = None,
        seed: Optional[int] = None,
        timestamps: bool = True,
        output_path: Optional[str] = None,
        zero_retention: Optional[bool] = None,
        preflight: Optional[Preflight] = None,
    ) -> TtsResult:
        exigir_consentimento(self._consent, self._org, voice_id, consent_ref)
        pf = preflight or self.preflight(text, model)
        if pf.creditos_max is not None and pf.saldo is not None and pf.creditos_max > pf.saldo:
            raise TtsRefused(f"estimated {pf.creditos_max} credits exceeds the remaining balance {pf.saldo}. "
                             "NO call was made.", codigo="saldo_insuficiente")
        ext = _EXT.get(output_format.split("_")[0], "bin")
        target = destino(self._out_dir, text, ext, output_path)

        body: dict = {"text": text, "model_id": model}
        if voice_settings:
            body["voice_settings"] = voice_settings
        if language_code:
            body["language_code"] = language_code
        if seed is not None:
            body["seed"] = seed
        zero = self._zero if zero_retention is None else zero_retention
        path = f"/v1/text-to-speech/{voice_id}" + ("/with-timestamps" if timestamps else "")
        try:
            raw, hdrs = self._t.bytes(
                "POST", path, body=body,
                params={"output_format": output_format, "enable_logging": "false" if zero else None},
                timeout=self._timeout)
        except TtsUpstreamError as e:
            if zero and e.status in (400, 401, 403, 422):
                raise TtsUpstreamError(str(e) + ZERO_RETENTION_HINT, status=e.status) from e
            raise

        alignment = payload = None
        try:
            if timestamps:
                payload = json.loads(raw.decode("utf-8"))
                audio = base64.b64decode(payload["audio_base64"])
                alignment = payload.get("alignment") or payload.get("normalized_alignment")
            else:
                audio = raw
        except (ValueError, KeyError) as e:
            raise TtsUpstreamError(f"unexpected TTS response shape ({type(e).__name__})", status=502) from e

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio)
        words = palavras_do_alinhamento(alignment)
        timings_path = None
        if timestamps:
            timings_path = str(target.with_suffix(".timings.json"))
            Path(timings_path).write_text(json.dumps({
                "audio_file": target.name, "model_id": model, "voice_id": voice_id,
                "words": [{"word": w.texto, "start": w.inicio_s, "end": w.fim_s} for w in words],
                "alignment": (payload or {}).get("alignment"),
                "normalized_alignment": (payload or {}).get("normalized_alignment"),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        dur, dur_src = duracao(alignment, output_format, len(audio))
        billed, src = creditos_cobrados(hdrs, pf.creditos_max)
        logger.info("tts ok: %d chars -> %d bytes", len(text), len(audio))  # never log text or key
        return TtsResult(str(target), words, len(text), billed, (hdrs or {}).get("request-id"), dur,
                         creditos_fonte=src, audio_s_fonte=dur_src, timings_path=timings_path)

    def clone_instant(
        self,
        name: str,
        samples: list[tuple[str, bytes, str]],
        *,
        consent_ref: str,
        description: Optional[str] = None,
        labels: Optional[dict] = None,
        remove_background_noise: bool = False,
    ) -> CloneResult:
        """`samples` = [(filename, bytes, mime)]. Consent is checked against the reference being exercised."""
        exigir_consentimento(self._consent, self._org, consent_ref, consent_ref)
        for fname, blob, _ in samples:
            if len(blob) > _MAX_SAMPLE_BYTES:
                raise TtsRefused(f"voice sample {fname!r} exceeds {_MAX_SAMPLE_BYTES // 2**20} MB.",
                                 codigo="amostra_grande")
        data = {"name": name, "description": description,
                "remove_background_noise": "true" if remove_background_noise else None,
                "labels": json.dumps(labels) if labels else None}
        payload, _ = self._t.bytes(
            "POST", "/v1/voices/add", data={k: v for k, v in data.items() if v is not None},
            files=[("files", s) for s in samples], timeout=self._timeout)
        try:
            d = json.loads(payload.decode("utf-8") or "{}")
        except ValueError as e:
            raise TtsUpstreamError("voices/add returned non-JSON", status=502) from e
        logger.info("voice cloned (consent ref recorded by caller)")
        return CloneResult(d.get("voice_id"), d.get("requires_verification"), d.get("library_voice_match"))

    def delete_voice(self, voice_id: str) -> bool:
        d = self._t.json("DELETE", f"/v1/voices/{voice_id}")
        return isinstance(d, dict) and d.get("status") == "ok"
