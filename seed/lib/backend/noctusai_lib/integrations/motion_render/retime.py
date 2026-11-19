"""Word-id retime: replace the spec's word times by the narration's, keeping the ids.

Pure. Refuses unless the narration's words match the script tokens 1:1,
punctuation- and case-insensitive -- a narration that adds, drops or changes a
word is new speech, not a retime.
"""
from __future__ import annotations

import copy
import re
import unicodedata

from noctusai_lib.integrations.motion_render.types import RetimeRecusado

_PUNCT = re.compile(r"[^\w]+", re.UNICODE)


def normaliza(palavra: str) -> str:
    return _PUNCT.sub("", unicodedata.normalize("NFC", palavra)).casefold()


def _campos(t) -> tuple[str, float, float]:
    if isinstance(t, dict):
        return t.get("texto", t.get("word", "")), float(t.get("inicio_s", t.get("start"))), float(t.get("fim_s", t.get("end")))
    return t.texto, float(t.inicio_s), float(t.fim_s)


def retime(spec: dict, timings: list) -> dict:
    palavras = spec.get("palavras") or []
    ws = [_campos(t) for t in timings]
    if len(ws) != len(palavras):
        raise RetimeRecusado(f"narracao tem {len(ws)} palavras, o roteiro tem {len(palavras)}: nao casa 1:1")
    dif = [i for i, ((a, _, _), p) in enumerate(zip(ws, palavras)) if normaliza(a) != normaliza(p["texto"])]
    if dif:
        raise RetimeRecusado(f"narracao diverge do roteiro em {len(dif)} palavras (indices {dif[:8]})")
    out = copy.deepcopy(spec)
    for p, (_, ini, fim) in zip(out["palavras"], ws):
        p["inicio_s"], p["fim_s"] = round(ini, 3), round(fim, 3)
    out["fala_fim_s"] = round(ws[-1][2], 3) if ws else 0.0
    return out
