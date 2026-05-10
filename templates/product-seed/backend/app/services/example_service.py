"""
Example service — placeholder business logic for the new product to fill in.

Pattern: routers stay thin; services own the IO + transformations. A
service is constructed per-request from the user-scoped Supabase client
so RLS policies bind to the JWT identity. **Never** hold a long-lived
service singleton with an admin client unless the operation truly needs
to bypass RLS (deliberate seam, document the why inline).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID


class ExampleServiceError(Exception):
    """Domain-level failure surfaced to the router as a 4xx/5xx."""


class ExampleService:
    """Owns CRUD + business rules for the ``example`` domain.

    TODO(new-product): rename to your domain (``UploadService``,
    ``VideoCacheService``, …) and replace the placeholder methods with
    the real DB calls. Keep the constructor's ``client`` typed loosely
    (``Any``) — Supabase's Python client does not export a stable type.
    """

    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = org_id

    async def list(self, *, limit: int = 50, cursor: str | None = None) -> dict:
        """List rows scoped to ``self._org_id`` (RLS already enforces).

        TODO(new-product): replace with the real query. The shape returned
        here mirrors ``ExampleListResponse`` so the router can cast directly.
        """
        raise NotImplementedError("ExampleService.list — fill in")

    async def create(self, *, payload: dict) -> dict:
        """Insert a new row. RLS rejects writes outside ``org_id``.

        TODO(new-product): replace with the real insert. Return the
        inserted row shaped like ``ExampleOut``.
        """
        raise NotImplementedError("ExampleService.create — fill in")
