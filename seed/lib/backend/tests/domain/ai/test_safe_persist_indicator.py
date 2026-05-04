"""Unit tests for `noctusai_lib.domain.ai.safe_persist_indicator`.

Surfaces the byte-identical `_persist_indicator` wrapper shipped today in
PF + ERP routers (filed by `projects/ai-plumbing-seed-absorption/`,
2026-05-04). The seed surface preserves their behavior identically:

  - happy path → returns the persisted row dict.
  - persist failure → returns the would-have-inserted payload with
    `id=None` + `persist_error=str(e)` and emits a logger.warning when
    a logger is supplied.

The product-side `_persist_indicator` wrappers can be deleted once the
PF / ERP migration cycles consume this surface.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from noctusai_lib.domain.ai import safe_persist_indicator


class _StubExecuteResult:
    def __init__(self, data):
        self.data = data
        self.count = None
        self.error = None


class _RecordingChain:
    """Records the call sequence + returns canned `.execute()` results.

    Mirrors the stub used by `test_ai_outputs.py::TestPersistOutput` so
    these tests stay shape-consistent with the existing persist-output
    tests they sit beside.
    """

    def __init__(self, recorded: dict, canned_data, *, raise_on_execute: Exception | None = None):
        self._recorded = recorded
        self._canned = canned_data
        self._raise_on_execute = raise_on_execute

    def schema(self, name):
        self._recorded["schema"] = name
        return self

    def table(self, name):
        self._recorded["table"] = name
        return self

    def insert(self, payload):
        self._recorded["insert"] = payload
        return self

    def execute(self):
        if self._raise_on_execute is not None:
            raise self._raise_on_execute
        return _StubExecuteResult(self._canned)


# ---------------------------------------------------------------------------
# Happy path — service-shaped dict → AIOutput → persist_output
# ---------------------------------------------------------------------------


class TestSafePersistIndicatorHappyPath:
    def test_full_dict_persists_and_returns_row(self):
        recorded: dict = {}
        canned_row = {
            "id": "row-1",
            "ref_type": "transacao",
            "ref_id": "tx-1",
            "kind": "classification",
            "label": "Categoria: Mercado",
        }
        stub = _RecordingChain(recorded, [canned_row])

        out = {
            "kind": "classification",
            "label": "Categoria: Mercado",
            "score": 0.92,
            "chip": "Mercado",
            "explanation": "Texto contém 'mercado'",
            "confidence": 0.92,
            "model_version": "gpt-4o-mini",
            "prompt_version": "pf-categorize@v1",
        }
        result = safe_persist_indicator(
            stub,
            schema="personal-finance",
            ref_type="transacao",
            ref_id="tx-1",
            out=out,
        )

        assert recorded["schema"] == "personal-finance"
        assert recorded["table"] == "ai_outputs"
        assert recorded["insert"]["ref_type"] == "transacao"
        assert recorded["insert"]["kind"] == "classification"
        assert recorded["insert"]["score"] == 0.92
        assert recorded["insert"]["chip"] == "Mercado"
        # No persist_error / id=None on happy path — caller gets the persisted row.
        assert result == canned_row
        assert "persist_error" not in result

    def test_minimum_keys_only_kind_and_label(self):
        """Only `kind` and `label` are required — every other key is optional."""
        recorded: dict = {}
        canned_row = {"id": "row-2", "ref_type": "ativo", "ref_id": "a-1", "kind": "flag", "label": "ok"}
        stub = _RecordingChain(recorded, [canned_row])

        result = safe_persist_indicator(
            stub,
            schema="erp",
            ref_type="ativo",
            ref_id="a-1",
            out={"kind": "flag", "label": "ok"},
        )

        # Optional keys land as None in the AIOutput → payload.
        assert recorded["insert"]["score"] is None
        assert recorded["insert"]["chip"] is None
        assert recorded["insert"]["confidence"] is None
        assert result == canned_row

    def test_extra_keys_in_out_are_ignored(self):
        """Callers may carry e.g. `matched_categoria_id` — wrapper ignores it."""
        recorded: dict = {}
        stub = _RecordingChain(recorded, [{"id": "row-3"}])

        safe_persist_indicator(
            stub,
            schema="personal-finance",
            ref_type="transacao",
            ref_id="tx-2",
            out={
                "kind": "classification",
                "label": "L",
                "matched_categoria_id": "cat-7",  # extra — must not appear in payload
                "downstream_marker": True,
            },
        )

        assert "matched_categoria_id" not in recorded["insert"]
        assert "downstream_marker" not in recorded["insert"]

    def test_schema_none_skips_schema_chain(self):
        """`public`-schema callers pass `schema=None`."""
        recorded: dict = {}
        stub = _RecordingChain(recorded, [{"id": "row-4"}])

        safe_persist_indicator(
            stub,
            schema=None,
            ref_type="x",
            ref_id="y",
            out={"kind": "flag", "label": "z"},
        )

        assert "schema" not in recorded
        assert recorded["table"] == "ai_outputs"


# ---------------------------------------------------------------------------
# Failure path — persist_output raising → fallback payload + logger.warning
# ---------------------------------------------------------------------------


class TestSafePersistIndicatorFailurePath:
    def test_persist_failure_returns_payload_with_id_none_and_error(self):
        recorded: dict = {}
        boom = RuntimeError("supabase 500 boom")
        stub = _RecordingChain(recorded, None, raise_on_execute=boom)

        out = {
            "kind": "score",
            "label": "Lead score: 85",
            "score": 0.85,
            "chip": "Hot",
        }
        result = safe_persist_indicator(
            stub,
            schema="erp",
            ref_type="cliente",
            ref_id="c-1",
            out=out,
        )

        # Returned payload mirrors what would have been inserted, plus
        # `id=None` and `persist_error=str(e)`.
        assert result["id"] is None
        assert result["persist_error"] == "supabase 500 boom"
        assert result["ref_type"] == "cliente"
        assert result["ref_id"] == "c-1"
        assert result["kind"] == "score"
        assert result["label"] == "Lead score: 85"
        assert result["score"] == 0.85
        assert result["chip"] == "Hot"

    def test_persist_failure_emits_warning_when_logger_provided(self):
        boom = RuntimeError("network timeout")
        stub = _RecordingChain({}, None, raise_on_execute=boom)
        logger = MagicMock(spec=logging.Logger)

        safe_persist_indicator(
            stub,
            schema="erp",
            ref_type="ativo",
            ref_id="a-99",
            out={"kind": "narrative", "label": "ok"},
            logger=logger,
        )

        assert logger.warning.called
        # Format string + args; assert the indicator id appears in args.
        args, _ = logger.warning.call_args
        # args[0] is the format string, args[1:] are the format args.
        assert "ai.persist_indicator failed" in args[0]
        assert "ativo" in args
        assert "a-99" in args

    def test_persist_failure_with_no_logger_is_silent(self):
        """When no logger is passed, failure still returns the fallback payload
        without raising — just no warning side-effect."""
        boom = ValueError("bad payload")
        stub = _RecordingChain({}, None, raise_on_execute=boom)

        result = safe_persist_indicator(
            stub,
            schema="erp",
            ref_type="ativo",
            ref_id="a-100",
            out={"kind": "flag", "label": "z"},
            logger=None,
        )

        assert result["id"] is None
        assert result["persist_error"] == "bad payload"


# ---------------------------------------------------------------------------
# Validation — invalid AIOutput shape still raises (we don't swallow
# construction errors; only persist_output failures).
# ---------------------------------------------------------------------------


class TestSafePersistIndicatorValidation:
    def test_invalid_kind_raises_at_construction(self):
        """Invalid `kind` is a programmer error — surface it loudly, do
        NOT return a degraded payload."""
        with pytest.raises(ValueError, match="not in"):
            safe_persist_indicator(
                MagicMock(),  # unused — never reaches persist_output
                schema="erp",
                ref_type="ativo",
                ref_id="a-1",
                out={"kind": "bogus", "label": "x"},
            )

    def test_missing_label_raises_at_construction(self):
        """Missing required `label` is a programmer error — fail fast."""
        with pytest.raises((KeyError, ValueError)):
            safe_persist_indicator(
                MagicMock(),
                schema="erp",
                ref_type="ativo",
                ref_id="a-1",
                out={"kind": "flag"},  # no label
            )
