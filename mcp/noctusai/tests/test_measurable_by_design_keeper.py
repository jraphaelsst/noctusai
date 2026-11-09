"""``check_measurable_by_design`` -- owner rule 2026-11-09: every product feature GENERATES data.

Red + green fixtures for each rule, the exemption heuristics researched against the real migration tree
(KB § PATTERNS/architect/measurement-by-design.md), the escape marker, and the construction round-trip
(``scaffold_migration(with_table, with_eventos)`` output must pass the gate it exists to satisfy). Hermetic (tmp_path).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev import scaffold_migration as sm  # noqa: E402
from tools.noctus.dev.compliance import check_measurable_by_design  # noqa: E402

MIG = "products/p/backend/migrations/002_x.sql"


def _run(tmp_path: Path, sql: str, rel: str = MIG, extra: dict[str, str] | None = None):
    for r, body in {rel: sql, **(extra or {})}.items():
        f = tmp_path / r
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    esc: list[dict] = []
    return check_measurable_by_design(repo_root=tmp_path, paths=[rel], escapes_out=esc), esc


def _rules(out):
    return sorted(i["rule"] for i in out)


class TestMeasurableByDesign:
    """The detector's two pinned shapes: the true positive (an undated table with an event-less lifecycle) and the
    false-positive guard (the same intent done right, including the escape)."""

    def test_true_positive_undated_lifecycle_table(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.visitas (id uuid PRIMARY KEY, status text CHECK (status IN ('a','b')));")
        assert {"missing_created_at", "lifecycle_no_events"} <= set(_rules(out))

    def test_false_positive_guard_measurable_shape_is_clean(self, tmp_path):
        sql = ("CREATE TABLE p.visitas (id uuid PRIMARY KEY, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now(), "
               "status text CHECK (status IN ('a','b')));\n"
               "CREATE TABLE p.visitas_eventos (id uuid PRIMARY KEY, entidade_id uuid REFERENCES p.visitas(id), actor_id uuid, "
               "created_at timestamptz DEFAULT now());")
        out, _ = _run(tmp_path, sql)
        assert out == []


class TestCreatedAt:
    def test_domain_table_without_created_at_is_blocked(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.visitas (id uuid PRIMARY KEY, imovel_id uuid, nota text);")
        assert _rules(out) == ["missing_created_at"] and out[0]["severity"] == "high"

    def test_created_at_passes(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.visitas (id uuid PRIMARY KEY, nota text, created_at timestamptz NOT NULL DEFAULT now());")
        assert out == []

    def test_local_timestamp_name_with_default_now_passes(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.visitas (id uuid PRIMARY KEY, agendada_em timestamptz NOT NULL DEFAULT now(), nota text);")
        assert out == []

    def test_join_table_composite_pk_is_exempt(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.a_b (a_id uuid NOT NULL, b_id uuid NOT NULL, PRIMARY KEY (a_id, b_id));")
        assert out == []

    def test_singleton_config_row_natural_pk_is_exempt(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.destino (org_id uuid PRIMARY KEY, modo text, usuario_id uuid);")
        assert out == []

    def test_cache_and_config_names_are_exempt(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.retrieval_cache (id uuid PRIMARY KEY, k text, v jsonb);\n"
                                "CREATE TABLE p.app_settings (id uuid PRIMARY KEY, k text, v text);")
        assert out == []


class TestLifecycleNeedsEvents:
    ENTITY = ("CREATE TABLE p.visitas (id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), "
              "updated_at timestamptz NOT NULL DEFAULT now(), "
              "status text NOT NULL DEFAULT 'agendada' CHECK (status IN ('agendada','realizada','cancelada')));")

    def test_status_enum_without_event_capture_is_blocked(self, tmp_path):
        out, _ = _run(tmp_path, self.ENTITY)
        assert _rules(out) == ["lifecycle_no_events"] and out[0]["severity"] == "high"

    def test_companion_eventos_table_in_same_file_passes(self, tmp_path):
        sql = self.ENTITY + ("\nCREATE TABLE p.visitas_eventos (id uuid PRIMARY KEY, entidade_id uuid REFERENCES p.visitas(id), "
                             "actor_id uuid, occurred_at timestamptz NOT NULL DEFAULT now());")
        out, _ = _run(tmp_path, sql)
        assert out == []

    def test_companion_in_an_earlier_migration_of_the_product_passes(self, tmp_path):
        prior = ("CREATE TABLE p.visitas_transicoes (id uuid PRIMARY KEY, visita_id uuid, actor_id uuid, "
                 "created_at timestamptz DEFAULT now());")
        out, _ = _run(tmp_path, self.ENTITY, extra={"products/p/backend/migrations/001_a.sql": prior})
        assert out == []

    def test_event_table_referencing_the_entity_passes_whatever_its_stem(self, tmp_path):
        sql = self.ENTITY + ("\nCREATE TABLE p.agenda_historico (id uuid PRIMARY KEY, v uuid REFERENCES p.visitas(id), "
                             "criado_por uuid, created_at timestamptz DEFAULT now());")
        out, _ = _run(tmp_path, sql)
        assert out == []

    def test_audit_trigger_on_the_table_passes(self, tmp_path):
        sql = self.ENTITY + "\nCREATE TRIGGER visitas_audit AFTER UPDATE ON p.visitas FOR EACH ROW EXECUTE FUNCTION p.audit_row();"
        out, _ = _run(tmp_path, sql)
        assert out == []

    def test_added_status_column_on_existing_table_is_caught(self, tmp_path):
        out, _ = _run(tmp_path, "ALTER TABLE p.visitas ADD COLUMN etapa text NOT NULL DEFAULT 'a' CHECK (etapa IN ('a','b'));")
        assert _rules(out) == ["lifecycle_no_events"]

    def test_run_and_metric_tables_are_self_recording(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.sync_runs (id uuid PRIMARY KEY, started_at timestamptz DEFAULT now(), "
                                "status text CHECK (status IN ('ok','erro')));")
        assert out == []

    def test_event_tables_themselves_are_not_asked_for_events(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.pedido_eventos (id uuid PRIMARY KEY, actor_id uuid, status text CHECK (status IN ('a')), "
                                "created_at timestamptz DEFAULT now());")
        assert out == []

    def test_no_status_column_means_no_lifecycle_finding(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.notas (id uuid PRIMARY KEY, texto text, created_at timestamptz DEFAULT now());")
        assert out == []


class TestAdvisories:
    def test_free_text_outcome_warns(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.leads (id uuid PRIMARY KEY, resultado text, created_at timestamptz DEFAULT now());")
        assert [(i["rule"], i["severity"]) for i in out] == [("outcome_free_text", "warning")]

    def test_enum_outcome_is_clean(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.leads (id uuid PRIMARY KEY, resultado text CHECK (resultado IN ('ganho','perdido')), "
                                "created_at timestamptz DEFAULT now());")
        assert out == []

    def test_event_table_without_actor_warns(self, tmp_path):
        out, _ = _run(tmp_path, "CREATE TABLE p.lead_eventos (id uuid PRIMARY KEY, event_type text, created_at timestamptz DEFAULT now());")
        assert [(i["rule"], i["severity"]) for i in out] == [("event_no_actor", "warning")]

    def test_lifecycle_without_updated_at_warns(self, tmp_path):
        sql = ("CREATE TABLE p.visitas (id uuid PRIMARY KEY, created_at timestamptz DEFAULT now(), status text CHECK (status IN ('a','b')));\n"
               "CREATE TABLE p.visitas_eventos (id uuid PRIMARY KEY, v uuid REFERENCES p.visitas(id), actor_id uuid, created_at timestamptz DEFAULT now());")
        out, _ = _run(tmp_path, sql)
        assert [(i["rule"], i["severity"]) for i in out] == [("mutable_no_updated", "warning")]


class TestScopeAndEscape:
    BAD = "CREATE TABLE p.visitas (id uuid PRIMARY KEY, nota text);"

    def test_escape_with_reason_silences_and_is_recorded(self, tmp_path):
        out, esc = _run(tmp_path, "-- measurable[visitas]: derived read-model, rebuilt from visitas_eventos\n" + self.BAD)
        assert out == [] and esc == [{"file": MIG, "table": "p.visitas", "reason": "derived read-model, rebuilt from visitas_eventos"}]

    def test_file_wide_escape(self, tmp_path):
        out, esc = _run(tmp_path, "-- measurable: static reference data loaded once, no lifecycle\n" + self.BAD)
        assert out == [] and len(esc) == 1

    def test_short_reason_is_itself_a_finding(self, tmp_path):
        out, _ = _run(tmp_path, "-- measurable: ok\n" + self.BAD)
        assert "escape_reason_short" in _rules(out) and "missing_created_at" in _rules(out)

    def test_first_migration_is_the_scaffold_baseline_and_exempt(self, tmp_path):
        out, _ = _run(tmp_path, self.BAD, rel="products/p/backend/migrations/001_p.sql")
        assert out == []

    def test_organ_generated_migration_is_exempt(self, tmp_path):
        out, _ = _run(tmp_path, "-- Finance organ -- generated by noctusai_lib.domain.finance.sql (do not hand-edit)\n" + self.BAD)
        assert out == []

    def test_non_migration_paths_are_ignored(self, tmp_path):
        out, _ = _run(tmp_path, self.BAD, rel="products/p/backend/app/x.sql")
        assert out == []

    def test_historical_files_outside_paths_are_never_scanned(self, tmp_path):
        (tmp_path / "products/p/backend/migrations").mkdir(parents=True)
        (tmp_path / "products/p/backend/migrations/009_old.sql").write_text(self.BAD)
        assert check_measurable_by_design(repo_root=tmp_path, paths=[]) == []


class TestConstructionRoundTrip:
    def test_scaffold_with_table_and_eventos_passes_the_gate_it_serves(self, tmp_path):
        products = tmp_path / "products"
        mig = products / "demo" / "backend" / "migrations"
        mig.mkdir(parents=True)
        (mig / "001_seed.sql").write_text("-- placeholder\n")
        # the scaffolded table has no lifecycle column; add one the way an engineer would, then require the events
        res = sm.scaffold_migration("demo", "visitas", with_table="visitas", with_eventos=True,
                                    products_dir=products, skip_fetch=True)
        assert res.get("created"), res
        sql = Path(res["path"]).read_text()
        assert "visitas_eventos" in sql and "actor_id" in sql and "append-only" in sql
        sql += "\nALTER TABLE demo.visitas ADD COLUMN status text NOT NULL DEFAULT 'agendada' CHECK (status IN ('agendada','realizada'));\n"
        Path(res["path"]).write_text(sql)
        rel = f"products/demo/backend/migrations/{Path(res['path']).name}"
        out = check_measurable_by_design(repo_root=tmp_path, paths=[rel])
        assert [i for i in out if i["severity"] != "warning"] == [], out

    def test_with_eventos_requires_with_table(self, tmp_path):
        products = tmp_path / "products"
        (products / "demo" / "backend" / "migrations").mkdir(parents=True)
        (products / "demo" / "backend" / "migrations" / "001_a.sql").write_text("--\n")
        res = sm.scaffold_migration("demo", "x", with_eventos=True, products_dir=products, skip_fetch=True)
        assert "with_eventos requires with_table" in res["error"]
