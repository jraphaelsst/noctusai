"""Deterministic render of a channel turn's SECOND system message (Julia v2 CONTRACT §6.3 / §8.1).

The compiled agent prompt stays the first system message (static, cacheable); this one is dynamic -- the
attendance state SW sent, the lead's DOSSIER (what the qualification records already hold, so it is never
asked again), the newest hand-off note and the re-engagement instruction -- so SW and the qualification state
can change per turn without republishing the agent version.

Every human-readable word (headings, labels, yes/no, the credit and re-engagement instructions) is a row of
``agent_version_textos`` read from the compiled content bundle (D2). This module owns ORDER and LAYOUT only,
plus the one security invariant: lead-influenced text (recorded values, the hand-off note) is rendered as JSON
string literals on one line each, so a value cannot open a heading or forge a section of the prompt. Pure:
same input, same bytes (golden-file tested).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.studio.models import ConteudoBundle

__all__ = ["Dossie", "render_contexto_system"]


@dataclass(frozen=True)
class Dossie:
    """The lead's recorded facts, as the render needs them (built from the computed qualification state)."""

    #: ``(criterion label, value)`` in the standard's order -- values are the LEAD's words/choices.
    valores: Sequence[tuple[str, Any]] = ()
    estagio: str | None = None
    score: int | None = None
    #: Labels of the criteria still missing (the next stage's, in order).
    faltando: Sequence[str] = ()
    oferecidos: Sequence[str] = ()
    gostou: Sequence[str] = ()
    #: The newest hand-off note's summary (``None`` = none).
    resumo_handoff: str | None = None


def _line(text: str) -> str:
    """One physical line: whitespace (incl. newlines) collapsed."""
    return " ".join(str(text).split())


def _um_linha(value: Any) -> Any:
    """Whitespace (incl. newlines) collapsed inside every string of a recorded value."""
    if isinstance(value, str):
        return _line(value)
    if isinstance(value, list):
        return [_um_linha(v) for v in value]
    if isinstance(value, dict):
        return {k: _um_linha(v) for k, v in value.items()}
    return value


def _lit(value: Any) -> str:
    """A JSON literal on ONE physical line: nothing the lead wrote can open a heading."""
    return json.dumps(_um_linha(value), ensure_ascii=False, default=str)


def render_contexto_system(
    conteudo: ConteudoBundle, *, agora: datetime, fuso: str, estado: Any | None, dossie: Dossie,
) -> str:
    """``estado`` is the request's ``contexto.estado`` (``None`` = not sent); a re-engagement turn is the
    one whose ``estado.reengajamento`` names the flow."""

    def T(chave: str) -> str:
        texto = conteudo.texto(chave).strip()
        if not texto:
            raise ValueError(f"texto_ausente: {chave}")
        return texto

    out: list[str] = [f"## {T('contexto.titulo_estado')}"]
    local = agora.astimezone(ZoneInfo(fuso))
    out.append(f"{T('contexto.rotulo_data_hora')}: {local.strftime('%Y-%m-%d %H:%M')} ({fuso})")
    if estado is not None:
        out.append(f"{T('contexto.rotulo_encerrado')}: {T('contexto.sim') if estado.encerrado else T('contexto.nao')}")
        if getattr(estado, "atendente_nome", None):
            out.append(f"{T('contexto.rotulo_atendente')}: {_lit(_line(estado.atendente_nome))}")
        origem = getattr(estado, "origem", None)
        if origem is not None and getattr(origem, "canal_origem", None):
            out.append(f"{T('contexto.rotulo_origem')}: {_line(origem.canal_origem)}")
        if origem is not None and getattr(origem, "codigo_imovel_campanha", None):
            out.append(f"{T('contexto.rotulo_campanha')}: {_lit(_line(origem.codigo_imovel_campanha))}")

    out += ["", f"## {T('contexto.titulo_dossie')}", T("contexto.aviso_valores_cliente")]
    if dossie.valores:
        out += [f"- {_line(rotulo)}: {_lit(valor)}" for rotulo, valor in dossie.valores]
    else:
        out.append(T("contexto.dossie_vazio"))
    if dossie.estagio is not None:
        out.append(f"{T('contexto.rotulo_estagio')}: {_line(dossie.estagio)}")
    if dossie.score is not None:
        out.append(f"{T('contexto.rotulo_score')}: {dossie.score}")
    if dossie.faltando:
        out.append(f"{T('contexto.rotulo_faltando')}: {', '.join(_line(f) for f in dossie.faltando)}")
    if dossie.oferecidos:
        out.append(f"{T('contexto.rotulo_oferecidos')}: {', '.join(_lit(c) for c in dossie.oferecidos)}")
    if dossie.gostou:
        out.append(f"{T('contexto.rotulo_gostou')}: {', '.join(_lit(c) for c in dossie.gostou)}")
    if dossie.resumo_handoff:
        out += ["", f"## {T('contexto.titulo_handoff')}", _lit(_line(dossie.resumo_handoff))]

    credito = getattr(estado, "credito", None) if estado is not None else None
    if credito is not None and credito.ativo:
        chave = "credito.pedir" if credito.consentimento is None else (
            "credito.consentiu" if credito.consentimento else "credito.recusou")
        out += ["", f"## {T('contexto.titulo_credito')}", T(chave)]

    tier = getattr(estado, "reengajamento", None) if estado is not None else None
    if tier is not None:
        out += ["", f"## {T('contexto.titulo_reengajamento')}", T(f"reengajamento.{tier}")]
        base = getattr(estado, "texto_base", None)
        if base:
            # SW's template text is an operator-authored string, but it still rides as one JSON literal.
            out.append(T("reengajamento.texto_base").replace("{texto_base}", _lit(_line(base))))
    return "\n".join(out) + "\n"
