"""Unit tests for `noctusai_lib.ai.outputs` — Tier 2 Phase 3 (P1 pattern).

Covers:
  - `AIOutput` dataclass validation (kind whitelist, label required, confidence range,
    chip/explanation soft-trim).
  - `persist_output` shape — payload omits id/created_at/updated_at; sets updated_at;
    routes through `db.schema(...).table('ai_outputs').insert(...)` chain.
  - `fetch_outputs_for` shape — orders newest-first, capped by limit.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.ai import AIOutput, persist_output, fetch_outputs_for


class TestAIOutputDataclass:
    def test_minimal_construction(self):
        out = AIOutput(
            ref_type="ativo", ref_id="a1", kind="classification", label="Mercado",
        )
        assert out.kind == "classification"
        assert out.label == "Mercado"
        assert out.score is None
        assert out.metadata == {}

    def test_full_construction(self):
        out = AIOutput(
            ref_type="ativo",
            ref_id="a1",
            kind="score",
            label="Lead score: 85",
            score=85.0,
            chip="Hot",
            explanation="Recent activity + high engagement",
            confidence=0.92,
            model_version="gpt-4o-mini",
            prompt_version="erp-leadscore@v1",
            metadata={"source": "ai_pipeline"},
        )
        assert out.confidence == 0.92
        assert out.metadata["source"] == "ai_pipeline"

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError, match="not in"):
            AIOutput(ref_type="x", ref_id="y", kind="bogus", label="z")

    def test_empty_label_raises(self):
        with pytest.raises(ValueError, match="label is required"):
            AIOutput(ref_type="x", ref_id="y", kind="flag", label="")

    def test_whitespace_label_raises(self):
        with pytest.raises(ValueError, match="label is required"):
            AIOutput(ref_type="x", ref_id="y", kind="flag", label="   ")

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError, match="out of"):
            AIOutput(ref_type="x", ref_id="y", kind="score", label="x", confidence=1.5)
        with pytest.raises(ValueError, match="out of"):
            AIOutput(ref_type="x", ref_id="y", kind="score", label="x", confidence=-0.1)

    def test_long_chip_is_trimmed_to_20(self):
        out = AIOutput(
            ref_type="x", ref_id="y", kind="flag", label="z",
            chip="a-very-long-chip-text-exceeding-twenty-chars",
        )
        assert len(out.chip) == 20

    def test_long_explanation_is_trimmed_to_280(self):
        out = AIOutput(
            ref_type="x", ref_id="y", kind="flag", label="z",
            explanation="x" * 500,
        )
        assert len(out.explanation) == 280

    def test_to_insert_payload_omits_db_managed_fields(self):
        out = AIOutput(
            ref_type="x", ref_id="y", kind="flag", label="z",
            id="should-be-omitted",
            created_at="should-be-omitted",
            updated_at="should-be-omitted",
        )
        payload = out.to_insert_payload()
        assert "id" not in payload
        assert "created_at" not in payload
        assert "updated_at" not in payload
        assert payload["ref_type"] == "x"
        assert payload["label"] == "z"


class _StubExecuteResult:
    def __init__(self, data):
        self.data = data
        self.count = None
        self.error = None


class _StubChain:
    """Records the call sequence + returns a canned `.execute()` result."""

    def __init__(self, recorded: dict, canned_data):
        self._recorded = recorded
        self._canned = canned_data

    def schema(self, name):
        self._recorded["schema"] = name
        return self

    def table(self, name):
        self._recorded["table"] = name
        return self

    def insert(self, payload):
        self._recorded["insert"] = payload
        return self

    def select(self, *args, **kwargs):
        self._recorded["select"] = (args, kwargs)
        return self

    def eq(self, column, value):
        self._recorded.setdefault("filters", []).append((column, value))
        return self

    def order(self, column, **kwargs):
        self._recorded["order"] = (column, kwargs)
        return self

    def limit(self, n):
        self._recorded["limit"] = n
        return self

    def execute(self):
        return _StubExecuteResult(self._canned)


class TestPersistOutput:
    def test_routes_through_schema_table_insert_chain(self):
        recorded: dict = {}
        canned_row = {"id": "abc", "ref_type": "ativo", "ref_id": "a1", "kind": "score", "label": "L"}
        stub = _StubChain(recorded, [canned_row])
        out = AIOutput(ref_type="ativo", ref_id="a1", kind="score", label="L")
        persisted = persist_output(stub, schema="erp", output=out)
        assert recorded["schema"] == "erp"
        assert recorded["table"] == "ai_outputs"
        assert recorded["insert"]["ref_type"] == "ativo"
        assert "updated_at" in recorded["insert"]
        assert persisted == canned_row

    def test_no_schema_skips_schema_chain(self):
        recorded: dict = {}
        stub = _StubChain(recorded, [{"id": "x"}])
        out = AIOutput(ref_type="t", ref_id="i", kind="flag", label="L")
        persist_output(stub, schema=None, output=out)
        assert "schema" not in recorded
        assert recorded["table"] == "ai_outputs"


class TestFetchOutputsFor:
    def test_fetch_orders_newest_first_and_limits(self):
        recorded: dict = {}
        canned = [{"id": "1"}, {"id": "2"}]
        stub = _StubChain(recorded, canned)
        rows = fetch_outputs_for(stub, schema="erp", ref_type="ativo", ref_id="a1", limit=10)
        assert recorded["schema"] == "erp"
        assert recorded["table"] == "ai_outputs"
        assert ("ref_type", "ativo") in recorded["filters"]
        assert ("ref_id", "a1") in recorded["filters"]
        assert recorded["order"] == ("created_at", {"desc": True})
        assert recorded["limit"] == 10
        assert rows == canned

    def test_fetch_no_schema_skips_schema_chain(self):
        recorded: dict = {}
        stub = _StubChain(recorded, [])
        fetch_outputs_for(stub, schema=None, ref_type="x", ref_id="y")
        assert "schema" not in recorded
        assert recorded["table"] == "ai_outputs"
