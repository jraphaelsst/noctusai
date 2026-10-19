"""Who may see a Lais contato (lais-build-contract A7 + DECISIONS 2026-10-15 #3) -- ONE rule, every route.

The OWNER of a contato is its `responsavel_user_id` (the attendant), else the `user_id` of the
whatsapp connection the contato arrived on. A contato is visible to:

  * an org owner/admin (any contato of the org), and
  * its owner (responsavel -> connection owner).

Any other member of the SAME org gets `403 sem_acesso`. A contato of ANOTHER org (or a missing id) is
`404 contato_nao_encontrado` -- never 403 across orgs, so ids cannot be probed. There is no shared /
public variant of this check anywhere: the history link needs a login too.

Every per-contato Lais route calls `exigir_contato` (single contato) or `filtrar_contatos` /
`filtrar_por_contato` (lists); nothing re-implements the predicate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

T_CONTATOS = "lais_contatos"
T_CONEXOES = "whatsapp_connections"
_IN_LOTE = 200


@dataclass(frozen=True)
class AcessoCtx:
    """The caller, as the access rule needs it. `admin` = org owner/admin IN the selected org."""

    org_id: UUID
    user_id: str
    admin: bool


def contexto(auth: Any, request: Any = None) -> AcessoCtx:
    """Build the ctx from the legacy `(user, token, org_id)` auth tuple. The admin bit comes from the
    trusted `noctus_users` role (never `user_metadata`)."""
    from noctusai_lib.api.auth.session import is_org_admin_for

    from app.dependencies import coerce_org_uuid, get_core_client

    user = auth[0]
    return AcessoCtx(
        org_id=coerce_org_uuid(auth[2]),
        user_id=str(getattr(user, "id", "") or ""),
        admin=bool(is_org_admin_for(get_core_client(), auth, request)),
    )


def _sem_acesso() -> AppException:
    return AppException("sem_acesso", "Você não tem acesso a esta conversa.", status_code=403)


def _nao_encontrado() -> AppException:
    return AppException("contato_nao_encontrado", "Contato não encontrado.", status_code=404)


def donos_das_conexoes(client: Any, org_id: UUID | str, connection_ids: Iterable[Any]) -> dict[str, Optional[str]]:
    """`{connection_id: user_id}` for the connections of this org (batched `.in_()`)."""
    ids = sorted({str(c) for c in connection_ids if c})
    out: dict[str, Optional[str]] = {}
    for i in range(0, len(ids), _IN_LOTE):
        rows = (
            client.table(T_CONEXOES).select("id, user_id").eq("org_id", str(org_id))
            .in_("id", ids[i:i + _IN_LOTE]).execute().data or []
        )
        out.update({str(r["id"]): (str(r["user_id"]) if r.get("user_id") else None) for r in rows})
    return out


def dono_do_contato(contato: dict[str, Any], donos: dict[str, Optional[str]]) -> Optional[str]:
    """Responsavel, else the owner of the connection the contato came in on."""
    if contato.get("responsavel_user_id"):
        return str(contato["responsavel_user_id"])
    return donos.get(str(contato.get("connection_id")))


def pode_ver_contato(
    ctx: AcessoCtx, contato: dict[str, Any], donos: Optional[dict[str, Optional[str]]] = None,
    *, client: Any = None,
) -> bool:
    """The A7 predicate. `donos` (connection owners) is only consulted when the contato has no
    responsavel; pass `client` to have it loaded on demand."""
    if str(contato.get("org_id")) != str(ctx.org_id):
        return False
    if ctx.admin:
        return True
    if contato.get("responsavel_user_id"):
        return str(contato["responsavel_user_id"]) == ctx.user_id
    if donos is None:
        if client is None:
            return False
        donos = donos_das_conexoes(client, ctx.org_id, [contato.get("connection_id")])
    return donos.get(str(contato.get("connection_id"))) == ctx.user_id


def exigir_acesso(client: Any, ctx: AcessoCtx, contato: dict[str, Any]) -> dict[str, Any]:
    """404 for another org's contato, 403 `sem_acesso` for a same-org stranger; the contato otherwise."""
    if str(contato.get("org_id")) != str(ctx.org_id):
        raise _nao_encontrado()
    if not pode_ver_contato(ctx, contato, client=client):
        raise _sem_acesso()
    return contato


def exigir_contato(client: Any, ctx: AcessoCtx, contato_id: UUID | str) -> dict[str, Any]:
    """Load a contato by id and apply the rule (the lookup is NOT org-filtered on purpose: another
    org's id and a missing id must be indistinguishable -> both 404)."""
    rows = client.table(T_CONTATOS).select("*").eq("id", str(contato_id)).limit(1).execute().data or []
    if not rows:
        raise _nao_encontrado()
    return exigir_acesso(client, ctx, rows[0])


def filtrar_contatos(client: Any, ctx: AcessoCtx, contatos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The contatos of `contatos` the caller may see (admins: all of their org)."""
    if ctx.admin:
        return [c for c in contatos if str(c.get("org_id")) == str(ctx.org_id)]
    donos = donos_das_conexoes(client, ctx.org_id, (c.get("connection_id") for c in contatos if not c.get("responsavel_user_id")))
    return [c for c in contatos if pode_ver_contato(ctx, c, donos)]


def filtrar_por_contato(
    client: Any, ctx: AcessoCtx, itens: list[dict[str, Any]], campo: str = "contato_id",
) -> list[dict[str, Any]]:
    """Items that hang off a contato (visitas, ...): keep those whose contato the caller may see."""
    if ctx.admin:
        return itens
    ids = sorted({str(i[campo]) for i in itens if i.get(campo)})
    contatos: list[dict[str, Any]] = []
    for k in range(0, len(ids), _IN_LOTE):
        contatos += (
            client.table(T_CONTATOS).select("*").eq("org_id", str(ctx.org_id))
            .in_("id", ids[k:k + _IN_LOTE]).execute().data or []
        )
    visiveis = {str(c["id"]) for c in filtrar_contatos(client, ctx, contatos)}
    return [i for i in itens if str(i.get(campo)) in visiveis]
