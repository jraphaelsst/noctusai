"""Handoff ledger `atendimento_handoffs` (maya-blocks CONTRACT §2): two triggers + the status machine.

T1  `sink_novo_lead` -- a `lais_eventos` sink (registered by `registrar()`): on `novo_lead` (Julia's successful
    send to the SW) writes `sdr -> bloco_atual(lead)`.
T2  `ao_movimento` / `apos_mover` -- the block-boundary hook, called right after every stage move that writes a
    `pipeline_movimentos` row: writes a `movimento_etapa` handoff iff the stage owner changes (both non-null).

Status machine (§2.3): `emitido -> assumido` on the first take-over signal after `created_at` and before
`created_at + horas_para_assumir`; `emitido -> expirado` once that deadline passes (`expirar_vencidos`, sweep).
Both are terminal; every transition is a conditional update (`status = 'emitido'`), so a race cannot rewrite it.
Signals: (1) a `pipeline_movimentos` row on the same deal (atendimento or its processo) -- marked inline by the T2
hook, AND by the sweep; (2) a `cliente_notas` row with `autor_id IS NOT NULL` on the card's cliente -- the notes
are written by the seed card-hub, so this one is detected by `detectar_assumidos` (the S3 sweep calls `varrer`).

Rules shared by all of it:
  * Recording happens ONLY while `supervisao_config.supervisao_ativa` is true (absent row = off); off means
    nothing is written and nothing is read beyond the switch.
  * References only (ids) -- no personal data is copied.
  * Idempotent on `(org_id, gatilho, origem_evento)`: `upsert(..., ignore_duplicates=True)`.
  * Never blocks the flow it observes: every failure is logged at ERROR and swallowed -- the send, the move or the
    accept already happened and is never undone (§5.6). Nothing here sends anything to anyone (§5.1).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from app.modules.atendimento_blocos import repository as repo
from app.modules.atendimento_blocos.blocos import (
    BLOCO_SDR,
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    PIPELINES_ATENDIMENTO,
    dono,
)

logger = logging.getLogger(__name__)

T_HANDOFFS = "atendimento_handoffs"
T_MOVIMENTOS = "pipeline_movimentos"
T_ATRIBUICOES = "lais_atribuicoes"
T_ENTREGAS = "lais_envio_entregas"
T_NOTAS = "cliente_notas"

GATILHO_NOVO_LEAD = "novo_lead"
GATILHO_MOVIMENTO = "movimento_etapa"
EMITIDO, ASSUMIDO, EXPIRADO = "emitido", "assumido", "expirado"
_CONFLITO = "org_id,gatilho,origem_evento"
_LIMITE_ABERTOS_POR_CARD = 100


def _ts(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _agora(agora: Optional[datetime]) -> datetime:
    return agora or datetime.now(timezone.utc)


def _gravar(client: Any, row: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Insert-or-ignore on the origin key: a replayed sink/hook is a no-op (returns None)."""
    data = client.table(T_HANDOFFS).upsert(row, on_conflict=_CONFLITO, ignore_duplicates=True).execute().data or []
    return data[0] if data else None


def _mais_recente(client: Any, tabela: str, org_id: str, **filtros: Any) -> Optional[dict[str, Any]]:
    q = client.table(tabela).select("id, created_at").eq("org_id", org_id)
    for coluna, valor in filtros.items():
        q = q.eq(coluna, valor)
    rows = q.order("created_at", desc=True).limit(1).execute().data or []
    return rows[0] if rows else None


