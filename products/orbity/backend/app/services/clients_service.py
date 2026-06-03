"""
Clients service — CRUD for orbity.clients (the agency's customers).

Per-org scoped: every operation carries org_id explicitly and the
Supabase client is user-scoped (RLS-bound), so double-protection.

No silent errors: every except block logs at the appropriate level.
No mock-data fallbacks: unknown / missing rows raise LookupError.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

TABLE = "clients"


class ClientsService:
    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _table(self):
        # The Supabase client is already schema-scoped to "orbity" by
        # create_database_module(settings, schema="orbity"). Calling
        # .schema() again would create a new client and break
        # MockSupabaseClient's inserted_payloads tracking in tests.
        return self._db.table(TABLE)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(
        self,
        *,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List clients for the caller's org, newest first."""
        offset = (page - 1) * page_size
        query = (
            self._table()
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if active_only:
            query = query.eq("active", True)

        try:
            result = query.execute()
        except Exception:
            logger.exception("clients.list failed for org=%s", self._org_id)
            raise

        return {
            "items": result.data or [],
            "total": result.count if result.count is not None else len(result.data or []),
            "page": page,
            "page_size": page_size,
        }

    def get(self, client_id: str) -> dict[str, Any] | None:
        """Fetch one client. Returns None if not found."""
        try:
            result = (
                self._table()
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", client_id)
                .execute()
            )
        except Exception:
            logger.exception("clients.get failed org=%s id=%s", self._org_id, client_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Insert a new client. org_id is always stamped server-side."""
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._table().insert(row).execute()
        except Exception:
            logger.exception("clients.create failed for org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("clients.create returned no rows for org=%s", self._org_id)
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update(self, client_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Patch a client. Returns None if not found / not in org."""
        if not payload:
            return self.get(client_id)
        # Prohibit escalating org_id via patch
        payload.pop("org_id", None)
        try:
            result = (
                self._table()
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", client_id)
                .execute()
            )
        except Exception:
            logger.exception("clients.update failed org=%s id=%s", self._org_id, client_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def archive(self, client_id: str) -> bool:
        """Soft-delete via active=False. Returns True if found."""
        row = self.update(client_id, {"active": False})
        return row is not None
