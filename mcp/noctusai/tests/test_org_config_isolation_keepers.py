"""``check_new_org_table_rls`` (blocking delta gate) + ``check_org_owned_definition_not_instanciavel``: org/app
configuration never reaches another org by default. Hermetic (tmp_path). KB § PATTERNS/compliance/org-config-isolation.md."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_new_org_table_rls, check_org_owned_definition_not_instanciavel

MIG = "products/p/backend/migrations/001_x.sql"


def _w(root: Path, rel: str, content: str) -> str:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return rel


def _run(tmp_path: Path, sql: str) -> list[dict]:
    _w(tmp_path, MIG, sql)
    return check_new_org_table_rls(repo_root=tmp_path, paths=[MIG])


class TestNewOrgTableRls:
    def test_org_table_without_rls_is_blocked(self, tmp_path):
        out = _run(tmp_path, "CREATE TABLE p.settings (id uuid PRIMARY KEY, org_id uuid NOT NULL, v text);")
        assert len(out) == 1 and "no `ENABLE ROW LEVEL SECURITY`" in out[0]["issue"]


    def test_rls_without_policy_or_revoke_is_blocked(self, tmp_path):
        out = _run(tmp_path, "CREATE TABLE p.settings (org_id uuid);\nALTER TABLE p.settings ENABLE ROW LEVEL SECURITY;")
        assert len(out) == 1 and "neither an org-scoped SELECT policy" in out[0]["issue"]


    def test_rls_plus_org_scoped_select_policy_passes(self, tmp_path):
        sql = ("CREATE TABLE p.settings (org_id uuid);\nALTER TABLE p.settings ENABLE ROW LEVEL SECURITY;\n"
               "CREATE POLICY s_sel ON p.settings FOR SELECT TO authenticated USING (org_id = p.current_org_id());")
        assert _run(tmp_path, sql) == []


    def test_write_only_policy_does_not_count_as_read_scope(self, tmp_path):
        sql = ("CREATE TABLE p.settings (org_id uuid);\nALTER TABLE p.settings ENABLE ROW LEVEL SECURITY;\n"
               "CREATE POLICY s_ins ON p.settings FOR INSERT TO authenticated WITH CHECK (org_id = p.current_org_id());")
        assert len(_run(tmp_path, sql)) == 1


    def test_service_role_only_posture_passes(self, tmp_path):
        sql = ("CREATE TABLE p.grants (org_id uuid);\nALTER TABLE p.grants ENABLE ROW LEVEL SECURITY;\n"
               "REVOKE ALL ON p.grants FROM PUBLIC, anon, authenticated;")
        assert _run(tmp_path, sql) == []


    def test_table_without_org_column_is_out_of_scope(self, tmp_path):
        assert _run(tmp_path, "CREATE TABLE p.catalog (id uuid PRIMARY KEY, nome text);") == []


    def test_dynamic_rls_block_counts(self, tmp_path):
        sql = ("CREATE TABLE p.a (org_id uuid);\nDO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['a'] LOOP "
               "EXECUTE format('ALTER TABLE p.%I ENABLE ROW LEVEL SECURITY', t); "
               "EXECUTE format('CREATE POLICY %I ON p.%I FOR SELECT USING (org_id = p.current_org_id())', t || '_sel', t); "
               "END LOOP; END $$;")
        assert _run(tmp_path, sql) == []


    def test_reviewed_escape_marker(self, tmp_path):
        sql = "-- noc-allow: org-table-rls — platform-wide reference\nCREATE TABLE p.x (org_id uuid);"
        assert _run(tmp_path, sql) == []


    def test_delta_only_existing_files_not_in_paths_are_ignored(self, tmp_path):
        _w(tmp_path, MIG, "CREATE TABLE p.old (org_id uuid);")
        assert check_new_org_table_rls(repo_root=tmp_path, paths=[]) == []


    def test_real_050_migration_passes(self):
        repo = Path(__file__).resolve().parents[3]
        rel = "products/agents/backend/migrations/050_definition_org_grants.sql"
        assert check_new_org_table_rls(repo_root=repo, paths=[rel]) == []


# ── owned definition never instanciavel ────────────────────────────────────


def _defs(tmp_path: Path, rel: str, body: str) -> list[dict]:
    _w(tmp_path, rel, body)
    return check_org_owned_definition_not_instanciavel(repo_root=tmp_path)


class TestOrgOwnedDefinitionNotInstanciavel:

    def test_owned_and_open_json_is_flagged(self, tmp_path):
        out = _defs(tmp_path, "products/m/ops/agents/a.json", json.dumps({"owner_product": "monica", "instanciavel": True}))
        assert len(out) == 1 and "EVERY org" in out[0]["issue"]


    def test_owned_and_closed_passes(self, tmp_path):
        assert _defs(tmp_path, "products/m/ops/agents/a.json", json.dumps({"owner_product": "m", "instanciavel": False})) == []


    def test_open_without_owner_passes(self, tmp_path):
        assert _defs(tmp_path, "products/m/ops/agents/a.json", json.dumps({"instanciavel": True})) == []


    def test_package_yaml_nested_is_flagged(self, tmp_path):
        out = _defs(tmp_path, "products/agents/packages/k/package.yaml", "agent:\n  owner_product: sw\n  instanciavel: true\n")
        assert len(out) == 1


    def test_unparseable_declaration_is_reported_not_skipped(self, tmp_path):
        assert len(_defs(tmp_path, "products/m/ops/agents/a.json", "{nope")) == 1


    def test_real_tree_is_clean(self):
        assert check_org_owned_definition_not_instanciavel(repo_root=Path(__file__).resolve().parents[3]) == []
