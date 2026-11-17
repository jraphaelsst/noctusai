"""Tests for ``noctus.dev.projection_reconcile``.

Hermetic: the DB seam is ``migrate_product.FakeSqlExecutor`` (injected), the
registry and the active scope are passed in — no monkey-patching of our own
code (KB § PATTERNS/compliance/testing.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.migrate_product import FakeSqlExecutor  # noqa: E402
from tools.noctus.dev.projection_reconcile import (  # noqa: E402
    DEFAULT_REGISTRY,
    LogSpec,
    PairSpec,
    StateSpec,
    build_log_sql,
    build_state_sql,
    diff_projection,
    fold_log,
    projection_reconcile,
    read_active_scope,
    validate_pair,
)

PAIRS = {p.id: p for p in DEFAULT_REGISTRY}
FIN = PAIRS["finance.settled_cents@social-wiring"]
FUNIL = PAIRS["sw.pipeline.funil"]
PART = PAIRS["agents.thread_participante.estado"]
ACTIVE = {"agents", "core", "nosnolimiar", "seed", "social-wiring"}


def _settlement(entry, amount, kind="payment", reversed_=False):
    return {"entry_id": entry, "amount_cents": amount, "kind": kind, "_skip": reversed_}


def _move(card, stage, ts):
    return {"entidade_id": card, "para_etapa_id": stage, "_ord0": ts}


# ---------------------------------------------------------------------------
# fold — sum (finance)
# ---------------------------------------------------------------------------


class TestSumFold:
    def test_payments_minus_refunds(self):
        f = fold_log(FIN, [_settlement("e1", 1000), _settlement("e1", 300, "refund"), _settlement("e2", 50)])
        assert f.values == {("e1",): 700, ("e2",): 50}

    def test_reversed_settlement_contributes_nothing(self):
        f = fold_log(FIN, [_settlement("e1", 1000), _settlement("e1", 400, reversed_=True)])
        assert f.values == {("e1",): 1000}

    def test_order_independent(self):
        rows = [_settlement("e1", 1000), _settlement("e1", 300, "refund"), _settlement("e1", 5, reversed_=True)]
        assert fold_log(FIN, rows).values == fold_log(FIN, list(reversed(rows))).values

    def test_entry_without_settlements_compares_to_zero(self):
        d = diff_projection(FIN, [{"id": "e1", "settled_cents": 0}, {"id": "e2", "settled_cents": 10}], fold_log(FIN, []))
        assert d["status"] == "drift"
        assert d["compared"] == 2 and d["mismatches"] == 1
        assert d["mismatch_sample"] == [{"key": {"id": "e2"}, "state": 10, "folded": 0}]

    def test_consistent(self):
        d = diff_projection(
            FIN,
            [{"id": "e1", "settled_cents": 700}],
            fold_log(FIN, [_settlement("e1", 1000), _settlement("e1", 300, "refund")]),
        )
        assert d["status"] == "consistent" and d["mismatches"] == 0


# ---------------------------------------------------------------------------
# fold — latest (pipeline / participant)
# ---------------------------------------------------------------------------


class TestLatestFold:
    def test_out_of_order_rows_fold_to_the_latest_timestamp(self):
        rows = [
            _move("c1", "s3", "2026-10-03T10:00:00.000000"),
            _move("c1", "s1", "2026-10-01T10:00:00.000000"),
            _move("c1", "s2", "2026-10-02T10:00:00.000000"),
        ]
        assert fold_log(FUNIL, rows).values == {("c1",): "s3"}

    def test_move_back_is_a_reversal_by_a_later_row(self):
        rows = [
            _move("c1", "s1", "2026-10-01T10:00:00.000000"),
            _move("c1", "s2", "2026-10-02T10:00:00.000000"),
            _move("c1", "s1", "2026-10-03T10:00:00.000000"),
        ]
        d = diff_projection(FUNIL, [{"id": "c1", "etapa_id": "s1"}], fold_log(FUNIL, rows))
        assert d["status"] == "consistent"

    def test_stale_card_stage_is_drift(self):
        d = diff_projection(
            FUNIL,
            [{"id": "c1", "etapa_id": "s1"}],
            fold_log(FUNIL, [_move("c1", "s2", "2026-10-02T10:00:00.000000")]),
        )
        assert d["status"] == "drift"
        assert d["mismatch_sample"] == [{"key": {"id": "c1"}, "state": "s1", "folded": "s2"}]

    def test_card_without_movement_is_unlogged_not_compared(self):
        d = diff_projection(FUNIL, [{"id": "c1", "etapa_id": "s1"}], fold_log(FUNIL, []))
        assert d["status"] == "consistent" and d["unlogged"] == 1 and d["compared"] == 0
        assert d["vacuous"] is True

    def test_tie_with_different_values_is_ambiguous_inconclusive(self):
        ts = "2026-10-02T10:00:00.000000"
        f = fold_log(FUNIL, [_move("c1", "s1", ts), _move("c1", "s2", ts)])
        d = diff_projection(FUNIL, [{"id": "c1", "etapa_id": "s1"}], f)
        assert d["status"] == "inconclusive" and d["ambiguous"] == 1

    def test_tie_resolved_by_a_later_row(self):
        ts = "2026-10-02T10:00:00.000000"
        f = fold_log(FUNIL, [_move("c1", "s1", ts), _move("c1", "s2", ts), _move("c1", "s3", "2026-10-03T00:00:00.000000")])
        assert f.ambiguous == set() and f.values == {("c1",): "s3"}

    def test_orphan_log_keys_counted_not_drift(self):
        d = diff_projection(FUNIL, [], fold_log(FUNIL, [_move("gone", "s1", "2026-10-01T00:00:00.000000")]))
        assert d["status"] == "consistent" and d["orphan_log_keys"] == 1

    def test_composite_key(self):
        rows = [
            {"thread_id": "t", "agent_id": "a", "para": "ativo", "_ord0": "2026-10-01T00:00:00.000000"},
            {"thread_id": "t", "agent_id": "a", "para": "transferido", "_ord0": "2026-10-02T00:00:00.000000"},
        ]
        d = diff_projection(PART, [{"thread_id": "t", "agent_id": "a", "estado": "ativo"}], fold_log(PART, rows))
        assert d["status"] == "drift"
        assert d["mismatch_sample"][0]["key"] == {"thread_id": "t", "agent_id": "a"}

    def test_sample_is_bounded(self):
        state = [{"id": f"c{i}", "etapa_id": "x"} for i in range(20)]
        log = [_move(f"c{i}", "y", "2026-10-01T00:00:00.000000") for i in range(20)]
        d = diff_projection(FUNIL, state, fold_log(FUNIL, log), sample=3)
        assert d["mismatches"] == 20 and len(d["mismatch_sample"]) == 3


# ---------------------------------------------------------------------------
# registry + SQL construction
# ---------------------------------------------------------------------------


class TestRegistryAndSql:
    def test_every_registered_pair_validates(self):
        for pair in DEFAULT_REGISTRY:
            validate_pair(pair)

    def test_ids_unique(self):
        assert len(PAIRS) == len(DEFAULT_REGISTRY)

    def test_registry_covers_active_products_only(self):
        active = read_active_scope(REPO_ROOT)
        assert active is not None
        assert {p.product for p in DEFAULT_REGISTRY} <= active

    def test_sql_is_one_select(self):
        for pair in DEFAULT_REGISTRY:
            for sql in (build_state_sql(pair, max_rows=10), build_log_sql(pair, max_rows=10)):
                assert sql.startswith("SELECT ") and ";" not in sql and sql.endswith("LIMIT 11")

    def test_log_sql_shapes(self):
        assert build_log_sql(FIN, max_rows=1) == (
            "SELECT entry_id, amount_cents, kind, (reversed_at IS NOT NULL) AS _skip "
            "FROM social_wiring.fin_settlements LIMIT 2"
        )
        sql = build_log_sql(FUNIL, max_rows=1)
        assert "WHERE pipeline = 'funil'" in sql and "AS _ord0" in sql
        assert build_state_sql(PAIRS["finance.settled_cents@core"], max_rows=1) == (
            "SELECT id, settled_cents FROM public.fin_entries LIMIT 2"
        )

    @pytest.mark.parametrize(
        "bad",
        [
            PairSpec("x", "p", "s; drop", "", StateSpec("t", ("id",), "v"), LogSpec("l", ("k",), "sum", "v")),
            PairSpec("x", "p", "s", "", StateSpec("t", ("id",), "v"),
                     LogSpec("l", ("k",), "latest", "v", order=("ts",), where=(("c", "a' OR 1=1"),)),
                     missing_log="unlogged"),
            PairSpec("x", "p", "s", "", StateSpec("t", ("id",), "v"), LogSpec("l", ("k",), "latest", "v")),
            PairSpec("x", "p", "s", "", StateSpec("t", ("id",), "v"), LogSpec("l", ("k", "j"), "sum", "v")),
            PairSpec("x", "p", "s", "", StateSpec("t", ("id",), "v"), LogSpec("l", ("k",), "median", "v")),
            PairSpec("x", "p", "s", "", StateSpec("t", ("id",), "v"), LogSpec("l", ("k",), "latest", "v", order=("ts",))),
        ],
    )
    def test_malformed_pair_refused(self, bad):
        with pytest.raises(ValueError):
            validate_pair(bad)


# ---------------------------------------------------------------------------
# orchestration through the executor seam
# ---------------------------------------------------------------------------


def _fake_for(pair, state_rows, log_rows):
    return FakeSqlExecutor(preset_rows={
        build_state_sql(pair, max_rows=1000): state_rows,
        build_log_sql(pair, max_rows=1000): log_rows,
    })


class TestOrchestration:
    def test_consistent_pair_is_ok(self):
        fake = _fake_for(FIN, [{"id": "e1", "settled_cents": 1000}], [_settlement("e1", 1000)])
        r = projection_reconcile(pairs=[FIN.id], executor=fake, max_rows=1000, active_scope=ACTIVE)
        assert r["ok"] is True and r["status"] == "consistent" and r["exit_code"] == 0
        assert all(sql.startswith("SELECT ") for sql in fake.executed)

    def test_drift_is_red(self):
        fake = _fake_for(FIN, [{"id": "e1", "settled_cents": 1}], [_settlement("e1", 1000)])
        r = projection_reconcile(pairs=[FIN.id], executor=fake, max_rows=1000, active_scope=ACTIVE)
        assert r["status"] == "drift" and r["ok"] is False and r["exit_code"] == 1

    def test_missing_table_is_inconclusive(self):
        fake = FakeSqlExecutor(fail_on={"fin_entries"})
        r = projection_reconcile(pairs=[FIN.id], executor=fake, active_scope=ACTIVE)
        assert r["status"] == "inconclusive" and r["ok"] is False
        assert r["pairs"][0]["status"] == "inconclusive"
        assert "state query failed" in r["pairs"][0]["reason"]

    def test_too_many_rows_is_inconclusive(self):
        fake = FakeSqlExecutor(preset_rows={"fin_entries": [{"id": str(i), "settled_cents": 0} for i in range(3)]})
        r = projection_reconcile(pairs=[FIN.id], executor=fake, max_rows=2, active_scope=ACTIVE)
        assert r["status"] == "inconclusive" and "max_rows" in r["pairs"][0]["reason"]

    def test_drift_outranks_inconclusive(self):
        fake = FakeSqlExecutor(
            preset_rows={
                build_state_sql(FIN, max_rows=1000): [{"id": "e1", "settled_cents": 5}],
                build_log_sql(FIN, max_rows=1000): [],
            },
            fail_on={"pipeline_movimentos"},
        )
        r = projection_reconcile(pairs=[FIN.id, FUNIL.id], executor=fake, max_rows=1000, active_scope=ACTIVE)
        assert r["status"] == "drift"
        assert r["summary"] == {"consistent": 0, "drift": 1, "inconclusive": 1, "skipped": 0}

    def test_asleep_product_skipped_and_never_green(self):
        fake = FakeSqlExecutor()
        r = projection_reconcile(pairs=[FIN.id], executor=fake, active_scope={"core"})
        assert r["pairs"][0]["status"] == "skipped"
        assert r["status"] == "inconclusive" and r["ok"] is False
        assert fake.executed == []

    def test_unknown_pair_refused(self):
        r = projection_reconcile(pairs=["nope"], executor=FakeSqlExecutor(), active_scope=ACTIVE)
        assert r["status"] == "error" and r["exit_code"] == 2 and "nope" in r["error"]

    def test_product_filter(self):
        fake = FakeSqlExecutor()
        r = projection_reconcile(product="agents", executor=fake, active_scope=ACTIVE)
        assert {p["id"] for p in r["pairs"]} == {"finance.settled_cents@agents", "agents.thread_participante.estado"}

    def test_unknown_product_refused(self):
        r = projection_reconcile(product="igig", executor=FakeSqlExecutor(), active_scope=ACTIVE)
        assert r["status"] == "error"

    def test_sample_clamped(self):
        state = [{"id": f"e{i}", "settled_cents": 1} for i in range(80)]
        fake = _fake_for(FIN, state, [])
        r = projection_reconcile(pairs=[FIN.id], executor=fake, max_rows=1000, sample=500, active_scope=ACTIVE)
        assert r["pairs"][0]["mismatches"] == 80 and len(r["pairs"][0]["mismatch_sample"]) == 50