# ── T1: novo_lead sink ──────────────────────────────────────────────────────
def sink_novo_lead(client: Any, evento: dict[str, Any]) -> Optional[dict[str, Any]]:
    """`lais_eventos` sink: `novo_lead` -> `sdr -> bloco_atual(lead)`. Other event types are ignored."""
    if evento.get("tipo") != GATILHO_NOVO_LEAD:
        return None
    org = str(evento.get("org_id") or "")
    try:
        if not repo.ler_supervisao(client, org)["supervisao_ativa"]:
            return None
        if not evento.get("id"):
            logger.error("atendimento_blocos: novo_lead event without an id (org=%s) -- handoff not recorded", org)
            return None
        payload = evento.get("payload") or {}
        lead_id = payload.get("lead_id")
        contato_id = evento.get("contato_id")
        if not lead_id:
            logger.warning("atendimento_blocos: novo_lead %s carries no lead_id (org=%s) -- no handoff", evento["id"], org)
            return None
        config = repo.configuracao_efetiva(client, org)
        card = repo.card_do_lead(client, org, lead_id)
        if card is None:
            logger.warning("atendimento_blocos: novo_lead %s -- lead %s has no card (sem_card, org=%s), no handoff", evento["id"], lead_id, org)
            return None
        para = repo.bloco_do_card(client, org, card, config)
        if para is None or para == BLOCO_SDR:
            logger.warning(
                "atendimento_blocos: novo_lead %s -- target block is %s (org=%s), no handoff",
                evento["id"], "sem_bloco" if para is None else para, org,
            )
            return None
        atribuicao = _mais_recente(client, T_ATRIBUICOES, org, contato_id=str(contato_id)) if contato_id else None
        entrega = _mais_recente(client, T_ENTREGAS, org, contato_id=str(contato_id), status="ok") if contato_id else None
        return _gravar(client, {
            "org_id": org, "de_bloco": BLOCO_SDR, "para_bloco": para,
            "de_agent_key": config[BLOCO_SDR].agent_key, "para_agent_key": config[para].agent_key,
            "gatilho": GATILHO_NOVO_LEAD, "origem_evento": str(evento["id"]),
            "contato_id": str(contato_id) if contato_id else None, "lead_id": str(lead_id),
            "atendimento_id": str(card["id"]),
            "atribuicao_id": str(atribuicao["id"]) if atribuicao else None,
            "entrega_id": str(entrega["id"]) if entrega else None,
            "status": EMITIDO,
            "created_at": (_ts(evento.get("created_at")) or _agora(None)).isoformat(),
        })
    except Exception:
        logger.exception("atendimento_blocos: novo_lead handoff failed (org=%s evento=%s) -- the send stands", org, evento.get("id"))
        return None


