"""Build a `social_wiring.imoveis` ROW the way Postgres would.

`_imovel_to_row` produces what the application WRITES. That is not the same
as what a `SELECT *` returns, because migration 062 added

    codigo_norm TEXT GENERATED ALWAYS AS (upper(btrim(codigo))) STORED

which Postgres materialises on every row and the application deliberately
never sends (a generated column is not writable). Any fake client seeded
straight from `_imovel_to_row` is therefore missing a column that
`ImoveisService.get` filters on — the query matches nothing and the test
fails for a reason that has nothing to do with what it is testing.

Extracted at N=3 (`tests/services/test_imoveis_service.py`,
`tests/services/test_whatsapp_intake_property_lookup.py`,
`tests/modules/youtube/test_upload_router.py` all hand-rolled the same
helper). The recurrence rule forbids shipping the fourth copy —
`KB § PATTERNS/architect/project-execution.md`.

Use this instead of calling `_imovel_to_row` directly whenever the row is
going to be READ back through a fake client. A test that only inspects the
write payload should keep calling `_imovel_to_row`, because that is
genuinely the write shape.
"""
from __future__ import annotations

from uuid import UUID

from noctusai_lib.domain.real_estate import Imovel

from app.services.imoveis_service import _imovel_to_row

__all__ = ["imovel_row"]


def imovel_row(codigo: str, org_id: UUID, synced_at: str, **kw) -> dict:
    """A row as `SELECT *` would return it, generated columns included."""
    imovel = Imovel(codigo=codigo, **kw)
    row = _imovel_to_row(imovel, org_id, synced_at)
    # Mirrors the migration-062 expression exactly. If that expression ever
    # changes, this line changes with it — one place, not four.
    row["codigo_norm"] = codigo.strip().upper()
    return row
