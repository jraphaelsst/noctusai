"""The classifier's evaluation: the owner's blind labels vs the model's verdict, as counts.

Pure functions over the rows of ``assistant.resumo_rotulos`` (model verdict x owner label, per prompt_version/model).
Definitions (written, so the number means one thing):

* the model's verdict is ``agendamento`` | ``outro``; the owner's label is ``agendamento`` | ``nao_agendamento`` |
  ``nao_sei``;
* they AGREE when (agendamento, agendamento) or (outro, nao_agendamento);
* ``nao_sei`` is the owner declining to judge: it is counted and shown, but it is outside the agreement denominator
  (``decididos`` = total - nao_sei), so an ambiguous message never counts for or against the model;
* ``concordancia`` is ``concordam / decididos`` and ``None`` (never 0) when nothing was decided.
Message text is never an input here.
"""
from __future__ import annotations

from typing import Any, Iterable

VEREDITOS = ("agendamento", "outro")
ROTULOS = ("agendamento", "nao_agendamento", "nao_sei")
_CONCORDA = {("agendamento", "agendamento"), ("outro", "nao_agendamento")}


def calcular_concordancia(linhas: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold ``{prompt_version, modelo, veredito, rotulo, n}`` rows into one summary per (prompt_version, modelo)."""
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    for r in linhas:
        veredito, rotulo, n = r["veredito"], r["rotulo"], int(r["n"])
        if veredito not in VEREDITOS or rotulo not in ROTULOS:
            raise ValueError(f"unknown verdict/label pair ({veredito!r}, {rotulo!r})")
        chave = (r["prompt_version"] or "", r["modelo"] or "")
        g = grupos.setdefault(chave, {
            "prompt_version": chave[0], "modelo": chave[1], "total": 0, "nao_sei": 0, "decididos": 0, "concordam": 0,
            "matriz": {v: {l: 0 for l in ROTULOS} for v in VEREDITOS},
        })
        g["matriz"][veredito][rotulo] += n
        g["total"] += n
        if rotulo == "nao_sei":
            g["nao_sei"] += n
            continue
        g["decididos"] += n
        if (veredito, rotulo) in _CONCORDA:
            g["concordam"] += n
    for g in grupos.values():
        g["concordancia"] = round(g["concordam"] / g["decididos"], 4) if g["decididos"] else None
    return [grupos[k] for k in sorted(grupos)]