# ── T2: the block-boundary hook ─────────────────────────────────────────────
def _atendimento_do_card(client: Any, org: str, pipeline: str, card_id: str) -> Optional[dict[str, Any]]:
    if pipeline == PIPELINE_PROCESSOS:
        rows = (
            client.table(repo.T_PROCESSOS).select("id, atendimento_id").eq("org_id", org).eq("id", card_id).limit(1)
            .execute().data or []
        )
        if not rows or not rows[0].get("atendimento_id"):
            return None
        card_id = str(rows[0]["atendimento_id"])
    rows = (
        client.table(repo.T_ATENDIMENTOS).select("id, lead_id, cliente_id, etapa_id").eq("org_id", org)
        .eq("id", card_id).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def ao_movimento(client: Any, org_id: UUID | str, movimento: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One `pipeline_movimentos` row: mark the deal's open handoffs `assumido` (signal 1), then record a
    `movimento_etapa` handoff when the move crosses a block boundary. Returns the new handoff row or None."""
    org = str(org_id)
    try:
        supervisao = repo.ler_supervisao(client, org)
        if not supervisao["supervisao_ativa"]:
            return None
        pipeline = movimento.get("pipeline")
        if pipeline not in PIPELINES_ATENDIMENTO or not movimento.get("id"):
            return None
        atendimento = _atendimento_do_card(client, org, pipeline, str(movimento["entidade_id"]))
        if atendimento is None:
            logger.warning("atendimento_blocos: move %s on a card with no atendimento (org=%s) -- no handoff", movimento["id"], org)
            return None
        sinal_at = _ts(movimento.get("created_at")) or _agora(None)
        marcar_assumidos_do_card(client, org, str(atendimento["id"]), sinal_at, supervisao["horas_para_assumir"])

        config = repo.configuracao_efetiva(client, org)
        para_bloco = dono(config, pipeline, repo.slug_da_etapa(client, org, movimento.get("para_etapa_id")))
        if movimento.get("de_etapa_id"):
            de_bloco = dono(config, pipeline, repo.slug_da_etapa(client, org, movimento["de_etapa_id"]))
        elif pipeline == PIPELINE_PROCESSOS:
            # The accept movement (`aceite.aceitar_proposta`): the deal enters processos from the funil accept stage.
            de_bloco = dono(config, PIPELINE_FUNIL, repo.slug_da_etapa(client, org, atendimento.get("etapa_id")))
        else:
            de_bloco = None
        if de_bloco is None or para_bloco is None or de_bloco == para_bloco:
            return None
        return _gravar(client, {
            "org_id": org, "de_bloco": de_bloco, "para_bloco": para_bloco,
            "de_agent_key": config[de_bloco].agent_key, "para_agent_key": config[para_bloco].agent_key,
            "gatilho": GATILHO_MOVIMENTO, "origem_evento": str(movimento["id"]),
            "lead_id": str(atendimento["lead_id"]) if atendimento.get("lead_id") else None,
            "atendimento_id": str(atendimento["id"]),
            "status": EMITIDO, "created_at": sinal_at.isoformat(),
        })
    except Exception:
        logger.exception("atendimento_blocos: block-boundary hook failed (org=%s movimento=%s) -- the move stands", org, movimento.get("id"))
        return None


def apos_mover(client: Any, org_id: UUID | str, pipeline: Any, card_id: Any, para_etapa_id: Any) -> Optional[dict[str, Any]]:
    """Call right after `move_card`: finds the movement it just wrote (none = a within-column reorder) and runs
    `ao_movimento` on it. Never raises."""
    org = str(org_id)
    nome = getattr(pipeline, "pipeline", pipeline)
    try:
        if not repo.ler_supervisao(client, org)["supervisao_ativa"]:
            return None
        rows = (
            client.table(T_MOVIMENTOS).select("*").eq("org_id", org).eq("pipeline", nome)
            .eq("entidade_id", str(card_id)).eq("para_etapa_id", str(para_etapa_id))
            .order("created_at", desc=True).limit(1).execute().data or []
        )
    except Exception:
        logger.exception("atendimento_blocos: could not read the movement of card %s (org=%s) -- no handoff", card_id, org)
        return None
    return ao_movimento(client, org, rows[0]) if rows else None


# ── status machine ──────────────────────────────────────────────────────────
def _no_prazo(handoff: dict[str, Any], sinal_at: datetime, horas: int) -> bool:
    criado = _ts(handoff.get("created_at"))
    return criado is not None and criado < sinal_at < criado + timedelta(hours=horas)


def _marcar(client: Any, org: str, handoff_id: Any, patch: dict[str, Any]) -> bool:
    rows = (
        client.table(T_HANDOFFS).update(patch).eq("org_id", org).eq("id", str(handoff_id)).eq("status", EMITIDO)
        .execute().data or []
    )
    return bool(rows)


def marcar_assumidos_do_card(client: Any, org_id: UUID | str, atendimento_id: str, sinal_at: datetime, horas: int) -> int:
    """Signal at `sinal_at` on this deal: every open handoff created before it (and still inside its deadline)
    becomes `assumido` at `sinal_at`. A late signal is left to the sweep, which expires it (no back-fill)."""
    org = str(org_id)
    abertos = (
        client.table(T_HANDOFFS).select("id, created_at, status").eq("org_id", org).eq("atendimento_id", atendimento_id)
        .eq("status", EMITIDO).limit(_LIMITE_ABERTOS_POR_CARD).execute().data or []
    )
    n = 0
    for h in abertos:
        if _no_prazo(h, sinal_at, horas) and _marcar(client, org, h["id"], {"status": ASSUMIDO, "assumido_at": sinal_at.isoformat()}):
            n += 1
    return n


def _abertos(client: Any, org: str) -> list[dict[str, Any]]:
    from noctusai_lib.integrations.persistence import iter_paged_rows

    return list(iter_paged_rows(
        lambda a, b: client.table(T_HANDOFFS).select("id, created_at, atendimento_id, gatilho, origem_evento").eq("org_id", org)
        .eq("status", EMITIDO).order("id").range(a, b).execute().data,
        label="atendimento_handoffs abertos",
    ))


def _primeiro_sinal(client: Any, org: str, handoff: dict[str, Any]) -> Optional[datetime]:
    """Earliest take-over signal after the handoff (signal 1: a move on the deal; signal 2: a human note)."""
    criado = _ts(handoff.get("created_at"))
    atendimento_id = handoff.get("atendimento_id")
    if criado is None or not atendimento_id:
        return None
    atendimento = _atendimento_do_card(client, org, PIPELINE_FUNIL, str(atendimento_id))
    if atendimento is None:
        return None
    cards = [str(atendimento_id)]
    processo = repo.processo_do_atendimento(client, org, str(atendimento_id))
    if processo is not None:
        cards.append(str(processo["id"]))
    candidatos: list[datetime] = []
    q = (
        client.table(T_MOVIMENTOS).select("id, created_at").eq("org_id", org).in_("entidade_id", cards)
        .gt("created_at", criado.isoformat())
    )
    origem = str(handoff.get("origem_evento") or "") if handoff.get("gatilho") == GATILHO_MOVIMENTO else ""
    if origem:
        # the move that EMITTED this handoff is its cause, never its take-over (same-instant clocks included)
        q = q.neq("id", origem)
    movs = q.order("created_at").limit(1).execute().data or []
    candidatos += [t for t in (_ts(m.get("created_at")) for m in movs if str(m.get("id")) != origem) if t and t > criado]
    if atendimento.get("cliente_id"):
        notas = (
            client.table(T_NOTAS).select("id, created_at, autor_id").eq("org_id", org)
            .eq("cliente_id", str(atendimento["cliente_id"])).not_.is_("autor_id", "null")
            .gt("created_at", criado.isoformat()).order("created_at").limit(1).execute().data or []
        )
        candidatos += [t for t in (_ts(n.get("created_at")) for n in notas if n.get("autor_id")) if t and t > criado]
    return min(candidatos) if candidatos else None


def detectar_assumidos(client: Any, org_id: UUID | str, *, horas: Optional[int] = None) -> int:
    """Sweep leg 1: every open handoff with a signal inside its deadline -> `assumido` at the signal time."""
    org = str(org_id)
    horas = horas or repo.ler_supervisao(client, org)["horas_para_assumir"]
    n = 0
    for h in _abertos(client, org):
        sinal = _primeiro_sinal(client, org, h)
        if sinal is not None and _no_prazo(h, sinal, horas) and _marcar(
            client, org, h["id"], {"status": ASSUMIDO, "assumido_at": sinal.isoformat()},
        ):
            n += 1
    return n


def expirar_vencidos(client: Any, org_id: UUID | str, *, horas: Optional[int] = None, agora: Optional[datetime] = None) -> int:
    """Sweep leg 2: every handoff still `emitido` at `created_at + horas` -> `expirado` (expirado_at = now)."""
    org = str(org_id)
    horas = horas or repo.ler_supervisao(client, org)["horas_para_assumir"]
    agora = _agora(agora)
    n = 0
    for h in _abertos(client, org):
        criado = _ts(h.get("created_at"))
        if criado is not None and agora >= criado + timedelta(hours=horas) and _marcar(
            client, org, h["id"], {"status": EXPIRADO, "expirado_at": agora.isoformat()},
        ):
            n += 1
    return n


def varrer(client: Any, org_id: UUID | str, *, agora: Optional[datetime] = None) -> dict[str, int]:
    """The S3 sweep body for one org: detect take-overs first (an in-time signal wins), then expire. Off -> no-op."""
    supervisao = repo.ler_supervisao(client, org_id)
    if not supervisao["supervisao_ativa"]:
        return {"assumidos": 0, "expirados": 0}
    horas = supervisao["horas_para_assumir"]
    return {
        "assumidos": detectar_assumidos(client, org_id, horas=horas),
        "expirados": expirar_vencidos(client, org_id, horas=horas, agora=agora),
    }


def registrar() -> None:
    """Bind T1 to the Lais event bus (idempotent -- `registrar_sink` keeps one copy)."""
    from app.services import lais_eventos_service

    lais_eventos_service.registrar_sink(sink_novo_lead)


__all__ = [
    "ASSUMIDO", "EMITIDO", "EXPIRADO", "GATILHO_MOVIMENTO", "GATILHO_NOVO_LEAD", "T_HANDOFFS", "ao_movimento",
    "apos_mover", "detectar_assumidos", "expirar_vencidos", "marcar_assumidos_do_card", "registrar", "sink_novo_lead",
    "varrer",
]
