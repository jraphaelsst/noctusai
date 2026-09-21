"""`PgInteressadosStore` -- the real `InteressadosStore` over
Supabase/PostgREST.

WHY THE UPSERT IS SELECT-THEN-INSERT-OR-UPDATE, NOT `.upsert(on_conflict=)`
----------------------------------------------------------------------------
The contract's uniqueness rule is `UNIQUE on lower(email)` -- an
EXPRESSION index (`011_interessados.sql`), not a plain-column unique
constraint. PostgREST's `.upsert(data, on_conflict="col1,col2")` can only
target the literal column list of an existing unique/exclusion
constraint; it cannot resolve conflicts against an expression index. So
this store looks the row up by its already-lower-cased `email` column
(the app normalizes every write -- see `_email_key` below) and issues an
explicit INSERT or UPDATE, catching a `23505` race (two concurrent
submissions for the same brand-new address) by re-reading and falling
back to an UPDATE.

`atualizado_em` is NOT set here on the UPDATE path -- the
`set_atualizado_em_interessados` trigger (011) stamps it on every UPDATE,
so the app never has to remember to. `criado_em`'s DEFAULT covers INSERT.
`consentimento_em` has no trigger (it is a domain event, not a plain
row-touch timestamp) so both paths set it explicitly to "now" -- contract:
"refreshed on every re-submission".

NOC-REMEDIATE[test]: this module is NOT exercised by this slice's test
suite -- the dispatch brief forbids applying migrations to any database,
so there is no live Postgres to run it against here (same constraint
`app/knowledge/pg.py` notes for `PgKnowledgeStore`). The Protocol-
conformance suite in `tests/interessados/` runs exclusively against
`FakeInteressadosStore`. Written to be correct by inspection and mirrors
the Fake's invariants method-for-method; a first real integration pass
is still owed once a dev/staging DB exists. -- 2026-09-21
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

_UNIQUE_VIOLATION = "23505"


def _email_key(email: str) -> str:
    return email.strip().lower()


class PgInteressadosStore:
    """`InteressadosStore` over the product's own Supabase admin client.

    `admin` MUST already be schema-scoped to `academia_de_reciclagem`
    (i.e. `create_database_module(settings,
    schema="academia_de_reciclagem").get_admin_client()`) -- mirrors
    `PgKnowledgeStore`'s own constructor contract.
    """

    def __init__(self, admin: Client) -> None:
        self._admin = admin

    async def upsert(
        self,
        *,
        nome: str,
        whatsapp: str,
        email: str,
        origem: str | None,
        consentimento_versao: str,
    ) -> None:
        email_key = _email_key(email)
        consentimento_em = datetime.now(timezone.utc).isoformat()
        existing_id = self._find_id_by_email(email_key)
        if existing_id is not None:
            self._update(existing_id, nome, whatsapp, origem, consentimento_versao, consentimento_em)
            return

        insert_payload = {
            "nome": nome,
            "whatsapp": whatsapp,
            "email": email_key,
            "origem": origem,
            "consentimento_versao": consentimento_versao,
            "consentimento_em": consentimento_em,
        }
        try:
            self._admin.table("interessados").insert(insert_payload).execute()
        except APIError as exc:
            if getattr(exc, "code", None) != _UNIQUE_VIOLATION:
                raise
            # Race: another request inserted this email between our SELECT
            # and INSERT. The row now exists -- fall back to an UPDATE.
            retry_id = self._find_id_by_email(email_key)
            if retry_id is None:
                raise
            self._update(retry_id, nome, whatsapp, origem, consentimento_versao, consentimento_em)

    def _find_id_by_email(self, email_key: str) -> str | None:
        resp = (
            self._admin.table("interessados")
            .select("id")
            .eq("email", email_key)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0]["id"] if rows else None

    def _update(
        self,
        row_id: str,
        nome: str,
        whatsapp: str,
        origem: str | None,
        consentimento_versao: str,
        consentimento_em: str,
    ) -> None:
        self._admin.table("interessados").update(
            {
                "nome": nome,
                "whatsapp": whatsapp,
                "origem": origem,
                "consentimento_versao": consentimento_versao,
                "consentimento_em": consentimento_em,
            }
        ).eq("id", row_id).execute()

    async def list(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        resp = (
            self._admin.table("interessados")
            .select("*", count="exact")
            .order("criado_em", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return list(resp.data or []), resp.count or 0

    async def delete(self, interessado_id: UUID) -> bool:
        resp = (
            self._admin.table("interessados")
            .delete()
            .eq("id", str(interessado_id))
            .execute()
        )
        return bool(resp.data)


__all__ = ["PgInteressadosStore"]
