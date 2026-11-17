"""Julia > the lead card's note: temperature, listings of interest and intent (Lais study S3, owner 2026-11-17).

Social Wiring is the ONLY CRM destination (owner decision: no Vista push, so study item S2 is dropped), therefore the
card note is where a broker reads how hot a lead is. Three facts are added to the note `julia_envio_service.montar_nota`
builds; all three are DERIVED from what SW already stores about the contato -- nothing new is collected, nothing is a
model free text:

  temperatura  `frio` | `morno` | `quente`. The agent's own value wins when it sent one (`slots.temperatura`, the hand-off
               report field of study item A11); otherwise it is derived: a visit / proposal intent or the `visita` trigger
               is `quente`, a cold or invalid-number trigger is `frio`, anything else that reached the send is `morno`.
  imoveis      up to `IMOVEIS_MAX` listing codes: the one the lead named (`slots.codigo_imovel`), the campaign listing
               (`codigo_imovel_campanha`) and the listings Julia looked up for this contato (`imovel_consultado` events).
  intencao     `visita` | `proposta` | None: the `intencao_visita` event, the `visita` trigger, a hand-off whose closed motive
               code is `pedido_visita` / `proposta` (codes the agents slice adds, item A10), or `slots.intencao`.

Pure functions + one read (`ler_sinais`); the codes are listing codes, never personal data.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

TEMPERATURAS = ("frio", "morno", "quente")
INTENCOES = ("visita", "proposta")
IMOVEIS_MAX = 5
EVENTOS_LIDOS = 200
TIPOS_SINAL = ("intencao_visita", "imovel_consultado", "handoff")
_MOTIVO_INTENCAO = {"pedido_visita": "visita", "proposta": "proposta"}
ROTULO_TEMPERATURA = {"frio": "frio", "morno": "morno", "quente": "quente"}
ROTULO_INTENCAO = {"visita": "quer visitar o imóvel", "proposta": "quer fazer uma proposta"}


def _codigo(v: Any) -> Optional[str]:
    c = str(v or "").strip().upper()
    return c[:40] if c else None


def ler_sinais(client: Any, org_id: Any, contato_id: Any) -> list[dict[str, Any]]:
    """The contato's signal events (newest first). A read failure is logged and answers `[]`: the note still goes out."""
    try:
        return (
            client.table("julia_eventos").select("tipo,payload,created_at").eq("org_id", str(org_id))
            .eq("contato_id", str(contato_id)).in_("tipo", list(TIPOS_SINAL)).order("created_at", desc=True)
            .limit(EVENTOS_LIDOS).execute().data or []
        )
    except Exception as exc:  # noqa: BLE001 -- the note is a courtesy to the broker; a failed read must not block the send
        logger.error("julia: note signals unreadable (org=%s) (%s)", org_id, type(exc).__name__)
        return []


def intencao(contato: dict[str, Any], gatilho: str, eventos: Iterable[dict[str, Any]]) -> Optional[str]:
    declarada = str((contato.get("slots") or {}).get("intencao") or "").strip().lower()
    if declarada in INTENCOES:
        return declarada
    if gatilho == "visita":
        return "visita"
    achada: Optional[str] = None
    for e in eventos:
        if e.get("tipo") == "intencao_visita":
            return "visita"
        if e.get("tipo") == "handoff":
            achada = achada or _MOTIVO_INTENCAO.get(str((e.get("payload") or {}).get("motivo_codigo") or ""))
    return achada


def temperatura(contato: dict[str, Any], gatilho: str, intencao_do_lead: Optional[str]) -> str:
    dada = str((contato.get("slots") or {}).get("temperatura") or "").strip().lower()
    if dada in TEMPERATURAS:
        return dada
    if intencao_do_lead is not None:
        return "quente"
    if gatilho in ("frio", "invalido"):
        return "frio"
    return "morno"


def imoveis_de_interesse(contato: dict[str, Any], eventos: Iterable[dict[str, Any]]) -> list[str]:
    """Distinct listing codes in priority order (named by the lead, campaign, then looked up), capped at `IMOVEIS_MAX`."""
    vistos: list[str] = []

    def _add(v: Any) -> None:
        c = _codigo(v)
        if c and c not in vistos:
            vistos.append(c)

    _add((contato.get("slots") or {}).get("codigo_imovel"))
    _add(contato.get("codigo_imovel_campanha"))
    for e in reversed(list(eventos)):  # oldest first: the order the lead explored them
        if e.get("tipo") == "imovel_consultado":
            for c in (e.get("payload") or {}).get("codigos") or []:
                _add(c)
        elif e.get("tipo") == "intencao_visita":
            _add((e.get("payload") or {}).get("codigo"))
    return vistos[:IMOVEIS_MAX]


def linhas_da_nota(client: Any, org_id: Any, contato: dict[str, Any], gatilho: str) -> list[str]:
    """The note's extra lines (`- temperatura: quente` ...), in a fixed order; empty facts are omitted."""
    eventos = ler_sinais(client, org_id, contato["id"])
    quer = intencao(contato, gatilho, eventos)
    codigos = imoveis_de_interesse(contato, eventos)
    linhas = [f"- temperatura: {ROTULO_TEMPERATURA[temperatura(contato, gatilho, quer)]}"]
    if codigos:
        linhas.append(f"- imóveis de interesse: {', '.join(codigos)}")
    if quer:
        linhas.append(f"- intenção: {ROTULO_INTENCAO[quer]}")
    return linhas


__all__ = ["IMOVEIS_MAX", "INTENCOES", "TEMPERATURAS", "imoveis_de_interesse", "intencao", "linhas_da_nota", "ler_sinais", "temperatura"]
