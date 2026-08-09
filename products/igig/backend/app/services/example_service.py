"""
Example service — the canonical page-scoped-CRUD business logic every
scaffolded product inherits and renames to its own domain.

Pattern: routers stay thin; services own the IO + transformations. A
service is constructed per-request from the user-scoped Supabase client
so RLS policies bind to the JWT identity. **Never** hold a long-lived
service singleton with an admin client unless the operation truly needs
to bypass RLS (deliberate seam, document the why inline).

This implements the full lifecycle — list / get / create / update /
soft-delete — against ``seed.examples`` (migration 003). It is the
backend half of the product-internal-wiring rule's *page-scoped CRUD*
mandate (KB § PATTERNS/product-internal-wiring.md): the page that lists
an entity is the page that manages it, so the entity needs a real CRUD
service end-to-end.

TODO(new-product): rename ``Example`` → your domain (``UploadService``,
``VideoService``, …), rename the table, and replace the placeholder
``title``/``description`` columns with your real fields.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

_TABLE = "examples"


class ExampleServiceError(Exception):
    """Domain-level failure surfaced to the router as a 4xx/5xx."""


class ExampleService:
    """Owns CRUD + business rules for the ``example`` domain.

    The ``client`` is the user-scoped, schema-bound Supabase client
    (``get_user_client(token)`` → schema ``seed``); RLS enforces org
    isolation, so reads/updates/deletes do not need a manual ``org_id``
    filter. Writes still set ``org_id`` so the row satisfies the
    ``WITH CHECK`` policy.
    """

    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = org_id

    async def list(self, *, limit: int = 50, cursor: str | None = None) -> dict:
        """List active rows for the caller's org (newest first).

        Returns the shape ``ExampleListResponse`` casts directly.
        ``cursor`` is accepted for forward-compat with the seed's
        cursor-paginated list contract; the placeholder returns the
        first page only (``next_cursor=None``).
        """
        result = (
            self._client.table(_TABLE)
            .select("*")
            .eq("ativo", True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {"items": result.data or [], "next_cursor": None}

    async def get(self, *, example_id: str | UUID) -> dict | None:
        """Fetch one row by id (RLS scopes to the caller's org)."""
        result = (
            self._client.table(_TABLE)
            .select("*")
            .eq("id", str(example_id))
            .maybe_single()
            .execute()
        )
        return result.data or None

    async def create(self, *, payload: dict) -> dict:
        """Insert a new row, stamping ``org_id`` for the RLS WITH CHECK."""
        row = {**payload, "org_id": str(self._org_id)}
        result = self._client.table(_TABLE).insert(row).execute()
        if not result.data:
            raise ExampleServiceError("insert returned no row")
        return result.data[0]

    async def update(self, *, example_id: str | UUID, payload: dict) -> dict | None:
        """Patch an existing row. Returns the updated row, or ``None`` if absent."""
        result = (
            self._client.table(_TABLE)
            .update(payload)
            .eq("id", str(example_id))
            .execute()
        )
        return result.data[0] if result.data else None

    async def delete(self, *, example_id: str | UUID) -> bool:
        """Soft-delete (flip ``ativo``) so the page can reactivate it.

        Soft-delete is the canonical default — the listing filters
        ``ativo=True``, and an admin/include-inactive view can surface +
        reactivate, mirroring the core admin-products fix that the
        product-internal-wiring rule was born from.
        """
        result = (
            self._client.table(_TABLE)
            .update({"ativo": False})
            .eq("id", str(example_id))
            .execute()
        )
        return bool(result.data)
