"""Regression tests for `check_org_picker_ready_policies`: a product whose chain last
sets products.org_picker_ready=true must carry no home-only policy (latest definition)."""
from __future__ import annotations

from pathlib import Path

from tools.noctus.dev.compliance import check_org_picker_ready_policies

READY = "UPDATE public.products SET org_picker_ready = true WHERE slug = 'demo';\n"
UNREADY = "UPDATE public.products SET org_picker_ready = false WHERE slug = 'demo';\n"
HOME_POLICY = (
    "CREATE POLICY leads_org ON demo.leads FOR ALL TO authenticated\n"
    "  USING (org_id = (SELECT public.current_org_id())) WITH CHECK (org_id = (SELECT public.current_org_id()));\n"
)
PICKER_POLICY = (
    "CREATE POLICY leads_org ON demo.leads FOR ALL TO authenticated\n"
    "  USING (org_id = (SELECT public.current_org_id_for('demo')));\n"
)


ATTACH = "SELECT public.attach_acting_audit_triggers('demo');\n"


def _chain(tmp_path: Path, attach: bool = True, **files: str) -> Path:
    """`attach` adds the acting-audit call so tests about OTHER rules stay single-issue."""
    d = tmp_path / "products" / "demo" / "backend" / "migrations"
    d.mkdir(parents=True)
    if attach:
        files = {**files, "999_acting_audit.sql": ATTACH}
    for name, sql in files.items():
        (d / name).write_text(sql, encoding="utf-8")
    return tmp_path


class TestOrgPickerReadyPolicies:
    def test_ready_with_a_home_only_policy_is_flagged(self, tmp_path):
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_ready.sql": READY})
        issues = check_org_picker_ready_policies(root)
        assert len(issues) == 1
        assert issues[0]["product"] == "demo" and "demo.leads::leads_org" in issues[0]["issue"]
        assert issues[0]["severity"] == "critical"


    def test_converted_policy_passes(self, tmp_path):
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_conv.sql": "DROP POLICY leads_org ON demo.leads;\n" + PICKER_POLICY,
                                   "003_ready.sql": READY, "004_audit.sql": ATTACH})
        assert check_org_picker_ready_policies(root) == []


    def test_alter_policy_to_the_picker_helper_passes(self, tmp_path):
        alter = "ALTER POLICY leads_org ON demo.leads USING (org_id = (SELECT public.current_org_id_for('demo')));\n"
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_alter.sql": alter, "003_ready.sql": READY, "004_audit.sql": ATTACH})
        assert check_org_picker_ready_policies(root) == []


    def test_inline_noctus_users_subquery_counts_as_home_only(self, tmp_path):
        inline = ("CREATE POLICY p ON demo.t USING (org_id IN (SELECT org_id FROM public.noctus_users "
                  "WHERE id = (SELECT auth.uid())));\n")
        root = _chain(tmp_path, **{"001_a.sql": inline, "002_ready.sql": READY})
        assert len(check_org_picker_ready_policies(root)) == 1


    def test_a_later_unready_flag_means_nothing_to_judge(self, tmp_path):
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_ready.sql": READY, "003_off.sql": UNREADY})
        assert check_org_picker_ready_policies(root) == []


    def test_never_ready_products_are_not_judged(self, tmp_path):
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY})
        assert check_org_picker_ready_policies(root) == []


    def test_dropped_table_drops_its_policies(self, tmp_path):
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_drop.sql": "DROP TABLE IF EXISTS demo.leads;\n",
                                   "003_ready.sql": READY, "004_audit.sql": ATTACH})
        assert check_org_picker_ready_policies(root) == []


    def test_comments_and_prose_are_not_statements(self, tmp_path):
        prose = "-- CREATE POLICY x ON demo.t USING (org_id = public.current_org_id());\n" + PICKER_POLICY
        root = _chain(tmp_path, **{"001_a.sql": prose, "002_ready.sql": READY, "003_audit.sql": ATTACH})
        assert check_org_picker_ready_policies(root) == []


    def test_ready_without_acting_audit_attach_is_flagged(self, tmp_path):
        root = _chain(tmp_path, attach=False, **{"001_a.sql": PICKER_POLICY, "002_ready.sql": READY})
        issues = check_org_picker_ready_policies(root)
        assert len(issues) == 1 and "attach_acting_audit_triggers" in issues[0]["issue"]
        assert issues[0]["severity"] == "critical"

    def test_attach_after_the_ready_flip_satisfies_it(self, tmp_path):
        root = _chain(tmp_path, attach=False, **{"001_a.sql": PICKER_POLICY, "002_ready.sql": READY, "003_audit.sql": ATTACH})
        assert check_org_picker_ready_policies(root) == []

    def test_attach_only_in_a_comment_does_not_count(self, tmp_path):
        root = _chain(tmp_path, attach=False, **{"001_a.sql": PICKER_POLICY, "002_ready.sql": READY,
                                   "003_x.sql": "-- SELECT public.attach_acting_audit_triggers('demo');\n"})
        assert len(check_org_picker_ready_policies(root)) == 1

    def test_allowlisted_role_check_needs_its_org_predicate_converted(self, tmp_path):
        role = ("EXISTS (SELECT 1 FROM public.noctus_users nu WHERE nu.id = auth.uid() "
                "AND nu.org_role = ANY (ARRAY['owner','admin']))")
        home = (f"CREATE POLICY api_tokens_insert_own_org_admin ON agents.api_tokens FOR INSERT\n"
                f"  WITH CHECK (org_id = (SELECT public.current_org_id()) AND {role});\n")
        root = _chain(tmp_path, **{"001_a.sql": home, "002_ready.sql": READY})
        issues = check_org_picker_ready_policies(root)
        assert len(issues) == 1 and "allowlisted for its home-keyed ROLE check" in issues[0]["issue"]
        converted = home.replace("public.current_org_id()", "public.current_org_id_for('agents')")
        root2 = _chain(tmp_path / "b", **{"001_a.sql": converted, "002_ready.sql": READY})
        assert check_org_picker_ready_policies(root2) == []

    def test_ready_flip_keyed_on_db_schema_is_judged(self, tmp_path):
        """The seed chain (template for every product) flips by db_schema, not slug."""
        by_schema = "UPDATE public.products SET org_picker_ready = true WHERE db_schema = 'demo';\n"
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_ready.sql": by_schema})
        issues = check_org_picker_ready_policies(root)
        assert len(issues) == 1 and "HOME-ONLY" in issues[0]["issue"]

    def test_unready_product_needs_no_attach(self, tmp_path):
        root = _chain(tmp_path, **{"001_a.sql": PICKER_POLICY})
        assert check_org_picker_ready_policies(root) == []

    def test_live_tree_is_clean(self):
        assert check_org_picker_ready_policies() == []


