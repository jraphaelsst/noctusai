"""Colocated regression test for `check_transition_log_hand_written` (meta-detector: every keeper ships Test<CamelCase>)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed/lib/backend"))

from noctusai_lib.domain.sql_templates import guc_carveout_guard_sql  # noqa: E402
from noctusai_lib.domain.transition_log import TransitionLogConfig, transition_log_migration  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_transition_log_hand_written,
    TransitionLogPrimitiveMissing,
    transition_log_hand_written_scan,
)


def _repo(tmp_path: Path, sql: str, name: str = "099_x.sql") -> Path:
    d = tmp_path / "products" / "demo" / "backend" / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(sql, encoding="utf-8")
    return tmp_path


HAND_PAIR = """CREATE TABLE IF NOT EXISTS demo.deal_movimentos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL,
    deal_id uuid NOT NULL REFERENCES demo.deals(id) ON DELETE CASCADE,
    de_etapa_id uuid,
    para_etapa_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""
HAND_TRIGGER = """CREATE TABLE demo.lead_eventos (id uuid PRIMARY KEY, org_id uuid NOT NULL, tipo text NOT NULL);
CREATE OR REPLACE FUNCTION demo.lead_eventos_ro() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only'; END; $$;
CREATE TRIGGER lead_eventos_ro BEFORE UPDATE OR DELETE ON demo.lead_eventos FOR EACH ROW EXECUTE FUNCTION demo.lead_eventos_ro();
"""


class TestTransitionLogHandWritten:
    def test_clean_case_no_issues(self, tmp_path):
        assert check_transition_log_hand_written(repo_root=_repo(tmp_path, "CREATE TABLE demo.t (id uuid);\n")) == []

    def test_from_to_pair_is_flagged(self, tmp_path):
        (issue,) = check_transition_log_hand_written(repo_root=_repo(tmp_path, HAND_PAIR))
        assert issue["severity"] == "high" and "deal_movimentos" in issue["issue"] and "transition_log_migration" in issue["issue"]

    def test_append_only_trigger_on_a_history_table_is_flagged(self, tmp_path):
        (issue,) = check_transition_log_hand_written(repo_root=_repo(tmp_path, HAND_TRIGGER))
        assert "lead_eventos" in issue["issue"] and "append-only-trigger" in issue["issue"]

    def test_temporal_ranges_and_entity_pairs_are_not_transitions(self, tmp_path):
        sql = ("CREATE TABLE demo.precos (id uuid, valid_from date, valid_to date, data_de timestamptz, data_para timestamptz);\n"
               "CREATE TABLE demo.matches (id uuid, ativo_origem_id uuid, ativo_destino_id uuid);\n"
               "CREATE TABLE demo.agent_versions (id uuid);\n"
               "CREATE TRIGGER v_ro BEFORE UPDATE OR DELETE ON demo.agent_versions FOR EACH ROW EXECUTE FUNCTION demo.f();\n")
        assert check_transition_log_hand_written(repo_root=_repo(tmp_path, sql)) == []

    def test_the_primitive_render_and_a_guc_guard_render_pass(self, tmp_path):
        cfg = TransitionLogConfig(schema="demo", aggregate="deal", state_table="deals", state_column="stage")
        sql = transition_log_migration(cfg) + guc_carveout_guard_sql(schema="demo", table="imovel_historico", guc="demo.purge")
        assert check_transition_log_hand_written(repo_root=_repo(tmp_path, sql)) == []

    def test_a_reasoned_waiver_passes_and_a_bare_one_does_not(self, tmp_path):
        ok = "-- transition-log-ok: deal_movimentos imported verbatim from the vendor dump, read-only archive\n" + HAND_PAIR
        assert check_transition_log_hand_written(repo_root=_repo(tmp_path, ok)) == []
        bare = "-- transition-log-ok: deal_movimentos\n" + HAND_PAIR
        assert len(check_transition_log_hand_written(repo_root=_repo(tmp_path, bare, "100_y.sql"))) == 1  # the waiver is per file

    def test_a_table_a_later_migration_drops_is_not_live(self, tmp_path):
        """The chain is immutable (the old CREATE stays), but a LATER migration that drops the table retires the hit."""
        repo = _repo(tmp_path, HAND_PAIR, "099_x.sql")
        assert len(check_transition_log_hand_written(repo_root=repo)) == 1
        _repo(tmp_path, "DROP TABLE IF EXISTS demo.deal_movimentos;\n", "098_before.sql")
        assert len(check_transition_log_hand_written(repo_root=repo)) == 1  # a drop BEFORE the create is no retirement
        _repo(tmp_path, "-- DROP TABLE demo.deal_movimentos (a comment is not a drop)\n", "100_comment.sql")
        assert len(check_transition_log_hand_written(repo_root=repo)) == 1
        _repo(tmp_path, "DROP TABLE IF EXISTS demo.deal_movimentos;\n", "101_drop.sql")
        assert check_transition_log_hand_written(repo_root=repo) == []

    def test_real_repo_is_clean_against_the_baseline(self):
        assert check_transition_log_hand_written(repo_root=REPO_ROOT) == []

    def test_the_baseline_only_lists_live_hits(self):
        """Shrink-only ratchet: an entry whose shape is gone must be removed (else it silently re-admits a copy)."""
        import json

        legacy = set(json.loads((REPO_ROOT / "mcp/noctusai/tests/transition_log_hand_written_baseline.json").read_text())["legacy"])
        live = {f"{rel}::{table}" for rel, _l, table, _w in transition_log_hand_written_scan(REPO_ROOT)}
        assert legacy <= live, sorted(legacy - live)


class TestPrimitiveMissingIsLoud:
    """An un-importable primitive must raise / report naming the module -- never read every table as hand-written."""

    def _break_import(self, monkeypatch):
        # Simulates a tree whose noctusai_lib lacks the primitive (the environment, not our own code).
        monkeypatch.setitem(sys.modules, "noctusai_lib.domain.transition_log", None)

    def test_scan_raises_naming_the_module(self, tmp_path, monkeypatch):
        self._break_import(monkeypatch)
        with pytest.raises(TransitionLogPrimitiveMissing, match="transition_log"):
            transition_log_hand_written_scan(_repo(tmp_path, HAND_PAIR))

    def test_check_returns_one_high_issue_not_a_hit_per_table(self, tmp_path, monkeypatch):
        self._break_import(monkeypatch)
        issues = check_transition_log_hand_written(repo_root=_repo(tmp_path, HAND_PAIR))
        assert len(issues) == 1 and issues[0]["severity"] == "high" and "transition_log" in issues[0]["issue"]
