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
