"""Pure mappers: ElevenLabs alignment/headers -> seed-domain timings and billing."""
from __future__ import annotations

import re
from typing import Mapping, Optional

from noctusai_lib.integrations.tts.types import PalavraTiming


def palavras_do_alinhamento(alignment: Optional[dict]) -> list[PalavraTiming]:
    """Group the character-level alignment into whitespace-separated words."""
    if not alignment:
        return []
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    out: list[PalavraTiming] = []
    cur: list[int] = []

    def flush() -> None:
        if cur:
            out.append(PalavraTiming("".join(chars[i] for i in cur), float(starts[cur[0]]), float(ends[cur[-1]])))
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


def duracao(alignment: Optional[dict], fmt: str, nbytes: int) -> tuple[Optional[float], Optional[str]]:
    ends = (alignment or {}).get("character_end_times_seconds") or []
    if ends:
        return round(float(ends[-1]), 3), "alinhamento"
    m = re.match(r"^(mp3|opus)_\d+_(\d+)$", fmt)  # constant-bitrate codecs only
    if m and int(m.group(2)) > 0:
        return round(nbytes * 8 / (int(m.group(2)) * 1000), 3), "estimado_bitrate"
    return None, None


def creditos_estimados(chars: int, model: Optional[dict]) -> Optional[float]:
    rates = (model or {}).get("model_rates") or {}
    mult = rates.get("character_cost_multiplier")
    if mult is None:
        return None
    return round(chars * float(mult) * float(rates.get("cost_discount_multiplier", 1) or 1), 2)


def creditos_cobrados(headers: Mapping[str, str], estimativa: Optional[float]) -> tuple[Optional[int], str]:
    """Billed credits: the vendor's response header wins; else the model-multiplier estimate."""
    hdrs = {str(k).lower(): v for k, v in (headers or {}).items()}
    raw = hdrs.get("x-character-count") or hdrs.get("character-cost")
    if raw and str(raw).isdigit():
        return int(raw), "response_header"
    if estimativa is not None:
        return int(round(estimativa)), "estimado_multiplicador"
    return None, "indisponivel"