class TestOrgPickerReadyExemptions:
    def test_storage_objects_is_home_only_by_design(self, tmp_path):
        sql = ("CREATE POLICY b_sel ON storage.objects FOR SELECT TO authenticated\n"
               "  USING ((storage.foldername(name))[1] = (current_org_id())::text);\n")
        root = _chain(tmp_path, **{"001_a.sql": sql, "002_ready.sql": READY})
        assert check_org_picker_ready_policies(root) == []

    def test_literal_table_rename_inside_do_guard_is_followed(self, tmp_path):
        rename = "DO $$ BEGIN ALTER TABLE demo.leads RENAME TO prospects; END $$;\n"
        converted = ("ALTER POLICY leads_org ON demo.prospects\n"
                     "  USING (org_id = (SELECT public.current_org_id_for('demo')));\n")
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_r.sql": rename,
                                   "003_c.sql": converted, "004_ready.sql": READY})
        assert check_org_picker_ready_policies(root) == []

    def test_renamed_table_unconverted_policy_still_flagged(self, tmp_path):
        rename = "ALTER TABLE demo.leads RENAME TO prospects;\n"
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_r.sql": rename, "003_ready.sql": READY})
        issues = check_org_picker_ready_policies(root)
        assert len(issues) == 1 and "demo.prospects::leads_org" in issues[0]["issue"]

    def test_policy_rename_is_followed(self, tmp_path):
        ren = "ALTER POLICY leads_org ON demo.leads RENAME TO leads_new;\n"
        root = _chain(tmp_path, **{"001_a.sql": HOME_POLICY, "002_r.sql": ren, "003_ready.sql": READY})
        issues = check_org_picker_ready_policies(root)
        assert len(issues) == 1 and "demo.leads::leads_new" in issues[0]["issue"]

    def test_allowlist_entries_are_exact_and_justified(self):
        from tools.noctus.dev.compliance import _OPR_ALLOWED_HOME_ONLY
        # social-wiring 5 + the seed-shipped api_tokens pair in agents and academia (2026-10-09)
        assert len(_OPR_ALLOWED_HOME_ONLY) == 9
        assert all("::" in k and "*" not in k and v for k, v in _OPR_ALLOWED_HOME_ONLY.items())
