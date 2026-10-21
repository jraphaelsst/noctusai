"""Unit tests for `noctusai_lib.domain.sql_templates`.

Asserts exact output shape so a future agent can't accidentally drift
the canonical SQL conventions.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.sql_templates import (
    rls_subquery_policy,
    set_search_path,
    updated_at_function,
    updated_at_trigger,
)


# ---------------------------------------------------------------------------
# set_search_path
# ---------------------------------------------------------------------------


class TestSetSearchPath:
    def test_single_schema(self):
        assert set_search_path("erp") == "SET search_path = erp, public"

    def test_multi_schema_preserves_order(self):
        assert (
            set_search_path("therapy", "core")
            == "SET search_path = therapy, core, public"
        )

    def test_appends_public_only_once_even_if_passed(self):
        # Caller passing "public" explicitly is unusual but shouldn't
        # double-append. Document the actual behavior — public always
        # appears as the last segment, and a redundant "public" earlier
        # is preserved verbatim (caller's choice).
        assert (
            set_search_path("public", "erp")
            == "SET search_path = public, erp, public"
        )

    def test_no_args_raises(self):
        with pytest.raises(ValueError, match="at least one schema"):
            set_search_path()


# ---------------------------------------------------------------------------
# updated_at_function
# ---------------------------------------------------------------------------


class TestUpdatedAtFunction:
    def test_default_function_name(self):
        actual = updated_at_function("therapy")
        expected = (
            "CREATE OR REPLACE FUNCTION therapy.set_updated_at()\n"
            "RETURNS TRIGGER\n"
            "LANGUAGE plpgsql SECURITY DEFINER SET search_path = therapy, public\n"
            "AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;"
        )
        assert actual == expected

    def test_erp_legacy_function_name(self):
        # ERP's first migration used `update_updated_at_column`. Pass
        # explicitly to preserve that name in fresh ERP migrations.
        actual = updated_at_function("erp", function_name="update_updated_at_column")
        assert "FUNCTION erp.update_updated_at_column()" in actual
        assert "search_path = erp, public" in actual

    def test_search_path_locks_to_schema(self):
        for schema in ("erp", "therapy", "core", "daily_life", "personal_finance"):
            out = updated_at_function(schema)
            assert f"search_path = {schema}, public" in out, (
                f"function for {schema} must lock search_path to its own schema"
            )


# ---------------------------------------------------------------------------
# updated_at_trigger
# ---------------------------------------------------------------------------


class TestUpdatedAtTrigger:
    def test_default_trigger_name(self):
        actual = updated_at_trigger("therapy", "clinics")
        expected = (
            "CREATE OR REPLACE TRIGGER set_updated_at_clinics\n"
            "    BEFORE UPDATE ON therapy.clinics\n"
            "    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();"
        )
        assert actual == expected

    def test_custom_trigger_name(self):
        actual = updated_at_trigger(
            "erp", "matricula_extracoes",
            trigger_name="set_updated_at_matricula_extracoes",
        )
        assert "TRIGGER set_updated_at_matricula_extracoes" in actual
        assert "BEFORE UPDATE ON erp.matricula_extracoes" in actual

    def test_custom_function_name(self):
        actual = updated_at_trigger(
            "erp", "negociacoes",
            function_name="update_updated_at_column",
        )
        assert "EXECUTE FUNCTION erp.update_updated_at_column();" in actual
        # Trigger name still defaults to `set_updated_at_negociacoes`.
        assert "TRIGGER set_updated_at_negociacoes" in actual


# ---------------------------------------------------------------------------
# rls_subquery_policy
# ---------------------------------------------------------------------------


class TestRlsSubqueryPolicy:
    def test_select_policy(self):
        actual = rls_subquery_policy(
            "erp", "metas", "metas_select", "SELECT",
            using="(SELECT auth.uid()) = usuario_id",
        )
        expected = (
            'CREATE POLICY "metas_select" ON erp.metas FOR SELECT TO authenticated\n'
            "  USING ((SELECT auth.uid()) = usuario_id);"
        )
        assert actual == expected

    def test_insert_policy_requires_with_check(self):
        with pytest.raises(ValueError, match="INSERT policies require"):
            rls_subquery_policy(
                "erp", "metas", "metas_insert", "INSERT",
                using="something",  # USING is irrelevant for INSERT
            )

    def test_insert_policy_with_check_only(self):
        actual = rls_subquery_policy(
            "erp", "metas", "metas_insert", "INSERT",
            with_check="usuario_id = (SELECT auth.uid())",
        )
        assert "FOR INSERT TO authenticated" in actual
        assert "WITH CHECK (usuario_id = (SELECT auth.uid()))" in actual
        assert "USING (" not in actual

    def test_update_policy_using_and_with_check(self):
        actual = rls_subquery_policy(
            "erp", "metas", "metas_update", "UPDATE",
            using="(SELECT auth.uid()) = usuario_id",
            with_check="(SELECT auth.uid()) = usuario_id",
        )
        assert "USING ((SELECT auth.uid()) = usuario_id)" in actual
        assert "WITH CHECK ((SELECT auth.uid()) = usuario_id)" in actual

    def test_delete_policy_requires_using(self):
        with pytest.raises(ValueError, match="DELETE policies require"):
            rls_subquery_policy(
                "erp", "metas", "metas_delete", "DELETE",
                with_check="anything",
            )

    def test_anon_deny_policy(self):
        actual = rls_subquery_policy(
            "erp", "user_roles", "deny_anon", "ALL",
            using="false",
            to_role="anon",
        )
        assert "FOR ALL TO anon" in actual
        assert "USING (false)" in actual

    def test_invalid_command_raises(self):
        with pytest.raises(ValueError, match="command must be one of"):
            rls_subquery_policy(
                "erp", "metas", "x", "TRUNCATE",
                using="false",
            )

    def test_no_clauses_raises(self):
        with pytest.raises(ValueError, match="at least one of"):
            rls_subquery_policy("erp", "metas", "x", "ALL")

    def test_command_case_insensitive(self):
        actual = rls_subquery_policy(
            "erp", "metas", "x", "select",
            using="(SELECT auth.uid()) = usuario_id",
        )
        assert "FOR SELECT TO" in actual


# ---------------------------------------------------------------------------
# Org-identity functions + invitations.token lockdown (SEC-2, 2026-09-28)
# ---------------------------------------------------------------------------

from noctusai_lib.domain.sql_templates import (  # noqa: E402
    ORG_IDENTITY_FUNCTION_NAMES,
    customer_roles_sql_array,
    invitation_token_lockdown_sql,
    org_identity_function_sql,
    org_identity_functions_sql,
)
from noctusai_lib.primitives.roles import CUSTOMER_ORG_ROLES, is_customer_role  # noqa: E402


class TestOrgIdentityFunctions:
    def test_customer_array_is_rendered_from_the_frozenset(self):
        assert customer_roles_sql_array() == "ARRAY[" + ", ".join(
            f"'{r}'" for r in sorted(CUSTOMER_ORG_ROLES)) + "]"
        assert customer_roles_sql_array(["b", "a"]) == "ARRAY['a', 'b']"

    def test_current_org_id_excludes_customers(self):
        sql = org_identity_function_sql("current_org_id")
        assert "<> ALL (ARRAY['membro'])" in sql
        assert "COALESCE(org_role, '')" in sql  # a NULL role is staff, not excluded
        assert org_identity_function_sql("current_user_org_id").replace(
            "current_user_org_id", "current_org_id") == sql

    def test_current_org_id_is_the_plain_home_org_read(self):
        # Act-as-org was removed (core 067): no join, no staff override.
        for name in ("current_org_id", "current_user_org_id"):
            sql = org_identity_function_sql(name)
            assert "act_as_sessions" not in sql
            assert "role = 'admin'" not in sql

    def test_customer_org_is_the_mirror(self):
        sql = org_identity_function_sql("current_customer_org_id")
        assert "org_role = ANY (ARRAY['membro'])" in sql

    def test_every_function_is_security_definer_with_pinned_path(self):
        for name in ORG_IDENTITY_FUNCTION_NAMES:
            sql = org_identity_function_sql(name)
            assert "STABLE SECURITY DEFINER" in sql
            assert "SET search_path TO 'public'" in sql
            assert sql.startswith(f"CREATE OR REPLACE FUNCTION public.{name}()")

    def test_block_carries_every_function_once(self):
        block = org_identity_functions_sql()
        for name in ORG_IDENTITY_FUNCTION_NAMES:
            assert block.count(f"FUNCTION public.{name}()") == 1

    def test_unknown_name_refused(self):
        import pytest

        with pytest.raises(ValueError):
            org_identity_function_sql("current_everything")

    def test_is_customer_role(self):
        assert is_customer_role("membro")
        assert not is_customer_role("member")
        assert not is_customer_role(None)


class TestInvitationTokenLockdown:
    def test_revokes_table_select_and_regrants_all_but_token(self):
        sql = invitation_token_lockdown_sql("igig")
        assert "REVOKE SELECT ON igig.invitations FROM authenticated;" in sql
        assert "REVOKE ALL ON igig.invitations FROM anon;" in sql
        assert "column_name <> 'token'" in sql
        assert "GRANT SELECT (%s) ON igig.invitations TO authenticated" in sql

    def test_template_placeholder_schema_allowed(self):
        assert "{{SCHEMA_NAME}}.invitations" in invitation_token_lockdown_sql("{{SCHEMA_NAME}}")

    def test_injection_shaped_schema_refused(self):
        import pytest

        with pytest.raises(ValueError):
            invitation_token_lockdown_sql("igig; DROP TABLE x")


# ── invitation_token_lockdown_all_sql — core 056's platform-wide sweep ──


def test_lockdown_all_quotes_schema_names_so_hyphens_work():
    from noctusai_lib.domain.sql_templates import invitation_token_lockdown_all_sql

    sql = invitation_token_lockdown_all_sql()
    # %I (quote_ident) on every statement — `personal-finance` is a real schema.
    assert "REVOKE ALL ON %I.invitations FROM anon" in sql
    assert "REVOKE SELECT ON %I.invitations FROM authenticated" in sql
    assert "GRANT SELECT (%s) ON %I.invitations TO authenticated" in sql
    # Only tables that actually carry a token column are touched.
    assert "a.attname = 'token'" in sql


def test_core_056_is_exactly_the_rendered_sweep():
    """The migration file is RENDERED from the template, never hand-edited —
    a drifted copy would silently stop covering a schema the probe checks."""
    from pathlib import Path

    from noctusai_lib.domain.sql_templates import invitation_token_lockdown_all_sql

    repo = Path(__file__).resolve().parents[4]
    migration = repo / "products/core/backend/migrations/056_invitation_token_lockdown_all_schemas.sql"
    assert invitation_token_lockdown_all_sql() in migration.read_text()


class TestAiTablesTemplates:
    """ai_outputs / ai_feedback: the 4th hand-copy formalized (2026-10-10)."""

    def test_render_for_a_schema_and_stay_idempotent(self):
        from noctusai_lib.domain.sql_templates import ai_feedback_table_sql, ai_outputs_table_sql

        out, fb = ai_outputs_table_sql("demo"), ai_feedback_table_sql("demo")
        assert "CREATE TABLE IF NOT EXISTS demo.ai_outputs" in out
        assert "CREATE TABLE IF NOT EXISTS demo.ai_feedback" in fb
        for sql in (out, fb):
            # every policy is dropped before it is created, so a re-apply is safe
            assert sql.count("CREATE POLICY") == sql.count("DROP POLICY IF EXISTS")
            assert "current_org_id_for('demo')" in sql
            assert "REVOKE ALL ON" in sql and "FROM anon" in sql
        assert "UNIQUE (user_id, output_ref)" in fb  # the seed router upserts on it

    def test_refuse_an_unsafe_schema_name(self):
        import pytest

        from noctusai_lib.domain.sql_templates import ai_outputs_table_sql

        with pytest.raises(ValueError):
            ai_outputs_table_sql("x; DROP SCHEMA public")


# ---------------------------------------------------------------------------
# guc_carveout_guard_sql — reproduces the hand-written instances semantically
# ---------------------------------------------------------------------------

import re  # noqa: E402

from noctusai_lib.domain.sql_templates import (  # noqa: E402
    guc_carveout_guard_sql,
    guc_carveout_set_config_sql,
)


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


class TestGucCarveoutGuard:
    def test_core_audit_logs_purge_053(self):
        sql = guc_carveout_guard_sql(
            schema="public", table="audit_logs", guc="core.audit_log_purge",
            error_message="audit_logs_append_only", search_path=("public", "pg_temp"),
        )
        n = _norm(sql)
        assert "SECURITY DEFINER SET search_path = public, pg_temp" in n
        assert (
            "IF TG_OP = 'DELETE' AND current_setting('core.audit_log_purge', true) = 'on' THEN RETURN OLD;"
            in n
        )
        assert "RAISE EXCEPTION 'audit_logs_append_only' USING ERRCODE = 'P0001';" in n
        assert "BEFORE UPDATE OR DELETE ON public.audit_logs" in n
        assert "REVOKE ALL ON FUNCTION public.guard_audit_logs_append_only() FROM PUBLIC, anon, authenticated;" in n

    def test_compiled_prompt_erasure_012(self):
        n = _norm(guc_carveout_guard_sql(
            schema="agents", table="compiled_prompts", guc="agents.compiled_prompt_erasure",
            function="guard_compiled_prompt_immutable", trigger="guard_compiled_prompts_immutable",
            error_message="compiled_prompt_immutable",
        ))
        assert "current_setting('agents.compiled_prompt_erasure', true) = 'on' THEN RETURN OLD;" in n
        assert "CREATE TRIGGER guard_compiled_prompts_immutable BEFORE UPDATE OR DELETE ON agents.compiled_prompts" in n

    def test_agent_delete_048_null_only_update(self):
        n = _norm(guc_carveout_guard_sql(
            schema="agents", table="agent_audit_log", guc="agents.agent_delete",
            function="guard_audit_log_append_only", trigger="guard_agent_audit_log_append_only",
            error_message="audit_log_append_only", allow_ops=("UPDATE",),
            null_only_column="agent_id",
            frozen_columns=("id", "org_id", "actor", "acao", "antes", "depois", "created_at", "agent_key", "agent_nome"),
        ))
        assert "IF TG_OP = 'UPDATE' AND current_setting('agents.agent_delete', true) = 'on'" in n
        assert "AND OLD.agent_id IS NOT NULL AND NEW.agent_id IS NULL" in n
        assert "AND NEW.id IS NOT DISTINCT FROM OLD.id" in n
        assert "AND NEW.agent_nome IS NOT DISTINCT FROM OLD.agent_nome THEN RETURN NEW;" in n
        assert "BEFORE UPDATE OR DELETE ON agents.agent_audit_log" in n

    def test_write_only_via_function_018_style(self):
        n = _norm(guc_carveout_guard_sql(
            schema="agents", table="editorial_items", guc="editorial.in_transition",
            allow_ops=("INSERT", "UPDATE"), error_message="editorial_write_via_transition_only",
        ))
        assert "IF TG_OP = 'INSERT' AND current_setting('editorial.in_transition', true) = 'on' THEN RETURN NEW; ELSIF TG_OP = 'UPDATE'" in n
        assert "BEFORE INSERT OR UPDATE OR DELETE ON agents.editorial_items" in n

    def test_set_config_snippet(self):
        assert guc_carveout_set_config_sql("agents.agent_delete") == "PERFORM set_config('agents.agent_delete', 'on', true);"
        assert guc_carveout_set_config_sql("agents.agent_delete", on=False).endswith("'off', true);")

    @pytest.mark.parametrize("kwargs", [
        {"allow_ops": ()},
        {"allow_ops": ("TRUNCATE",)},
        {"frozen_columns": ("a",)},
        {"allow_ops": ("DELETE",), "null_only_column": "x"},
        {"table": "bad name"},
    ])
    def test_rejects_bad_input(self, kwargs):
        base = dict(schema="s", table="t", guc="s.flag")
        base.update(kwargs)
        with pytest.raises(ValueError):
            guc_carveout_guard_sql(**base)

    def test_guc_must_be_namespaced(self):
        with pytest.raises(ValueError):
            guc_carveout_set_config_sql("flag")
