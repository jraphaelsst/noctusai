"""Lais contatos + interacoes (episodes) + the `gen` stale guard (contract 0.2 / 2.2).

One `lais_contatos` row per person Julia talks to; one open `lais_interacoes` row per
contato at a time (DB-enforced by `lais_interacoes_uma_aberta_uq`). Pure table logic over
the schema-scoped service client; the async parts (closing an episode calls agents'
`/resumo`) live in `lais_acoes_service.fechar_interacao`.

The stale guard: every Lais job payload carries `{org_id, chat_key, gen}` built by
`payload_job` from the contato's CURRENT `gen`; at fire time `job_obsoleto` re-reads it and a
mismatch means "complete as `obsoleto`, no side effects". `gen` is bumped by every inbound
(`registrar_inbound`), every `encerrar` and every pause/handoff (`bump_gen`) -- that is how
"cancel on inbound" works without a queue cancel (the seed job queue has none).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

T_CONTATOS = "lais_contatos"
T_INTERACOES = "lais_interacoes"
T_ACOES = "lais_acoes_aplicadas"
T_EVENTOS = "lais_eventos"

#: An inbound after this much silence opens a NEW episode (contract 2.2).
SILENCIO_NOVO_EPISODIO = timedelta(hours=24)
_CAS_TENTATIVAS = 5


class GenConflito(RuntimeError):
    """The compare-and-set on `gen` lost `_CAS_TENTATIVAS` races in a row (should never happen)."""


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now(agora: Optional[datetime]) -> datetime:
    return agora or datetime.now(timezone.utc)


# ── contato ─────────────────────────────────────────────────────────────────
def buscar_contato(client: Any, org_id: UUID | str, connection_id: UUID | str, chat_id: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(T_CONTATOS).select("*")
        .eq("org_id", str(org_id)).eq("connection_id", str(connection_id)).eq("chat_id", chat_id)
        .limit(1).execute().data or []
    )
    return rows[0] if rows else None


def obter_ou_criar_contato(
    client: Any, *, org_id: UUID | str, connection_id: UUID | str, chat_id: str,
    telefone_e164: Optional[str] = None, nome: Optional[str] = None, canal: str = "whatsapp",
) -> dict[str, Any]:
    """The contato for `(org, connection, chat)`; created on first sight. Phone/name fill in
    when missing (never overwrite what an action or a human already set)."""
    row = buscar_contato(client, org_id, connection_id, chat_id)
    if row is None:
        # upsert + ignore_duplicates == INSERT ... ON CONFLICT DO NOTHING: two concurrent first
        # messages cannot both insert, and neither raises.
        client.table(T_CONTATOS).upsert(
            {
                "org_id": str(org_id), "connection_id": str(connection_id), "chat_id": chat_id,
                "telefone_e164": telefone_e164, "nome": (nome or None), "canal": canal,
                # explicit, not left to column defaults: `gen` is a compare-and-set key and must exist
                "gen": 0, "slots": {}, "status_envio": "nao_pronto", "email": None, "operacao": None,
                "encerrado_at": None, "ultimo_inbound_at": None, "ultimo_outbound_at": None,
            },
            on_conflict="org_id,connection_id,chat_id", ignore_duplicates=True,
        ).execute()
        row = buscar_contato(client, org_id, connection_id, chat_id)
        if row is None:
            raise RuntimeError("lais: contato not readable right after its insert")
        return row
    patch: dict[str, Any] = {}
    if telefone_e164 and not row.get("telefone_e164"):
        patch["telefone_e164"] = telefone_e164
    if nome and not row.get("nome"):
        patch["nome"] = nome
    if patch:
        patch["updated_at"] = _now(None).isoformat()
        client.table(T_CONTATOS).update(patch).eq("id", row["id"]).execute()
        row = {**row, **patch}
    return row


def atualizar_contato(client: Any, contato_id: UUID | str, patch: dict[str, Any]) -> None:
    client.table(T_CONTATOS).update({**patch, "updated_at": _now(None).isoformat()}).eq("id", str(contato_id)).execute()


def _cas_gen(client: Any, contato_id: UUID | str, extra: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """`gen = gen + 1` as a compare-and-set (PostgREST has no atomic increment). Returns the
    new gen and the row as stored."""
    for _ in range(_CAS_TENTATIVAS):
        cur_rows = client.table(T_CONTATOS).select("*").eq("id", str(contato_id)).limit(1).execute().data or []
        if not cur_rows:
            raise LookupError(f"lais contato {contato_id} not found")
        cur = cur_rows[0]
        novo = int(cur.get("gen") or 0) + 1
        patch = {**extra, "gen": novo, "updated_at": _now(None).isoformat()}
        done = (
            client.table(T_CONTATOS).update(patch)
            .eq("id", str(contato_id)).eq("gen", int(cur.get("gen") or 0)).execute().data or []
        )
        if done:
            return novo, {**cur, **patch}
    raise GenConflito(f"lais contato {contato_id}: gen compare-and-set lost {_CAS_TENTATIVAS} races")


def bump_gen(client: Any, contato_id: UUID | str, **extra: Any) -> int:
    """Invalidate every queued job of this contato (encerrar / pause / handoff)."""
    return _cas_gen(client, contato_id, extra)[0]


def bump_gen_do_chat(client: Any, org_id: UUID | str, connection_id: UUID | str, chat_id: str) -> Optional[int]:
    """`bump_gen` by chat key; None when the chat has no contato (nothing queued to invalidate)."""
    row = buscar_contato(client, org_id, connection_id, chat_id)
    return bump_gen(client, row["id"]) if row else None


def registrar_inbound(
    client: Any, contato: dict[str, Any], *, agora: Optional[datetime] = None
) -> tuple[dict[str, Any], Optional[datetime]]:
    """An inbound batch arrived: `gen + 1` (cancels queued jobs), `ultimo_inbound_at = now`, a
    previously closed contato is live again (`encerrado_at = null`). Returns the updated contato
    and the PREVIOUS last-activity instant (for the 24 h episode rule)."""
    agora = _now(agora)
    anterior = max(
        (t for t in (_ts(contato.get("ultimo_inbound_at")), _ts(contato.get("ultimo_outbound_at"))) if t),
        default=None,
    )
    _novo, row = _cas_gen(client, contato["id"], {"ultimo_inbound_at": agora.isoformat(), "encerrado_at": None})
    return row, anterior


def registrar_outbound(client: Any, contato_id: UUID | str, *, agora: Optional[datetime] = None) -> None:
    atualizar_contato(client, contato_id, {"ultimo_outbound_at": _now(agora).isoformat()})


# ── interacao (episode) ─────────────────────────────────────────────────────
def interacao_aberta(client: Any, contato_id: UUID | str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(T_INTERACOES).select("*").eq("contato_id", str(contato_id)).is_("encerrada_at", "null")
        .limit(1).execute().data or []
    )
    return rows[0] if rows else None


def abrir_interacao(client: Any, org_id: UUID | str, contato: dict[str, Any], *, agora: Optional[datetime] = None) -> dict[str, Any]:
    """Open an episode. The partial unique index keeps it at one: if a concurrent turn won the
    race our insert is refused (23505) and the winner's row is exactly what we want. Anything
    else (no open row to fall back on) re-raises the original error."""
    existente = interacao_aberta(client, contato["id"])
    if existente is not None:
        return existente
    try:
        client.table(T_INTERACOES).insert({
            "org_id": str(org_id), "contato_id": contato["id"], "iniciada_at": _now(agora).isoformat(),
            "operacao": contato.get("operacao"), "slots": contato.get("slots") or {},
            "encerrada_at": None, "tipo": "comercial", "intencoes": [], "resumo": None,
            "desfecho": None, "custo_usd": None,
        }).execute()
    except Exception:
        ganhador = interacao_aberta(client, contato["id"])
        if ganhador is None:
            raise
        logger.info("lais: interacao open raced for contato=%s -- using the winner", contato["id"])
        return ganhador
    row = interacao_aberta(client, contato["id"])
    if row is None:
        raise RuntimeError("lais: no open interacao right after opening one")
    return row


def episodio_vencido(ultima_atividade: Optional[datetime], *, agora: Optional[datetime] = None) -> bool:
    """True when the open episode went silent for more than 24 h before this inbound."""
    if ultima_atividade is None:
        return False
    return _now(agora) - ultima_atividade > SILENCIO_NOVO_EPISODIO


# ── the stale guard (contract 0.2) ──────────────────────────────────────────
def payload_job(contato: dict[str, Any], chat_key: str) -> dict[str, Any]:
    """The `{org_id, chat_key, gen}` every Lais job payload carries (gen = the contato's CURRENT one)."""
    return {"org_id": str(contato["org_id"]), "chat_key": chat_key, "gen": int(contato.get("gen") or 0)}


def job_obsoleto(client: Any, org_id: UUID | str, contato_id: UUID | str, gen: int) -> bool:
    """True when the job must complete as `obsoleto` without side effects: the contato is gone
    or its `gen` moved on since enqueue."""
    rows = (
        client.table(T_CONTATOS).select("gen").eq("org_id", str(org_id)).eq("id", str(contato_id))
        .limit(1).execute().data or []
    )
    return (not rows) or int(rows[0].get("gen") or 0) != int(gen)


# ── LGPD: deletion on request ───────────────────────────────────────────────
def apagar_do_chat(client: Any, org_id: UUID | str, connection_id: UUID | str, chat_ids: list[str]) -> int:
    """Remove the contato of the chat (every alias spelling) and everything hanging from it.
    Children are deleted explicitly -- not only through the FK cascade -- so the erasure does
    not depend on the schema's ON DELETE behaviour. Returns the number of contatos removed."""
    contatos = (
        client.table(T_CONTATOS).select("id")
        .eq("org_id", str(org_id)).eq("connection_id", str(connection_id)).in_("chat_id", chat_ids)
        .execute().data or []
    )
    ids = [str(c["id"]) for c in contatos]
    if not ids:
        return 0
    # wave 13: the credit-analysis rows (consent log + analyses) are personal/financial data -- erased explicitly too
    for tabela in (T_EVENTOS, T_ACOES, "lais_credito_analises", "lais_credito_consentimentos", T_INTERACOES):
        client.table(tabela).delete().eq("org_id", str(org_id)).in_("contato_id", ids).execute()
    client.table(T_CONTATOS).delete().eq("org_id", str(org_id)).in_("id", ids).execute()
    return len(ids)


__all__ = [
    "GenConflito", "SILENCIO_NOVO_EPISODIO", "abrir_interacao", "apagar_do_chat", "atualizar_contato",
    "bump_gen", "bump_gen_do_chat", "buscar_contato", "episodio_vencido", "interacao_aberta",
    "job_obsoleto", "obter_ou_criar_contato", "payload_job", "registrar_inbound", "registrar_outbound",
]
