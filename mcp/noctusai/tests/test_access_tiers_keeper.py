"""Red + green fixtures for the access-tier keepers (`check_access_tier_routes`, `check_access_tier_tables`).

Each test builds a tiny repo (the REAL registry copied in), so both verdicts are proven against the real
dependency map -- never a patched guard. KB § PATTERNS/security/access-tiers.md."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.noctus.dev import access_tiers as at
from tools.noctus.dev import findings_ledger as gl
from tools.noctus.dev.compliance import check_access_tier_routes, check_access_tier_tables

REPO = Path(__file__).resolve().parents[3]

_DEPS = '''
from fastapi import Depends
def get_auth_context(): ...
require_member = require_scopes(user_roles=frozenset({"member"}), get_auth_context=get_auth_context, restrict="user_only")
require_platform_admin = _require_platform_admin(get_auth_context=get_auth_context)
async def require_platform_content_admin(ctx=Depends(get_auth_context)):
    return await require_platform_admin(ctx=ctx)
'''


def _tree(tmp_path: Path, router_src: str, migrations: dict[str, str] | None = None, live_keys: list[str] | None = None) -> Path:
    reg = tmp_path / at.REGISTRY_REL
    reg.parent.mkdir(parents=True)
    shutil.copy(REPO / at.REGISTRY_REL, reg)
    (tmp_path / "deploy/fleet").mkdir(parents=True)
    (tmp_path / "deploy/fleet/active-scope.txt").write_text("agents\n", encoding="utf-8")
    app = tmp_path / "products/agents/backend/app"
    (app / "routers").mkdir(parents=True)
    (app / "dependencies.py").write_text(_DEPS, encoding="utf-8")
    (app / "routers/r.py").write_text(router_src, encoding="utf-8")
    mig = tmp_path / "products/agents/backend/migrations"
    mig.mkdir(parents=True)
    for name, sql in (migrations or {}).items():
        (mig / name).write_text(sql, encoding="utf-8")
    for k in live_keys or []:  # rows the ledger already knows (the ratchet)
        gl.append("access-tier", tmp_path, scope="agents", target=k, found_by="test", key=k)
    return tmp_path


_HEAD = "from fastapi import APIRouter, Depends\nfrom app.dependencies import *\nfrom noctusai_lib.api.access_tiers import access_tier\nrouter = APIRouter(prefix='/api/studio')\n"


class TestAccessTierRoutes:
    def test_platform_ip_behind_member_is_too_open(self, tmp_path):
        src = _HEAD + "@router.get('/agents/{k}/evals/runs')\ndef runs(ctx=Depends(require_member)): ...\n"
        issues = check_access_tier_routes(_tree(tmp_path, src))
        assert len(issues) == 1 and "too-open" in issues[0]["issue"]

    def test_platform_ip_behind_platform_admin_is_clean(self, tmp_path):
        src = _HEAD + "@router.get('/agents/{k}/evals/runs')\ndef runs(ctx=Depends(require_platform_content_admin)): ...\n"
        assert check_access_tier_routes(_tree(tmp_path, src)) == []

    def test_undeclared_route_is_refused(self, tmp_path):
        src = _HEAD + "@router.post('/hook')\ndef hook(): ...\n"
        issues = check_access_tier_routes(_tree(tmp_path, src))
        assert len(issues) == 1 and "unclear" in issues[0]["issue"]

    def test_declared_public_in_allowlist_and_health_are_clean(self, tmp_path):
        src = _HEAD + (
            "@router.get('/pricing')\n@limiter.limit('10/minute')\n@access_tier('public', reason='pricing page', category='pricing-checkout')\ndef pricing(): ...\n"
            "@router.get('/health')\ndef health(): ...\n")
        assert check_access_tier_routes(_tree(tmp_path, src)) == []

    def test_public_outside_the_allowlist_is_refused(self, tmp_path):
        src = _HEAD + "@router.get('/leads')\n@limiter.limit('10/minute')\n@access_tier('public', reason='x', category='misc')\ndef leads(): ...\n"
        issues = check_access_tier_routes(_tree(tmp_path, src))
        assert len(issues) == 1 and "closed allowlist" in issues[0]["issue"]

    def test_public_without_rate_limit_is_refused(self, tmp_path):
        src = _HEAD + "@router.get('/pricing')\n@access_tier('public', reason='x', category='pricing-checkout')\ndef pricing(): ...\n"
        assert "rate limit" in check_access_tier_routes(_tree(tmp_path, src))[0]["issue"]

    def test_public_write_needs_abuse_protection(self, tmp_path):
        bad = _HEAD + "@router.post('/lead')\n@limiter.limit('5/minute')\n@access_tier('public', reason='x', category='lead-capture')\ndef lead(): ...\n"
        assert "abuse protection" in check_access_tier_routes(_tree(tmp_path, bad))[0]["issue"]
        good = bad.replace("def lead(): ...", "def lead():\n    verify_turnstile()")
        assert check_access_tier_routes(_tree(tmp_path / "g", good)) == []

    def test_signed_webhook_is_service_not_public(self, tmp_path):
        src = _HEAD + "@router.post('/hook')\ndef hook():\n    verify_hmac_sha256(b'', '', '')\n"
        assert check_access_tier_routes(_tree(tmp_path, src)) == []
        routes = at.classify_routes(tmp_path)
        assert routes[0].tier == "service" and routes[0].category == "signed:webhook"

    def test_oauth_callback_must_verify_state(self, tmp_path):
        bad = _HEAD + "@router.get('/oauth/callback')\ndef cb(code: str): ...\n"
        assert "state" in check_access_tier_routes(_tree(tmp_path, bad))[0]["issue"]
        good = bad.replace("def cb(code: str): ...", "def cb(code: str):\n    verify_state(code, binding=cookie)")
        assert check_access_tier_routes(_tree(tmp_path / "g", good)) == []

    def test_oauth_callback_state_must_be_bound_to_the_browser(self, tmp_path):
        # verifying that "this server issued the state" is not enough: it does not stop login-CSRF / account-linking
        unbound = _HEAD + "@router.get('/oauth/callback')\ndef cb(code: str):\n    consume_state(code)\n"
        issues = check_access_tier_routes(_tree(tmp_path, unbound))
        assert len(issues) == 1 and "does not bind it to the browser" in issues[0]["issue"]
        # the keyword must be on the STATE call itself, not merely present somewhere in the handler
        elsewhere = _HEAD + "@router.get('/oauth/callback')\ndef cb(code: str):\n    binding = 1\n    consume_state(code)\n"
        assert "does not bind" in check_access_tier_routes(_tree(tmp_path / "e", elsewhere))[0]["issue"]
        bound = _HEAD + "@router.get('/oauth/callback')\ndef cb(code: str):\n    consume_state(code, binding=cookie)\n"
        assert check_access_tier_routes(_tree(tmp_path / "b", bound)) == []

    def test_org_route_off_platform_path_is_clean(self, tmp_path):
        src = _HEAD + "@router.get('/modelo')\ndef modelo(ctx=Depends(require_member)): ...\n"
        assert check_access_tier_routes(_tree(tmp_path, src)) == []

    def test_baseline_silences_known_and_blocks_new(self, tmp_path):
        src = _HEAD + "@router.post('/hook')\ndef hook(): ...\n@router.post('/hook2')\ndef hook2(): ...\n"
        key = "agents|POST /api/studio/hook|hook"
        issues = check_access_tier_routes(_tree(tmp_path, src, live_keys=[key]))
        assert [i["issue"].split(":")[0] for i in issues] == ["[unclear] agents|POST /api/studio/hook2|hook2"]

    def test_public_marker_requires_reason(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("reg", REPO / at.REGISTRY_REL)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        try:
            mod.access_tier("public", category="landing")
        except ValueError:
            pass
        else:
            raise AssertionError("a public marker without a reason must be refused")
        try:
            mod.access_tier("public", reason="x", category="misc")
        except ValueError:
            return
        raise AssertionError("a public marker without a reason must be refused")


_BASE = "CREATE SCHEMA IF NOT EXISTS agents;\nCREATE TABLE agents.compiled_prompts (id int, org_id uuid);\n"


class TestAccessTierTables:
    def test_default_privileges_grant_exposes_platform_table(self, tmp_path):
        sql = ("GRANT ALL ON ALL TABLES IN SCHEMA agents TO authenticated, service_role;\n" + _BASE)
        # the grant precedes the table: only ALTER DEFAULT PRIVILEGES reaches it
        sql = ("ALTER DEFAULT PRIVILEGES IN SCHEMA agents GRANT ALL ON TABLES TO authenticated;\n" + _BASE)
        issues = check_access_tier_tables(_tree(tmp_path, "", {"001.sql": sql}))
        assert any("grant" in i["file"] for i in issues)

    def test_weak_policy_flagged_and_admin_policy_clean(self, tmp_path):
        weak = _BASE + ("CREATE POLICY p ON agents.compiled_prompts FOR SELECT TO authenticated "
                        "USING (org_id = current_org_id());\n")
        assert any("policy" in i["file"] for i in check_access_tier_tables(_tree(tmp_path, "", {"001.sql": weak})))

    def test_admin_policy_is_clean(self, tmp_path):
        ok = _BASE + ("CREATE POLICY p ON agents.compiled_prompts FOR SELECT TO authenticated "
                      "USING (EXISTS (SELECT 1 FROM public.noctus_users u WHERE u.id = auth.uid() AND u.role = 'admin'));\n")
        assert check_access_tier_tables(_tree(tmp_path, "", {"001.sql": ok})) == []

    def test_revoke_later_in_chain_clears_it(self, tmp_path):
        sql1 = "ALTER DEFAULT PRIVILEGES IN SCHEMA agents GRANT ALL ON TABLES TO authenticated;\n" + _BASE
        sql2 = "REVOKE ALL ON agents.compiled_prompts FROM authenticated;\n"
        assert check_access_tier_tables(_tree(tmp_path, "", {"001.sql": sql1, "002.sql": sql2})) == []

    def test_public_table_with_no_grant_statement_inherits_supabase_default_grants(self, tmp_path):
        """085_finance shape: CREATE TABLE public.x with no GRANT/REVOKE inherits anon+authenticated ALL."""
        root = _tree(tmp_path, "", {"001.sql": "CREATE TABLE IF NOT EXISTS public.fin_accounts (id int, org_id uuid);\n"})
        keys = {f["key"] for f in at.analyze_tables(root)["grant_findings"]}
        assert {"grant:public.fin_accounts:anon", "grant:public.fin_accounts:authenticated"} <= keys

    def test_later_forward_revoke_closes_inherited_public_grants(self, tmp_path):
        sql1 = "CREATE TABLE public.fin_accounts (id int);\n"
        sql2 = "REVOKE ALL ON public.fin_accounts FROM anon, authenticated;\n"
        root = _tree(tmp_path, "", {"001.sql": sql1, "002.sql": sql2})
        assert at.analyze_tables(root)["grant_findings"] == []

    def test_explicit_revoke_in_same_migration_is_clean(self, tmp_path):
        sql = "CREATE TABLE public.fin_x (id int);\nREVOKE ALL ON public.fin_x FROM anon, authenticated;\n"
        assert at.analyze_tables(_tree(tmp_path, "", {"001.sql": sql}))["grant_findings"] == []

    def test_tier_comment_makes_any_table_platform(self, tmp_path):
        sql = ("CREATE TABLE agents.secret_rubrics (id int);\nCOMMENT ON TABLE agents.secret_rubrics IS 'tier:platform';\n"
               "GRANT SELECT ON agents.secret_rubrics TO authenticated;\n")
        assert len(check_access_tier_tables(_tree(tmp_path, "", {"001.sql": sql}))) == 1

    def test_new_table_without_tier_is_refused(self, tmp_path):
        root = _tree(tmp_path, "", {"090_new.sql": "CREATE TABLE agents.widgets (id int);\n"})
        rel = "products/agents/backend/migrations/090_new.sql"
        assert len(check_access_tier_tables(root, paths=[rel])) == 2  # no tier AND no explicit grants

    def test_new_table_with_tier_comment_is_clean(self, tmp_path):
        sql = "CREATE TABLE agents.widgets (id int);\nCOMMENT ON TABLE agents.widgets IS 'tier:org';\nREVOKE ALL ON agents.widgets FROM anon;\n"
        root = _tree(tmp_path, "", {"090_new.sql": sql})
        assert check_access_tier_tables(root, paths=["products/agents/backend/migrations/090_new.sql"]) == []


from tools.noctus.dev.compliance import (  # noqa: E402
    check_access_tier_fingerprint, check_access_tier_ledger, check_access_tier_streams, check_findings_ledger_visibility,
    check_findings_ledgers)

_PUB = "async def publish_event(*a, **k): ...\n"


class TestAccessTierStreams:
    def test_unfiltered_delta_publish_flagged(self, tmp_path):
        root = _tree(tmp_path, _PUB + "async def run(bus):\n    await publish_event('c', 'message.delta', {}, bus=bus)\n")
        assert len(check_access_tier_streams(root)) == 1

    def test_filtered_delta_publish_clean(self, tmp_path):
        src = _PUB + ("async def run(bus, guarda):\n    filtro = FiltroDeltas(guarda)\n"
                      "    await publish_event('c', 'message.delta', filtro(1), bus=bus)\n")
        assert check_access_tier_streams(_tree(tmp_path, src)) == []

    def test_other_events_not_flagged(self, tmp_path):
        root = _tree(tmp_path, _PUB + "async def run(bus):\n    await publish_event('c', 'message.new', {}, bus=bus)\n")
        assert check_access_tier_streams(root) == []


_SEAM = "products/agents/backend/app/channels/conformidade.py"
_TREG = "products/agents/backend/app/channels/tool_registry.py"
_FULL = ("    c = compiled.conteudo\n    return [compiled.texto, c.textos, c.ferramentas, c.decisoes, c.skills, c.skill_files]")


def _fp_tree(tmp_path, seam_body, tools):
    root = _tree(tmp_path, "")
    (root / _SEAM).parent.mkdir(parents=True, exist_ok=True)
    (root / _SEAM).write_text(f"def texto_fonte_do_prompt(compiled):\n{seam_body}\n", encoding="utf-8")
    (root / _TREG).write_text("TOOLS = (" + ", ".join(f"ToolDef('{t}', X)" for t in tools) + ")\n", encoding="utf-8")
    return root


class TestAccessTierFingerprint:
    def test_missing_source_flagged(self, tmp_path):
        body = "    c = compiled.conteudo\n    return [compiled.texto, c.textos, c.ferramentas, c.decisoes]"
        keys = [i["issue"] for i in check_access_tier_fingerprint(_fp_tree(tmp_path, body, ["handoff"]))]
        assert len(keys) == 2 and all("skill" in k for k in keys)

    def test_full_coverage_clean(self, tmp_path):
        assert check_access_tier_fingerprint(_fp_tree(tmp_path, _FULL, ["abrir_skill", "handoff"])) == []

    def test_unclassified_tool_refused(self, tmp_path):
        issues = check_access_tier_fingerprint(_fp_tree(tmp_path, _FULL, ["abrir_skill", "brand_new_tool"]))
        assert len(issues) == 1 and "brand_new_tool" in issues[0]["issue"]

    def test_missing_seam_is_unmeasurable_not_green(self, tmp_path):
        assert len(check_access_tier_fingerprint(_tree(tmp_path, ""))) == 1


class TestExposure:
    def test_effective_grant_on_platform_table_is_drift(self, tmp_path):
        root = _tree(tmp_path, "", {"001.sql": _BASE})
        out = at.diff_exposure({"grants": [{"table_schema": "agents", "table_name": "compiled_prompts",
                                            "grantee": "authenticated", "privilege_type": "SELECT"}],
                                "policies": [], "db_schemas": "public,agents", "columns": []}, root)
        assert not out["ok"] and out["findings"][0]["kind"] == "grant"

    def test_clean_effective_state_is_ok(self, tmp_path):
        root = _tree(tmp_path, "", {"001.sql": _BASE})
        assert at.diff_exposure({"grants": [], "policies": [], "db_schemas": "public", "columns": []}, root)["ok"]

    def test_unmeasured_input_is_never_green(self, tmp_path):
        root = _tree(tmp_path, "", {"001.sql": _BASE})
        out = at.diff_exposure({"grants": []}, root)
        assert not out["ok"] and set(out["unmeasured"]) == {"policies", "db_schemas", "columns"}


class TestExposureClasses:
    def test_anon_policy_on_secret_column_table_is_critical(self, tmp_path):
        out = at.diff_exposure({"grants": [], "db_schemas": "public", "columns": [
            {"table_schema": "erp", "table_name": "portal_tokens", "column_name": "token"}],
            "policies": [{"schemaname": "erp", "tablename": "portal_tokens", "policyname": "p", "roles": "{anon}",
                          "cmd": "SELECT", "qual": "(is_active AND expires_at > now())"}]}, _tree(tmp_path, "", {"001.sql": _BASE}))
        assert out["findings"][0]["kind"] == "policy-secret" and out["findings"][0]["severity"] == "critical"

    def test_public_qual_true_with_anon_grant(self, tmp_path):
        out = at.diff_exposure({"db_schemas": "public", "columns": [],
            "grants": [{"table_schema": "erp", "table_name": "metas", "grantee": "anon", "privilege_type": "SELECT"}],
            "policies": [{"schemaname": "erp", "tablename": "metas", "policyname": "p", "roles": "{public}", "cmd": "SELECT", "qual": "true"}]},
            _tree(tmp_path, "", {"001.sql": _BASE}))
        assert any(f["kind"] == "policy-open" for f in out["findings"])

    def test_inactive_product_schema_served(self, tmp_path):
        root = _tree(tmp_path, "", {"001.sql": _BASE})
        d = root / "products/erp-imobiliario/backend/migrations"
        d.mkdir(parents=True)
        (d / "001.sql").write_text("CREATE SCHEMA IF NOT EXISTS erp;\n", encoding="utf-8")
        out = at.diff_exposure({"grants": [], "policies": [], "columns": [], "db_schemas": "public,erp"}, root)
        assert any(f["kind"] == "inactive-schema-served" for f in out["findings"])


class TestStaticTableClasses:
    def test_static_secret_policy_and_open_true(self, tmp_path):
        sql = ("CREATE TABLE erp.portal_tokens (id int, token text, is_active bool);\n"
               "GRANT SELECT ON erp.portal_tokens TO anon;\n"
               "CREATE POLICY portal_tokens_anon_read ON erp.portal_tokens FOR SELECT TO anon USING (is_active);\n"
               "CREATE TABLE erp.metas (id int);\nGRANT SELECT ON erp.metas TO anon;\n"
               "CREATE POLICY corretor_read ON erp.metas FOR SELECT USING (true);\n")
        kinds = {f["kind"] for f in at.analyze_tables(_tree(tmp_path, "", {"001.sql": sql}))["findings"]}
        assert {"policy-secret", "policy-open"} <= kinds

    def test_org_scoped_token_table_policy_is_not_flagged(self, tmp_path):
        sql = ("CREATE TABLE a.keys (id int, api_key text, org_id uuid);\n"
               "CREATE POLICY k ON a.keys FOR SELECT TO authenticated USING (org_id = current_org_id());\n")
        assert at.analyze_tables(_tree(tmp_path, "", {"001.sql": sql}))["findings"] == []

    def test_do_block_lockdown_is_replayed(self, tmp_path):
        sql = ("ALTER DEFAULT PRIVILEGES IN SCHEMA agents GRANT ALL ON TABLES TO authenticated;\n" + _BASE +
               "DO $r$ DECLARE t text; v_tables text[] := ARRAY['compiled_prompts'];\nBEGIN FOREACH t IN ARRAY v_tables LOOP\n"
               "EXECUTE format('REVOKE ALL ON agents.%I FROM PUBLIC, anon, authenticated', t); END LOOP; END $r$;\n")
        assert at.analyze_tables(_tree(tmp_path, "", {"001.sql": sql}))["findings"] == []


class TestNewTableGrants:
    def test_new_table_inheriting_default_privileges_refused(self, tmp_path):
        sql = "CREATE TABLE agents.widgets (id int);\nCOMMENT ON TABLE agents.widgets IS 'tier:org';\n"
        issues = check_access_tier_tables(_tree(tmp_path, "", {"090.sql": sql}), paths=["products/agents/backend/migrations/090.sql"])
        assert len(issues) == 1 and "default privileges" in issues[0]["issue"]

    def test_explicit_revoke_clears_it(self, tmp_path):
        sql = ("CREATE TABLE agents.widgets (id int);\nCOMMENT ON TABLE agents.widgets IS 'tier:org';\n"
               "REVOKE ALL ON agents.widgets FROM anon;\n")
        assert check_access_tier_tables(_tree(tmp_path, "", {"090.sql": sql}), paths=["products/agents/backend/migrations/090.sql"]) == []


class TestRealTree:
    def test_real_tree_is_green_against_its_ledger(self):
        assert check_access_tier_routes(REPO) == []
        assert check_access_tier_tables(REPO) == []
        assert check_access_tier_streams(REPO) == []
        assert check_access_tier_fingerprint(REPO) == []

    def test_every_ledger_agrees_with_reality(self):
        """Status never disagrees with the latest scan (the drift keeper, over all registered ledgers)."""
        assert gl.check_all(REPO) == []


class TestFindingsLedgers:
    def _root(self, tmp_path):
        return _tree(tmp_path, _HEAD + "@router.post('/hook')\ndef hook(): ...\n")

    def test_reconcile_opens_then_closes_when_fixed(self, tmp_path):
        root = self._root(tmp_path)
        assert gl.reconcile("access-tier", root)["added"] == 2   # the undeclared route + the (unmeasurable) fingerprint seam
        assert gl.check("access-tier", root) == []
        (root / "products/agents/backend/app/routers/r.py").write_text(
            _HEAD + "@router.post('/hook')\ndef hook(ctx=Depends(require_member)): ...\n", encoding="utf-8")
        assert any("no longer sees" in i["issue"] for i in gl.check("access-tier", root))
        assert gl.reconcile("access-tier", root)["closed"] == 1
        assert gl.check("access-tier", root) == []

    def test_fixed_but_still_seen_fails(self, tmp_path):
        root = self._root(tmp_path)
        gl.reconcile("access-tier", root)
        fid = next(f["id"] for f in gl.query("access-tier", root)["findings"] if f["class"] == "unclear")
        gl.update("access-tier", root, id=fid, status="fixed", detail="abc1234")
        assert any("marked FIXED" in i["issue"] for i in gl.check("access-tier", root))

    def test_new_finding_without_row_fails_the_keeper(self, tmp_path):
        issues = check_access_tier_routes(self._root(tmp_path))
        assert len(issues) == 1

    def test_manual_append_validates_and_needs_detail(self, tmp_path):
        root = self._root(tmp_path)
        assert not gl.append("access-tier", root, scope="erp", target="t", found_by="x", status="accepted")["ok"]
        assert gl.append("access-tier", root, scope="erp", target="t", found_by="x", status="accepted", detail="by design")["ok"]
        assert not gl.append("access-tier", root, scope="erp", target="t", found_by="x", severity="bogus")["ok"]

    def test_a_second_ledger_plugs_in_without_a_fork(self, tmp_path):
        gl.register_ledger(gl.LedgerType(
            name="t-demo", prefix="TD", path="p/demo.ndjson", summary="p/DEMO.md",
            extra={"attribution": ("MODEL", "STRUCTURAL", "CONTENT"), "regression_case_id": None}, sections=("eval",),
            scanner=lambda root: {"c1": {"section": "eval", "scope": "julia", "target": "case 1", "note": "bad",
                                         "attribution": "CONTENT", "regression_case_id": "RC-1"}}))
        try:
            assert gl.reconcile("t-demo", tmp_path)["added"] == 1
            row = gl.query("t-demo", tmp_path)["findings"][0]
            assert row["attribution"] == "CONTENT" and row["regression_case_id"] == "RC-1"
            assert not gl.append("t-demo", tmp_path, scope="julia", target="x", found_by="a", attribution="BOGUS")["ok"]
            assert gl.open_for_scope("julia", tmp_path)
        finally:
            gl._REGISTRY.pop("t-demo", None)


class TestTypedRouter:
    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("reg2", REPO / at.REGISTRY_REL)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    def test_tier_is_a_required_argument(self):
        import pytest
        with pytest.raises(TypeError):
            self._mod().make_router(prefix="/x")

    def test_platform_and_org_need_a_guard_and_public_takes_none(self):
        import pytest
        m = self._mod()
        with pytest.raises(ValueError):
            m.make_router(tier="platform")
        with pytest.raises(ValueError):
            m.make_router(tier="public", reason="r", category="landing", guard=lambda: None)
        r = m.make_router(tier="org", guard=lambda: None, prefix="/x")
        assert r.access_tier == "org" and len(r.dependencies) == 1

    def test_router_declaring_platform_but_gated_only_by_member_is_too_open(self, tmp_path):
        src = ("from fastapi import APIRouter, Depends\nfrom app.dependencies import *\n"
               "router = make_router(tier='platform', guard=require_member, prefix='/api/x')\n"
               "@router.get('/y')\ndef y(ctx=Depends(require_member)): ...\n")
        issues = check_access_tier_routes(_tree(tmp_path, src))
        assert len(issues) == 1 and "only enforce org" in issues[0]["issue"]

    def test_router_declaring_org_with_matching_gate_is_clean(self, tmp_path):
        src = ("from fastapi import Depends\nfrom app.dependencies import *\n"
               "router = make_router(tier='org', guard=require_member, prefix='/api/x')\n"
               "@router.get('/y')\ndef y(): ...\n")
        assert check_access_tier_routes(_tree(tmp_path, src)) == []


class TestAdvisoryAndSarif:
    def test_heuristic_pii_policy_is_recorded_but_never_blocks(self, tmp_path):
        sql = ("CREATE TABLE s.contacts (id int, email text);\nGRANT SELECT ON s.contacts TO anon;\n"
               "CREATE POLICY p ON s.contacts FOR SELECT TO anon USING (is_active);\n")
        root = _tree(tmp_path, "", {"001.sql": sql})
        assert any(f["kind"] == "policy-pii" for f in at.analyze_tables(root)["findings"])
        assert check_access_tier_tables(root) == []                 # warn-only until measured precise
        assert gl.reconcile("access-tier", root)["added"] >= 1       # but tracked
        assert gl.check("access-tier", root) == []

    def test_sarif_export_maps_status_to_baseline_and_suppressions(self, tmp_path):
        root = _tree(tmp_path, "")
        gl.append("access-tier", root, scope="erp", target="erp.t", found_by="x", cls="policy-open", tier="none", severity="critical")
        gl.append("access-tier", root, scope="erp", target="erp.u", found_by="x", cls="policy-open", tier="none",
                  status="accepted", detail="by design")
        doc = gl.export_sarif("access-tier", root)
        assert doc["version"] == "2.1.0"
        res = {r["properties"]["status"]: r for r in doc["runs"][0]["results"]}
        assert res["open"]["level"] == "error" and res["open"]["baselineState"] == "unchanged"
        assert res["accepted"]["suppressions"][0]["state"] == "accepted"

    def test_advisor_rows_join_and_blind_spots_are_reported(self, tmp_path):
        root = _tree(tmp_path, "", {"001.sql": _BASE})
        out = at.diff_exposure({"grants": [{"table_schema": "agents", "table_name": "compiled_prompts", "grantee": "authenticated",
                                            "privilege_type": "SELECT"}], "policies": [], "db_schemas": "public", "columns": [],
                                "advisors": [{"name": "rls_policy_always_true", "level": "WARN", "metadata": {"schema": "erp", "name": "metas"}}]}, root)
        assert any(f["kind"].startswith("advisor:") for f in out["findings"])
        assert "grant" in out["advisor_blind_spots"]


class TestOpenApiContract:
    """Docs stay public => the schema leaks nothing, hides Platform IP, and every documented non-public route is enforced."""

    def _app(self):
        import importlib.util
        from fastapi import Depends, FastAPI, HTTPException
        spec = importlib.util.spec_from_file_location("reg3", REPO / at.REGISTRY_REL)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

        def org(authorization: str | None = None):
            if authorization not in ("org", "admin"):
                raise HTTPException(401)
            return authorization

        def admin(authorization: str | None = None):
            if authorization == "org":
                raise HTTPException(403)
            return org(authorization)

        app = FastAPI()
        r_org = m.make_router(tier="org", guard=org, prefix="/api/o")
        r_pl = m.make_router(tier="platform", guard=admin, prefix="/api/p")

        @r_org.get("/x")
        def x(): return {}

        @r_pl.get("/y")
        def y(): return {}

        app.include_router(r_org)
        app.include_router(r_pl)
        return app

    def test_platform_router_is_left_out_of_the_public_schema(self):
        assert "/api/p/y" not in self._app().openapi()["paths"]
        assert "/api/o/x" in self._app().openapi()["paths"]

    def test_tier_contract_proves_401_and_403(self):
        from fastapi.testclient import TestClient
        from noctusai_lib.testing.openapi_tier_contract import assert_tier_contract
        app = self._app()
        tiers = {("GET", "/api/o/x"): "org"}
        assert assert_tier_contract(TestClient(app), tiers) == []
        assert any("NO declared tier" in f for f in assert_tier_contract(TestClient(app), {}))

    def test_tier_contract_catches_an_unprotected_documented_route(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from noctusai_lib.testing.openapi_tier_contract import assert_tier_contract
        app = FastAPI()

        @app.get("/open")
        def open_(): return {}
        fails = assert_tier_contract(TestClient(app), {("GET", "/open"): "org"})
        assert fails and "expected strictly 401" in fails[0]

    def test_schema_leak_scanner(self):
        from noctusai_lib.testing.openapi_tier_contract import schema_leaks
        bad = {"paths": {"/api/p/y": {"get": {"description": "You are Julia, the system prompt follows",
                                              "responses": {"500": {"description": "Traceback (most recent call last)"}}}}},
               "x": {"example": "sk-ABCDEFGHIJKLMNOP12345 at db.internal"}}
        kinds = " ".join(schema_leaks(bad, platform_paths=[("GET", "/api/p/y")]))
        for k in ("secret", "internal-host", "prompt-or-skill-text", "stack-trace", "PUBLIC schema"):
            assert k in kinds
        assert schema_leaks({"paths": {"/ok": {"get": {"description": "Lists things"}}}}) == []

    def test_platform_route_listed_in_schema_is_a_finding(self, tmp_path):
        src = ("from fastapi import APIRouter, Depends\nfrom app.dependencies import *\n"
               "router = APIRouter(prefix='/api/p')\n@router.get('/y')\ndef y(ctx=Depends(require_platform_admin)): ...\n")
        assert len(at.analyze_schema_exposure(_tree(tmp_path, src))) == 1
        hidden = src.replace("APIRouter(prefix='/api/p')", "APIRouter(prefix='/api/p', include_in_schema=False)")
        assert at.analyze_schema_exposure(_tree(tmp_path / "h", hidden)) == []

    def test_make_router_platform_is_hidden_by_default(self, tmp_path):
        """make_router(tier='platform') defaults include_in_schema=False: the prescribed form is not a finding,
        and an explicit include_in_schema=True on it still is."""
        src = ("from noctusai_lib.api.access_tiers import make_router\nfrom app.dependencies import *\n"
               "router = make_router(tier='platform', guard=require_platform_admin, prefix='/api/p')\n"
               "@router.get('/y')\ndef y(): ...\n")
        assert at.analyze_schema_exposure(_tree(tmp_path, src)) == []
        shown = src.replace("prefix='/api/p')", "prefix='/api/p', include_in_schema=True)")
        assert len(at.analyze_schema_exposure(_tree(tmp_path / "s", shown))) == 1


class TestAccessTierLedger:
    def test_clean_when_ledger_matches_and_flags_a_new_finding(self, tmp_path):
        root = _tree(tmp_path, _HEAD + "@router.post('/hook')\ndef hook(): ...\n")
        assert check_access_tier_ledger(root)                       # NEW finding without a row
        gl.reconcile("access-tier", root)
        assert check_access_tier_ledger(root) == []


class TestFindingsLedgerVisibility:
    def test_flags_unregistered_injection_hook_and_passes_when_wired(self, tmp_path):
        assert any("SessionStart" in i["issue"] or "missing" in i["issue"] for i in check_findings_ledger_visibility(tmp_path))
        assert check_findings_ledger_visibility(REPO) == []         # the real tree wires it


class TestFindingsLedgersAll:
    def test_all_ledgers_agree_with_reality_on_the_real_tree(self):
        assert check_findings_ledgers(REPO) == []


class TestCatalog:
    def test_catalog_renders_with_public_categories_and_docs_sections(self, tmp_path):
        root = _tree(tmp_path, _HEAD + "@router.get('/pricing')\n@limiter.limit('1/s')\n@access_tier('public', reason='r', category='pricing-checkout')\ndef p(): ...\n")
        md = at.render_catalog(root)
        assert "Public routes by category" in md and "pricing-checkout (1)" in md and "API docs exposure" in md


class TestWiringScannerKnowsMakeRouter:
    def test_prefix_regex_reads_the_typed_constructor(self):
        from tools.noctus.dev.scan_wiring import _APIROUTER_PREFIX_RE
        m = _APIROUTER_PREFIX_RE.search('router = make_router(tier="org", guard=get_current_user_org, prefix="/api/example")')
        assert m and m.group("prefix") == "/api/example"
