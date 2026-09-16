"""`SupabaseUsageSink.record()` — the `supports_image_columns` opt-in.

Per the NOC-REMEDIATE[llm-usage-image-columns] resolution (edicao-fotos
Wave 1 W1 migrations slice): the four image-edit columns
(image_input_tokens / image_output_tokens / model_version / batch) must
be written ONLY when the consumer's own `<schema>.llm_usage` table was
created from `llm_usage.sql.template` (or widened to match it) — writing
them against `erp-imobiliario`'s 020 or `therapy-platform`'s 006 shape
would fail the insert. Default `False` must keep every existing
consumer's row shape byte-identical.

Pure DI stub client — no monkeypatching of our own code.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.integrations.llm.usage import SupabaseUsageSink, UsageEvent


class _StubQueryBuilder:
    def __init__(self, sink: "_StubDbClient", schema: str, table: str) -> None:
        self._sink = sink
        self._schema = schema
        self._table = table
        self._row: dict | None = None

    def insert(self, row: dict) -> "_StubQueryBuilder":
        self._row = row
        return self

    def execute(self) -> None:
        self._sink.inserted_payloads.append(
            {"schema": self._schema, "table": self._table, "row": self._row}
        )


class _StubSchemaBuilder:
    def __init__(self, sink: "_StubDbClient", schema: str) -> None:
        self._sink = sink
        self._schema = schema

    def table(self, table: str) -> _StubQueryBuilder:
        return _StubQueryBuilder(self._sink, self._schema, table)


class _StubDbClient:
    """Minimal Supabase-client stand-in. Records every insert payload for
    assertions — mirrors `MockRequestBuilder.inserted_payloads`'s read-side
    shape (`KB § PATTERNS/backend/di-test-seam.md`)."""

    def __init__(self) -> None:
        self.inserted_payloads: list[dict] = []

    def schema(self, name: str) -> _StubSchemaBuilder:
        return _StubSchemaBuilder(self, name)


def _make_event(**overrides) -> UsageEvent:
    base = dict(
        provider="openai",
        model="gpt-image-2.5-sunburst",
        operation="image_edit",
        org_id="org-1",
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
        image_input_tokens=1200,
        image_output_tokens=3400,
        cost_estimate_usd=0.12,
        at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        model_version="gpt-image-2.5-sunburst-2026-09-08",
        batch=False,
    )
    base.update(overrides)
    return UsageEvent(**base)


@pytest.mark.asyncio
async def test_default_omits_image_columns_for_narrow_schema() -> None:
    """Default False — the erp/therapy narrow-shape safety net."""
    db = _StubDbClient()
    sink = SupabaseUsageSink(db, schema="erp", table="llm_usage")

    await sink.record(_make_event())

    row = db.inserted_payloads[0]["row"]
    for key in ("image_input_tokens", "image_output_tokens", "model_version", "batch"):
        assert key not in row, f"{key} must not be written when supports_image_columns=False"
    assert row["org_id"] == "org-1"
    assert row["cost_estimate_usd"] == 0.12


@pytest.mark.asyncio
async def test_opt_in_writes_image_columns_for_wide_schema() -> None:
    """`supports_image_columns=True` — the llm_usage.sql.template shape."""
    db = _StubDbClient()
    sink = SupabaseUsageSink(
        db, schema="social_wiring", table="llm_usage", supports_image_columns=True
    )

    await sink.record(_make_event())

    row = db.inserted_payloads[0]["row"]
    assert row["image_input_tokens"] == 1200
    assert row["image_output_tokens"] == 3400
    assert row["model_version"] == "gpt-image-2.5-sunburst-2026-09-08"
    assert row["batch"] is False
