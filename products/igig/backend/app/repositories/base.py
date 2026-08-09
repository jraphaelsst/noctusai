"""Base repository over the seed persistence seam.

Repositories are the product's data vocabulary: routers and services speak
``ClienteRepository.listar_ativos(org_id)``, never
``store.list("cliente", org_id, QuerySpec(...))``. That indirection is the
whole point of the seam — when IgIg moves from SQLite to Supabase, the store
underneath changes and nothing here does.

Per-entity repositories live in the PRODUCT, not the seed: they encode IgIg's
domain, and `KB § PATTERNS/architect/seed-lib-layout.md` reserves the seed for
product-agnostic machinery. The generic ``RecordStore`` they compose is the
part that is shared.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.persistence import (
    Op,
    Order,
    QuerySpec,
    Record,
    RecordNotFound,
    RecordStore,
)

__all__ = ["BaseRepository", "RecordNotFound"]


class BaseRepository:
    """CRUD over one table, always org-scoped.

    Subclasses set :attr:`table` and add domain query methods. They do NOT
    re-implement CRUD — that is what this base is for, and a subclass that
    reaches past it into ``self._store`` for a plain get/list is the
    duplication the recurrence rule forbids.
    """

    #: Table this repository owns. Subclasses MUST set it.
    table: str = ""

    #: Default ordering for :meth:`listar` when the caller gives none.
    default_order: tuple[Order, ...] = (Order("created_at", descending=True),)

    def __init__(self, store: RecordStore) -> None:
        if not self.table:
            raise ValueError(f"{type(self).__name__} must declare `table`")
        self._store = store

    # ── CRUD ────────────────────────────────────────────────────────
    def criar(self, org_id: str, values: Record) -> Record:
        return self._store.insert(self.table, org_id, values)

    def buscar(self, org_id: str, record_id: str) -> Record:
        """Return one row. Raises ``RecordNotFound`` — never returns None.

        Callers translate that into a 404; a ``None`` return would make the
        miss easy to ignore, which is the silent-error shape this platform
        forbids.
        """
        return self._store.get(self.table, org_id, record_id)

    def listar(
        self,
        org_id: str,
        *,
        spec: QuerySpec | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Record]:
        spec = spec or QuerySpec()
        if spec.order_by == () and self.default_order:
            spec = QuerySpec(
                filters=spec.filters,
                order_by=self.default_order,
                limit=spec.limit,
                offset=spec.offset,
                columns=spec.columns,
            )
        if limit is not None or offset:
            spec = QuerySpec(
                filters=spec.filters,
                order_by=spec.order_by,
                limit=limit if limit is not None else spec.limit,
                offset=offset or spec.offset,
                columns=spec.columns,
            )
        return self._store.list(self.table, org_id, spec)

    def atualizar(self, org_id: str, record_id: str, values: Record) -> Record:
        return self._store.update(self.table, org_id, record_id, values)

    def remover(self, org_id: str, record_id: str) -> bool:
        return self._store.delete(self.table, org_id, record_id)

    def contar(self, org_id: str, *, spec: QuerySpec | None = None) -> int:
        return self._store.count(self.table, org_id, spec)

    # ── helpers for subclasses ──────────────────────────────────────
    def _por(self, column: str, value: Any, org_id: str) -> list[Record]:
        """Rows where ``column`` equals ``value`` — the commonest lookup."""
        return self.listar(org_id, spec=QuerySpec().with_filter(column, Op.EQ, value))
