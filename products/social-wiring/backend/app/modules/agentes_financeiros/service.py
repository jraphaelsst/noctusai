"""Financing-agent registry — reads and writes, org-scoped by RLS.

🔴 EVERY CALL TAKES A USER-SCOPED CLIENT, NOT THE ADMIN ONE.

Migration 100 gives this table a `FOR ALL TO authenticated` policy predicated
on `current_org_id()`, which is unusual in this schema: most tables are
select-only for users and let the service role write. That shape is right for
rows the SYSTEM writes — leads arriving, cards a trigger spawns, extraction
results. This is a registry a PERSON maintains on its own page, so the write is
theirs and the database is what scopes it.

The `.eq("org_id", ...)` predicates below are therefore belt-and-braces rather
than the only guard. They stay because a future caller passing an admin client
would otherwise silently reach every org's rows, and a redundant predicate is
cheaper than that failure.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError

SCHEMA = "social_wiring"
TABLE = "agentes_financeiros"
FINANCIAMENTO_TABLE = "atendimento_financiamento"

#: Returned to the card's dropdown and to the management page alike. Explicit
#: rather than `*` so widening the table cannot silently widen the payload.
FIELDS = (
    "id",
    "nome",
    "codigo_banco",
    "agencia",
    "contato_nome",
    "contato_email",
    "contato_telefone",
    "observacoes",
    "ativo",
    "created_at",
    "updated_at",
)

#: Columns a caller may set. `id`, `org_id` and the audit columns are derived
#: here, never accepted — an accepted `org_id` is a cross-tenant write waiting
#: for its first bug.
EDITAVEIS = (
    "nome",
    "codigo_banco",
    "agencia",
    "contato_nome",
    "contato_email",
    "contato_telefone",
    "observacoes",
    "ativo",
)


def _t(client: Any):
    return client.schema(SCHEMA).table(TABLE)


def _out(row: dict) -> dict:
    return {k: row.get(k) for k in FIELDS}


def listar(
    client: Any,
    org_id: UUID,
    *,
    incluir_inativos: bool = False,
) -> dict:
    """Every agent for this org, alphabetically.

    `incluir_inativos` defaults to False because the common caller is the
    card's dropdown, which must not offer a retired bank. The management page
    passes True — it is the surface where you reactivate one, and an agent you
    cannot see is an agent you cannot bring back.
    """
    q = _t(client).select(",".join(FIELDS)).eq("org_id", str(org_id))
    if not incluir_inativos:
        q = q.eq("ativo", True)
    rows = (q.order("nome", desc=False).execute()).data or []
    itens = [_out(r) for r in rows]
    return {"items": itens, "total": len(itens)}


def obter(client: Any, org_id: UUID, agente_id: UUID) -> dict:
    rows = (
        _t(client)
        .select(",".join(FIELDS))
        .eq("org_id", str(org_id))
        .eq("id", str(agente_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("Agente financeiro não encontrado.")
    return _out(rows[0])


def criar(
    client: Any,
    org_id: UUID,
    *,
    dados: dict,
    user_id: Optional[UUID] = None,
) -> dict:
    """Register an agent.

    A duplicate name surfaces as a 409 rather than the database's raw unique
    violation: `uq_sw_agentes_financeiros_org_nome` is case- and
    whitespace-insensitive, so "Caixa" colliding with "CAIXA " is correct and
    needs to read as "this one already exists", not as a server error.
    """
    row = {k: dados.get(k) for k in EDITAVEIS if k in dados}
    row["id"] = str(uuid4())
    row["org_id"] = str(org_id)
    row.setdefault("ativo", True)
    if user_id:
        row["created_por"] = str(user_id)

    try:
        _t(client).insert(row).execute()
    except Exception as exc:  # noqa: BLE001 — re-raised, never swallowed
        if _e_duplicata(exc):
            raise ConflictError(
                f"Já existe um agente financeiro chamado {row.get('nome')!r}."
            ) from exc
        raise
    return obter(client, org_id, UUID(row["id"]))


def atualizar(
    client: Any,
    org_id: UUID,
    agente_id: UUID,
    *,
    dados: dict,
    user_id: Optional[UUID] = None,
) -> dict:
    """Patch an agent. Only keys actually present are written.

    `dados` is already the parsed body's `exclude_unset` dict, so an omitted
    field is left alone and an explicit `null` clears it — the distinction a
    PATCH exists to make.
    """
    updates = {k: dados[k] for k in EDITAVEIS if k in dados}
    if not updates:
        return obter(client, org_id, agente_id)
    if user_id:
        updates["updated_por"] = str(user_id)

    obter(client, org_id, agente_id)  # 404 before writing, not after
    try:
        (
            _t(client)
            .update(updates)
            .eq("org_id", str(org_id))
            .eq("id", str(agente_id))
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — re-raised, never swallowed
        if _e_duplicata(exc):
            raise ConflictError(
                f"Já existe um agente financeiro chamado {updates.get('nome')!r}."
            ) from exc
        raise
    return obter(client, org_id, agente_id)


def remover(client: Any, org_id: UUID, agente_id: UUID) -> None:
    """Delete an agent — refused while any deal points at it.

    🔴 CHECKED HERE *AND* ENFORCED BY THE FK. The database's ON DELETE RESTRICT
    is the real guarantee; this lookup exists to turn it into a sentence a
    person can act on ("3 atendimentos usam este agente — desative-o") instead
    of a foreign-key violation. Removing the check would not make the delete
    succeed, it would only make the refusal unreadable.
    """
    obter(client, org_id, agente_id)

    em_uso = (
        client.schema(SCHEMA)
        .table(FINANCIAMENTO_TABLE)
        .select("atendimento_id")
        .eq("org_id", str(org_id))
        .eq("agente_financeiro_id", str(agente_id))
        .limit(1)
        .execute()
    ).data or []
    if em_uso:
        raise ConflictError(
            "Este agente financeiro está em uso por um ou mais atendimentos. "
            "Desative-o (ativo = false) em vez de excluí-lo — os atendimentos "
            "que já o utilizam continuam exibindo-o."
        )

    (
        _t(client)
        .delete()
        .eq("org_id", str(org_id))
        .eq("id", str(agente_id))
        .execute()
    )


def _e_duplicata(exc: Exception) -> bool:
    """Is this the unique-name violation, rather than any other failure?

    Matched on the constraint NAME, not on the word "duplicate": the message
    text varies by driver and locale, and a substring match on "unique" would
    also catch an unrelated index. Anything this does not recognise is
    re-raised — an unknown database error must not be reported as "name taken".
    """
    texto = str(getattr(exc, "message", "") or exc)
    return "uq_sw_agentes_financeiros_org_nome" in texto


__all__ = [
    "EDITAVEIS",
    "FIELDS",
    "atualizar",
    "criar",
    "listar",
    "obter",
    "remover",
]
