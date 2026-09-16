"""Real-Supabase smoke test for `RealSupabasePointsLedger`.

This slice ships **no migration** — the points table lives in the
consuming product's own schema (see `ledger.py`'s module docstring), so
there is no live table yet to write real rows into. This test instead
proves the REAL adapter's error-propagation contract against a REAL
Postgrest error shape (not a synthetic mock exception): a genuine
non-`23505` failure (INSERT against a table that does not exist) MUST
propagate, never be swallowed as "already claimed". It never writes any
row that would need cleanup.

Skips **loudly** — with a reason, never silently passing — when
`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` are absent from the
environment.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.engagement import PointAward
from noctusai_lib.domain.engagement.ledger import RealSupabasePointsLedger

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

pytestmark = pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY,
    reason=(
        "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in the environment — "
        "realdb test for RealSupabasePointsLedger skipped (this slice ships no "
        "migration; see noctusai_lib.domain.engagement.ledger module docstring)"
    ),
)


def _real_client():
    from supabase import create_client

    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def test_record_propagates_a_real_non_unique_violation_error() -> None:
    """The consuming product's engagement-points table does not exist
    yet. A real INSERT against a nonexistent table must raise — never
    be treated as an idempotent-duplicate no-op — proving
    `record()`'s `_is_unique_violation` narrowing lets a genuine,
    unrelated Postgrest error through instead of masking it."""
    client = _real_client()
    ledger = RealSupabasePointsLedger(
        client,
        schema_name="public",
        table_name=f"engagement_points_ledger_does_not_exist_{uuid.uuid4().hex}",
    )
    award = PointAward(
        member_id="realdb-smoke-member",
        source="platform",
        action="post",
        points=1,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=str(uuid.uuid4()),
    )
    with pytest.raises(Exception):
        ledger.record(award)
