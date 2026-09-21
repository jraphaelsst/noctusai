"""The `InteressadosStore` seam — public "receber futuras comunicações" signup.

Separate from `app.knowledge.KnowledgeStore` on purpose: that seam is
org-scoped (every method takes `org_id` first — contract §A.11), while
`academia_de_reciclagem.interessados` is product-level — a public visitor
submitting the popup has no org. Mirrors the shape (Protocol + Fake + Pg +
factory) `app/knowledge/store.py` established, at a much smaller surface
(3 methods, no revisions, no `Provenance` — this table has no per-write
audit trail requirement in the contract).
"""
from __future__ import annotations

from typing import Protocol
from uuid import UUID


class InteressadosStore(Protocol):
    """The seam both routers (`POST /api/public/interessados` and the
    admin `GET`/`DELETE /api/interessados`) go through. Every method is
    `async`."""

    async def upsert(
        self,
        *,
        nome: str,
        whatsapp: str,
        email: str,
        origem: str | None,
        consentimento_versao: str,
    ) -> None:
        """Insert a new row, or refresh an existing one matched on
        `lower(email)` (contract: "refresh nome, whatsapp, origem,
        consentimento_em, atualizado_em"). Never raises on a duplicate —
        that IS the expected, non-exceptional path."""
        ...

    async def list(self, *, limit: int, offset: int) -> tuple[list[dict], int]:
        """Newest-first page of rows + the total count (contract:
        `GET /api/interessados?limit=&offset=`)."""
        ...

    async def delete(self, interessado_id: UUID) -> bool:
        """`True` if a row was deleted, `False` if `interessado_id` did
        not match any row (the router maps that to 404)."""
        ...


__all__ = ["InteressadosStore"]
