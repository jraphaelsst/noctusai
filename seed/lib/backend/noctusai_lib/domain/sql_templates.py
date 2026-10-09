"""Authoring-time helpers for canonical SQL DDL the platform reuses.

Pure string emission — no IO, no DB access. Use these in migration files
and the scaffold tool so the SECURITY DEFINER / search_path / updated_at /
RLS subquery conventions can't drift across products.

The shapes here mirror what every product schema currently authors by
hand. They are *authoring-time* helpers — existing migration files are
authoritative replay logs and MUST stay verbatim per the
"MCP migrations mirror the file" rule. Use these in:
- New migrations being authored fresh.
- The product-scaffold tool that bootstraps a new product's schema.

Adopted 2026-05-01 by `projects/sql-templates-absorption/` (Wave A of
the first-batch absorptions queue).
"""
from __future__ import annotations

from typing import Iterable


def set_search_path(*schemas: str) -> str:
    """Emit ``SET search_path = <schemas>, public`` — schema-lock prelude.

    Used inside a SECURITY DEFINER function declaration to pin name
    resolution. Always trails with ``, public`` automatically because
    every adopter follows that convention.

        >>> set_search_path("erp")
        'SET search_path = erp, public'
        >>> set_search_path("therapy", "core")
        'SET search_path = therapy, core, public'

    Raises ``ValueError`` if no schema is provided — calling
    ``set_search_path()`` with no args is always a bug.
    """
    if not schemas:
        raise ValueError("set_search_path requires at least one schema")
    parts = [*schemas, "public"]
    return f"SET search_path = {', '.join(parts)}"


def updated_at_function(
    schema: str,
    function_name: str = "set_updated_at",
) -> str:
    """Emit the canonical auto-touch helper function for ``<schema>``.

    Every schema needs exactly one of these — invoked by every
    ``BEFORE UPDATE`` trigger that wants ``updated_at`` to track the
    last modification. The function is SECURITY DEFINER + search-path
    locked so it works correctly when called by RLS-enforced clients.

        >>> print(updated_at_function("erp"))
        CREATE OR REPLACE FUNCTION erp.set_updated_at()
        RETURNS TRIGGER
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = erp, public
        AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

    The default ``function_name="set_updated_at"`` matches therapy /
    daily-life / personal-finance / mailing. ERP's first migration
    used ``update_updated_at_column`` — pass it explicitly there.
    """
    return (
        f"CREATE OR REPLACE FUNCTION {schema}.{function_name}()\n"
        f"RETURNS TRIGGER\n"
        f"LANGUAGE plpgsql SECURITY DEFINER SET search_path = {schema}, public\n"
        f"AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;"
    )


def updated_at_trigger(
    schema: str,
    table: str,
    function_name: str = "set_updated_at",
    trigger_name: str | None = None,
) -> str:
    """Emit a ``BEFORE UPDATE`` trigger that calls ``<schema>.<function_name>``.

    ``trigger_name`` defaults to ``set_updated_at_<table>`` (the
    convention every adopter follows). Override only when the table
    name collides with a reserved identifier or the schema-wide
    naming convention demands something else.

        >>> print(updated_at_trigger("therapy", "clinics"))
        CREATE OR REPLACE TRIGGER set_updated_at_clinics
            BEFORE UPDATE ON therapy.clinics
            FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();
    """
    name = trigger_name or f"set_updated_at_{table}"
    return (
        f"CREATE OR REPLACE TRIGGER {name}\n"
        f"    BEFORE UPDATE ON {schema}.{table}\n"
        f"    FOR EACH ROW EXECUTE FUNCTION {schema}.{function_name}();"
    )


def service_role_bypass(table: str, schema: str = "public") -> str:
    """Emit the canonical ``service_role_bypass`` policy for one table.

    Keeper-detector coupling: the platform's
    ``check_admin_endpoint_service_role_bypass`` detector (CLI ``--review``)
    searches each migration for a policy whose *literal name* is
    ``service_role_bypass``. Equivalent policies under different names
    are flagged as defense-in-depth gaps even when they work at runtime —
    so the literal name MUST be preserved by every caller. Renaming the
    policy re-opens every keeper finding for that table.

    Output shape mirrors ``products/therapy-platform/backend/migrations/
    001_therapy_platform.sql:846+`` — the canonical reference adopter.
    Byte-equal output is verified in the test suite.

    Args:
        table: Table name within ``schema`` (e.g. ``"clinics"``).
        schema: Schema-qualifying the table. Defaults to ``"public"``
            (matches the few core tables that don't use a product-private
            schema). Pass the product schema for every real adopter
            (``"therapy"``, ``"erp"``, ``"mailing"``, ...). Dashed schema
            names (``"personal-finance"``) pass through unchanged —
            Postgres-quoting is the caller's responsibility upstream.

    Returns:
        A single-line ``CREATE POLICY`` string terminated with ``;``. No
        trailing newline — callers compose with ``"\n"``-joined sections.

    Example::

        >>> service_role_bypass("clinics", schema="therapy")
        'CREATE POLICY "service_role_bypass" ON therapy.clinics FOR ALL TO service_role USING (true) WITH CHECK (true);'

    Raises:
        ValueError: If ``table`` or ``schema`` is empty / all-whitespace.
    """
    if not table or not table.strip():
        raise ValueError("service_role_bypass requires a non-empty table")
    if not schema or not schema.strip():
        raise ValueError("service_role_bypass requires a non-empty schema")
    return (
        f'CREATE POLICY "service_role_bypass" ON {schema}.{table} '
        f"FOR ALL TO service_role USING (true) WITH CHECK (true);"
    )


def rls_subquery_policy(
    schema: str,
    table: str,
    policy_name: str,
    command: str,
    using: str | None = None,
    with_check: str | None = None,
    to_role: str = "authenticated",
) -> str:
    """Emit a ``CREATE POLICY`` that uses the ``(SELECT auth.uid())`` subquery shape.

    Why subquery? Postgres planner evaluates ``(SELECT auth.uid())``
    once per query, not per row — meaningful speedup on large tables.
    Plain ``auth.uid()`` re-evaluates per row. This is the platform
    standard documented in ``KB § PATTERNS/database-rls.md``.

    Args:
        schema: Schema-qualifying the table (``erp``, ``therapy``, ...).
        table: Table name within the schema.
        policy_name: Name of the policy. Quoted in output.
        command: One of ``SELECT``, ``INSERT``, ``UPDATE``, ``DELETE``,
            ``ALL``. Case-insensitive.
        using: ``USING`` clause body (without the keyword). Required
            for SELECT/UPDATE/DELETE/ALL; optional for INSERT.
        with_check: ``WITH CHECK`` clause body. Required for
            INSERT/UPDATE; optional for ALL.
        to_role: Role the policy applies to. Defaults to
            ``authenticated`` — the platform default. Pass
            ``"anon"`` for a deny-policy on unauthenticated traffic.

    Caller is responsible for using the canonical subquery shape in
    the ``using`` / ``with_check`` strings. Example:

        >>> print(rls_subquery_policy(
        ...     "erp", "metas", "metas_select", "SELECT",
        ...     using="(SELECT auth.uid()) = usuario_id",
        ... ))
        CREATE POLICY "metas_select" ON erp.metas FOR SELECT TO authenticated
          USING ((SELECT auth.uid()) = usuario_id);
    """
    cmd = command.strip().upper()
    valid = {"SELECT", "INSERT", "UPDATE", "DELETE", "ALL"}
    if cmd not in valid:
        raise ValueError(
            f"command must be one of {sorted(valid)}; got {command!r}"
        )
    if using is None and with_check is None:
        raise ValueError(
            "rls_subquery_policy needs at least one of `using` or `with_check`"
        )
    if cmd == "INSERT" and with_check is None:
        raise ValueError("INSERT policies require `with_check`")
    if cmd in {"SELECT", "DELETE"} and using is None:
        raise ValueError(f"{cmd} policies require `using`")

    lines = [f'CREATE POLICY "{policy_name}" ON {schema}.{table} FOR {cmd} TO {to_role}']
    if using is not None:
        lines.append(f"  USING ({using})")
    if with_check is not None:
        # Append `WITH CHECK` to the previous line if no USING, otherwise on its own line.
        suffix = f"  WITH CHECK ({with_check})"
        lines.append(suffix)
    return "\n".join(lines) + ";"


# ---------------------------------------------------------------------------
# Org-identity functions — the ONE definition behind every org-scoped RLS
# policy in every schema (SEC-2 customer-role isolation, 2026-09-28).
# ---------------------------------------------------------------------------
#
# `public.current_org_id()` (and its core twin `current_user_org_id()`) is
# re-declared by `CREATE OR REPLACE` in MANY migration chains — every
# product's 001, the template's 001_seed.sql, core 001/035, and each forward
# migration that touches it. They all write the same shared `public`
# function, so on a fresh environment the LAST chain applied wins: one
# stale copy anywhere silently reverts the whole fleet. The rendering below
# is therefore the only allowed body, and keeper
# `check_org_identity_function_parity` fails any migration whose
# re-declaration differs from it.
#
# Customers (`CUSTOMER_ORG_ROLES`, e.g. `membro`) get NULL from
# `current_org_id()` — so every `org_id = public.current_org_id()` policy
# denies them at once, in every schema, without touching a single policy.
# A product that genuinely serves customers keys its customer-facing
# policies on `public.current_customer_org_id()` instead (non-NULL ONLY for
# a customer), never on `current_org_id()`.

#: Every shared org-identity function the parity keeper polices.
ORG_IDENTITY_FUNCTION_NAMES: tuple[str, ...] = (
    "current_org_id",
    "current_user_org_id",
    "current_org_role",
    "is_customer",
    "current_customer_org_id",
)


#: Org-picker RLS helpers (core 070) the parity keeper polices alongside the
#: functions above. A SEPARATE tuple on purpose: ``org_identity_functions_sql()``
#: embeds every ``ORG_IDENTITY_FUNCTION_NAMES`` member in forward migrations of
#: any chain, while these read ``platform_org_selections`` (core 070 only).
#: ``current_org_id_for(p_schema)`` is the ONLY org-picker-aware helper; the
#: functions above stay HOME-ONLY forever (public tables / storage / realtime
#: never act-as). KB § PATTERNS/backend/tenancy-license-gate.md § Platform org picker.
ORG_PICKER_FUNCTION_NAMES: tuple[str, ...] = ("current_org_id_for",)


def customer_roles_sql_array(customer_roles: Iterable[str] | None = None) -> str:
    """``ARRAY['membro', ...]`` rendered from ``CUSTOMER_ORG_ROLES`` (sorted,
    so the rendering is deterministic).

    ``customer_roles`` overrides the source set — used ONLY by the parity
    keeper, which loads this module straight from a worktree's file and
    must not import whichever ``noctusai_lib`` the interpreter happens to
    resolve (the primary checkout's, from a worktree).
    """
    if customer_roles is None:
        from noctusai_lib.primitives.roles import CUSTOMER_ORG_ROLES

        customer_roles = CUSTOMER_ORG_ROLES
    return "ARRAY[" + ", ".join(f"'{r}'" for r in sorted(customer_roles)) + "]"


def _org_fn(name: str, returns: str, body: str) -> str:
    return (
        f"CREATE OR REPLACE FUNCTION public.{name}()\n"
        f"  RETURNS {returns}\n"
        "  LANGUAGE sql\n"
        "  STABLE SECURITY DEFINER\n"
        "  SET search_path TO 'public'\n"
        "AS $f$\n"
        f"{body}\n"
        "$f$;"
    )


def _org_picker_fn_sql(roles: str) -> str:
    """Canonical ``public.current_org_id_for(p_schema text)`` — the product-policy
    opt-in (``(SELECT public.current_org_id_for('<schema>'))``) for the platform org
    picker. Staff (``noctus_users.role='admin'`` AND home org ``is_platform``) with a
    LIVE selection for the product whose ``db_schema = p_schema``, bound to THIS login
    (``session_id`` claim), aal2, target still licensed, and (optional narrowing)
    ``x-noctus-acting-org`` equal to the target, resolve to the target org; EVERYONE
    else resolves the home rule (customers excluded → NULL)."""
    return (
        "CREATE OR REPLACE FUNCTION public.current_org_id_for(p_schema text)\n"
        "  RETURNS uuid\n"
        "  LANGUAGE plpgsql\n"
        "  STABLE SECURITY DEFINER\n"
        "  SET search_path TO 'public'\n"
        "AS $f$\n"
        "DECLARE\n"
        "  v_uid      uuid := auth.uid();\n"
        "  v_claims   jsonb := auth.jwt();\n"
        "  v_home     uuid;\n"
        "  v_org_role text;\n"
        "  v_role     text;\n"
        "  v_target   uuid;\n"
        "  v_hdr      text;\n"
        "BEGIN\n"
        "  SELECT u.org_id, u.org_role, u.role INTO v_home, v_org_role, v_role\n"
        "    FROM public.noctus_users u WHERE u.id = v_uid;\n"
        "  IF NOT FOUND THEN\n"
        "    RETURN NULL;\n"
        "  END IF;\n"
        f"  IF COALESCE(v_org_role, '') = ANY ({roles}) THEN\n"
        "    RETURN NULL;\n"
        "  END IF;\n"
        "  IF v_role = 'admin' AND p_schema IS NOT NULL\n"
        "     AND EXISTS (SELECT 1 FROM public.organizations o WHERE o.id = v_home AND o.is_platform)\n"
        "  THEN\n"
        "    SELECT s.target_org_id INTO v_target\n"
        "      FROM public.products p\n"
        "      JOIN public.platform_org_selections s\n"
        "        ON s.product_id = p.id AND s.user_id = v_uid AND s.ended_at IS NULL\n"
        "     WHERE p.db_schema = p_schema\n"
        "       AND s.auth_session_id = NULLIF(v_claims ->> 'session_id', '')::uuid\n"
        "       AND v_claims ->> 'aal' = 'aal2'\n"
        "       AND EXISTS (\n"
        "         SELECT 1 FROM public.licenses l\n"
        "          WHERE l.org_id = s.target_org_id AND l.product_id = p.id\n"
        "            AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()));\n"
        "    IF FOUND THEN\n"
        "      BEGIN\n"
        "        v_hdr := NULLIF(btrim(NULLIF(current_setting('request.headers', true), '')::json\n"
        "                              ->> 'x-noctus-acting-org'), '');\n"
        "      EXCEPTION WHEN OTHERS THEN\n"
        "        v_hdr := NULL;\n"
        "      END;\n"
        "      IF v_hdr IS NULL OR lower(v_hdr) = v_target::text THEN\n"
        "        RETURN v_target;\n"
        "      END IF;\n"
        "    END IF;\n"
        "  END IF;\n"
        "  RETURN v_home;\n"
        "END;\n"
        "$f$;"
    )


def org_identity_function_sql(name: str, customer_roles: Iterable[str] | None = None) -> str:
    """The canonical ``CREATE OR REPLACE FUNCTION public.<name>()`` statement.

    Paste it verbatim into any migration that (re)declares ``<name>`` — the
    parity keeper compares whitespace-normalized text against this.
    """
    roles = customer_roles_sql_array(customer_roles)
    if name == "current_org_id_for":
        return _org_picker_fn_sql(roles)
    staff_org = (
        "  SELECT org_id FROM public.noctus_users\n"
        "   WHERE id = (SELECT auth.uid())\n"
        f"     AND COALESCE(org_role, '') <> ALL ({roles});"
    )
    if name in ("current_org_id", "current_user_org_id"):
        return _org_fn(name, "uuid", staff_org)
    if name == "current_org_role":
        return _org_fn(
            name,
            "text",
            "  SELECT org_role FROM public.noctus_users WHERE id = (SELECT auth.uid());",
        )
    if name == "is_customer":
        return _org_fn(
            name,
            "boolean",
            "  SELECT COALESCE(\n"
            f"    (SELECT org_role = ANY ({roles})\n"
            "       FROM public.noctus_users WHERE id = (SELECT auth.uid())),\n"
            "    false\n"
            "  );",
        )
    if name == "current_customer_org_id":
        return _org_fn(
            name,
            "uuid",
            "  SELECT org_id FROM public.noctus_users\n"
            "   WHERE id = (SELECT auth.uid())\n"
            f"     AND org_role = ANY ({roles});",
        )
    raise ValueError(
        f"unknown org-identity function {name!r}; expected one of "
        f"{ORG_IDENTITY_FUNCTION_NAMES + ORG_PICKER_FUNCTION_NAMES}"
    )


def org_identity_functions_sql() -> str:
    """Every canonical org-identity function, in one block.

    The block a forward migration embeds so the functions are correct no
    matter which product chain a fresh environment applies last. EXECUTE
    grants are deliberately left at the PostgreSQL default (PUBLIC): many
    policies carry no ``TO`` clause and so also evaluate for ``anon`` — a
    revoked EXECUTE would turn their "0 rows" into a 42501 error. For an
    anonymous caller every function already answers NULL / false.
    """
    return "\n\n".join(org_identity_function_sql(n) for n in ORG_IDENTITY_FUNCTION_NAMES)


def invitation_token_lockdown_sql(schema: str) -> str:
    """Make ``<schema>.invitations.token`` unreadable through the API roles.

    A column REVOKE is a no-op while the table-level SELECT grant stands
    (Supabase's default privileges grant ALL on every table), so the table
    grant is revoked and SELECT re-granted on every column EXCEPT ``token``
    — derived from the live catalog, so a column added later is not
    silently exposed or silently dropped from the list. ``anon`` loses the
    table entirely. The seed invite flow reads/validates tokens through the
    service role, which this does not touch.
    """
    if not schema or not schema.replace("_", "").replace("{", "").replace("}", "").isalnum():
        raise ValueError(f"invalid schema name {schema!r}")
    # SQL DDL text for a migration file — never a PostgREST table argument.
    table = f"{schema}.invitations"  # postgrest-qualified-ok
    return (
        "DO $lock$\n"
        "DECLARE\n"
        "  v_cols text;\n"
        "BEGIN\n"
        f"  IF to_regclass('{table}') IS NULL THEN\n"
        f"    RAISE NOTICE 'no {table} table — nothing to lock';\n"
        "    RETURN;\n"
        "  END IF;\n"
        "  SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)\n"
        "    INTO v_cols\n"
        "    FROM information_schema.columns\n"
        f"   WHERE table_schema = '{schema}' AND table_name = 'invitations'\n"
        "     AND column_name <> 'token';\n"
        f"  REVOKE ALL ON {table} FROM anon;\n"
        f"  REVOKE SELECT ON {table} FROM authenticated;\n"
        f"  EXECUTE format('GRANT SELECT (%s) ON {table} TO authenticated', v_cols);\n"
        "END\n"
        "$lock$;"
    )


def invitation_token_lockdown_all_sql() -> str:
    """``invitation_token_lockdown_sql`` for EVERY schema that has an
    ``invitations`` table with a ``token`` column — the platform-wide form.

    The per-schema form is what each product's own migration renders; this
    one is core's sweep for the schemas no awake product migrates (asleep
    and legacy products whose tables still live in the shared DB), which the
    platform-wide ``invitations.token_not_api_readable`` probe also checks.
    Same statements, same live-catalog column derivation; schema names are
    ``quote_ident``-ed, so a hyphenated schema (``personal-finance``) works.
    Idempotent: re-running re-derives the same column grant.
    """
    return (
        "DO $lock_all$\n"
        "DECLARE\n"
        "  r record;\n"
        "  v_cols text;\n"
        "BEGIN\n"
        "  FOR r IN\n"
        "    SELECT n.nspname AS sch\n"
        "      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace\n"
        "     WHERE c.relname = 'invitations' AND c.relkind = 'r'\n"
        "       AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid\n"
        "                    AND a.attname = 'token' AND NOT a.attisdropped)\n"
        "  LOOP\n"
        "    SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)\n"
        "      INTO v_cols\n"
        "      FROM information_schema.columns\n"
        "     WHERE table_schema = r.sch AND table_name = 'invitations'\n"
        "       AND column_name <> 'token';\n"
        "    EXECUTE format('REVOKE ALL ON %I.invitations FROM anon', r.sch);\n"
        "    EXECUTE format('REVOKE SELECT ON %I.invitations FROM authenticated', r.sch);\n"
        "    EXECUTE format('GRANT SELECT (%s) ON %I.invitations TO authenticated', v_cols, r.sch);\n"
        "  END LOOP;\n"
        "END\n"
        "$lock_all$;"
    )



# ---------------------------------------------------------------------------
# Editorial workflow tables (seed `domain/editorial`)
# ---------------------------------------------------------------------------

EDITORIAL_IN_TRANSITION_GUC = "editorial.in_transition"

_EDITORIAL_SQL = r"""
-- Editorial workflow (seed domain/editorial). Three tables, write-once / append-only,
-- every state change through __S__.editorial_create_item / editorial_transition.
-- RLS deny-by-default: no policy but service_role_bypass; consumers add an org-scoped
-- SELECT policy only if a client reads directly. The DB re-checks legality + separation
-- of duties; the GRANTS it receives (p_grants) come from the caller (the permissions
-- organ) — the DB cannot see them, so only the service-role API may call these functions.

CREATE TABLE IF NOT EXISTS __S__.editorial_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    kind                TEXT NOT NULL,
    ref                 TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'rascunho',
    published_version_n INTEGER NULL,
    current_version_n   INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT editorial_items_state_check CHECK (state IN (__STATES__)),
    CONSTRAINT editorial_items_org_kind_ref_key UNIQUE (org_id, kind, ref),
    CONSTRAINT editorial_items_version_order_check
        CHECK (published_version_n IS NULL OR published_version_n <= current_version_n)
);

CREATE TABLE IF NOT EXISTS __S__.editorial_versions (
    item_id     UUID NOT NULL REFERENCES __S__.editorial_items(id) ON DELETE RESTRICT,
    n           INTEGER NOT NULL CHECK (n >= 1),
    content     JSONB NOT NULL,
    content_sha TEXT NOT NULL,
    author_id   UUID NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, n),
    CONSTRAINT editorial_versions_sha_check CHECK (content_sha ~ '^[0-9a-f]{64}$')
);

CREATE TABLE IF NOT EXISTS __S__.editorial_events (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id    UUID NOT NULL,
    version_n  INTEGER NOT NULL,
    action     TEXT NOT NULL CHECK (action IN (__ACTIONS__)),
    from_state TEXT NULL,
    to_state   TEXT NOT NULL,
    actor_id   UUID NOT NULL,
    grant_name TEXT NULL,
    motivo     TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (item_id, version_n) REFERENCES __S__.editorial_versions(item_id, n) ON DELETE RESTRICT,
    CONSTRAINT editorial_events_motivo_check
        CHECK (action NOT IN (__MOTIVO_ACTIONS__) OR length(btrim(coalesce(motivo, ''))) > 0)
);

CREATE INDEX IF NOT EXISTS idx_editorial_items_org_state ON __S__.editorial_items (org_id, state);
CREATE INDEX IF NOT EXISTS idx_editorial_events_item ON __S__.editorial_events (item_id, id);

ALTER TABLE __S__.editorial_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE __S__.editorial_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE __S__.editorial_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_bypass" ON __S__.editorial_items FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON __S__.editorial_versions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON __S__.editorial_events FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON __S__.editorial_items, __S__.editorial_versions, __S__.editorial_events FROM anon, authenticated;

-- The rule table, GENERATED from the Python workflow (never hand-edited here).
CREATE OR REPLACE FUNCTION __S__.editorial_rules()
RETURNS TABLE (action TEXT, from_state TEXT, to_state TEXT, grant_name TEXT, needs_motivo BOOLEAN,
               not_author BOOLEAN, not_editorial_approver BOOLEAN, needs_security_signoff BOOLEAN,
               creates_version BOOLEAN)
LANGUAGE sql IMMUTABLE SET search_path = __S__, public
AS $fn$
    SELECT * FROM (VALUES
__RULES__
    ) AS r(action, from_state, to_state, grant_name, needs_motivo, not_author,
           not_editorial_approver, needs_security_signoff, creates_version)
$fn$;

-- Immutability: versions are write-once, events append-only. DELETE is refused too.
CREATE OR REPLACE FUNCTION __S__.editorial_guard_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = __S__, public
AS $fn$
BEGIN
    IF TG_TABLE_NAME = 'editorial_versions' THEN
        RAISE EXCEPTION 'editorial_version_immutable' USING ERRCODE = 'P0001';
    END IF;
    RAISE EXCEPTION 'editorial_event_append_only' USING ERRCODE = 'P0001';
END;
$fn$;

-- Writes only inside editorial_create_item / editorial_transition (they raise the
-- transaction-local flag). A direct service-role INSERT/UPDATE/DELETE cannot forge a
-- state, a version or an audit event around the legality + separation-of-duties checks.
CREATE OR REPLACE FUNCTION __S__.editorial_guard_via_transition()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = __S__, public
AS $fn$
BEGIN
    IF current_setting('__GUC__', true) IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION 'editorial_write_via_transition_only' USING ERRCODE = 'P0001';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'editorial_write_via_transition_only' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION __S__.editorial_create_item(
    p_org_id UUID, p_kind TEXT, p_ref TEXT, p_actor_id UUID, p_grants TEXT[],
    p_content JSONB, p_content_sha TEXT
) RETURNS UUID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = __S__, public
AS $fn$
DECLARE
    v_rule RECORD;
    v_id UUID;
BEGIN
    SELECT * INTO v_rule FROM __S__.editorial_rules() r WHERE r.action = 'create';
    IF p_actor_id IS NULL THEN
        RAISE EXCEPTION 'editorial_actor_required' USING ERRCODE = 'P0001';
    END IF;
    IF NOT (v_rule.grant_name = ANY (coalesce(p_grants, ARRAY[]::TEXT[]))) THEN
        RAISE EXCEPTION 'editorial_missing_grant' USING ERRCODE = 'P0001';
    END IF;
    IF p_content IS NULL OR p_content_sha IS NULL THEN
        RAISE EXCEPTION 'editorial_content_required' USING ERRCODE = 'P0001';
    END IF;
    PERFORM set_config('__GUC__', 'on', true);
    INSERT INTO __S__.editorial_items (org_id, kind, ref, state, current_version_n)
    VALUES (p_org_id, p_kind, p_ref, v_rule.to_state, 1) RETURNING id INTO v_id;
    INSERT INTO __S__.editorial_versions (item_id, n, content, content_sha, author_id)
    VALUES (v_id, 1, p_content, p_content_sha, p_actor_id);
    INSERT INTO __S__.editorial_events (item_id, version_n, action, from_state, to_state, actor_id, grant_name)
    VALUES (v_id, 1, 'create', NULL, v_rule.to_state, p_actor_id, v_rule.grant_name);
    PERFORM set_config('__GUC__', 'off', true);
    RETURN v_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION __S__.editorial_transition(
    p_org_id UUID, p_item_id UUID, p_action TEXT, p_actor_id UUID, p_grants TEXT[],
    p_motivo TEXT DEFAULT NULL, p_content JSONB DEFAULT NULL, p_content_sha TEXT DEFAULT NULL
) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = __S__, public
AS $fn$
DECLARE
    v_item __S__.editorial_items%ROWTYPE;
    v_rule RECORD;
    v_n INTEGER;
    v_new_n INTEGER;
    v_author UUID;
    v_last_submit BIGINT;
    v_ed_approver UUID;
    v_signed BOOLEAN;
    v_published INTEGER;
    v_event BIGINT;
BEGIN
    SELECT * INTO v_item FROM __S__.editorial_items
     WHERE id = p_item_id AND org_id = p_org_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'editorial_item_not_found' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_rule FROM __S__.editorial_rules() r
     WHERE r.action = p_action AND r.from_state = v_item.state;
    IF NOT FOUND THEN
        IF NOT EXISTS (SELECT 1 FROM __S__.editorial_rules() r WHERE r.action = p_action) THEN
            RAISE EXCEPTION 'editorial_unknown_action' USING ERRCODE = 'P0001';
        END IF;
        RAISE EXCEPTION 'editorial_illegal_transition' USING ERRCODE = 'P0001';
    END IF;

    v_n := v_item.current_version_n;
    SELECT v.author_id INTO v_author FROM __S__.editorial_versions v
     WHERE v.item_id = p_item_id AND v.n = v_n;
    SELECT coalesce(max(e.id), 0) INTO v_last_submit FROM __S__.editorial_events e
     WHERE e.item_id = p_item_id AND e.version_n = v_n AND e.action = 'submit';
    SELECT e.actor_id INTO v_ed_approver FROM __S__.editorial_events e
     WHERE e.item_id = p_item_id AND e.version_n = v_n AND e.action = 'approve_editorial'
       AND e.id > v_last_submit ORDER BY e.id DESC LIMIT 1;
    SELECT EXISTS (SELECT 1 FROM __S__.editorial_events e
     WHERE e.item_id = p_item_id AND e.version_n = v_n AND e.action = 'approve_security'
       AND e.id > v_last_submit) INTO v_signed;

    IF p_action = 'approve_security' AND v_signed THEN
        RAISE EXCEPTION 'editorial_illegal_transition' USING ERRCODE = 'P0001';
    END IF;
    IF p_actor_id IS NULL THEN
        RAISE EXCEPTION 'editorial_actor_required' USING ERRCODE = 'P0001';
    END IF;
    IF NOT (v_rule.grant_name = ANY (coalesce(p_grants, ARRAY[]::TEXT[]))) THEN
        RAISE EXCEPTION 'editorial_missing_grant' USING ERRCODE = 'P0001';
    END IF;
    IF v_rule.needs_motivo AND length(btrim(coalesce(p_motivo, ''))) = 0 THEN
        RAISE EXCEPTION 'editorial_motivo_required' USING ERRCODE = 'P0001';
    END IF;
    IF v_rule.creates_version AND (p_content IS NULL OR p_content_sha IS NULL) THEN
        RAISE EXCEPTION 'editorial_content_required' USING ERRCODE = 'P0001';
    END IF;
    IF v_rule.not_author AND p_actor_id = v_author THEN
        RAISE EXCEPTION 'editorial_self_approval' USING ERRCODE = 'P0001';
    END IF;
    IF v_rule.not_editorial_approver AND p_actor_id IS NOT DISTINCT FROM v_ed_approver THEN
        RAISE EXCEPTION 'editorial_same_approver' USING ERRCODE = 'P0001';
    END IF;
    IF v_rule.needs_security_signoff AND NOT v_signed THEN
        RAISE EXCEPTION 'editorial_security_signoff_missing' USING ERRCODE = 'P0001';
    END IF;

    PERFORM set_config('__GUC__', 'on', true);
    v_new_n := v_n;
    IF v_rule.creates_version THEN
        v_new_n := v_n + 1;
        INSERT INTO __S__.editorial_versions (item_id, n, content, content_sha, author_id)
        VALUES (p_item_id, v_new_n, p_content, p_content_sha, p_actor_id);
    END IF;
    v_published := v_item.published_version_n;
    IF p_action = 'publish' THEN
        v_published := v_n;
    ELSIF p_action = 'archive' THEN
        v_published := NULL;
    END IF;
    UPDATE __S__.editorial_items
       SET state = v_rule.to_state, current_version_n = v_new_n,
           published_version_n = v_published, updated_at = now()
     WHERE id = p_item_id;
    INSERT INTO __S__.editorial_events
        (item_id, version_n, action, from_state, to_state, actor_id, grant_name, motivo)
    VALUES (p_item_id, v_new_n, p_action, v_rule.from_state, v_rule.to_state, p_actor_id,
            v_rule.grant_name, nullif(btrim(coalesce(p_motivo, '')), ''))
    RETURNING id INTO v_event;
    PERFORM set_config('__GUC__', 'off', true);
    RETURN v_event;
END;
$fn$;

DROP TRIGGER IF EXISTS editorial_guard_versions_immutable ON __S__.editorial_versions;
CREATE TRIGGER editorial_guard_versions_immutable
    BEFORE UPDATE OR DELETE ON __S__.editorial_versions
    FOR EACH ROW EXECUTE FUNCTION __S__.editorial_guard_immutable();
DROP TRIGGER IF EXISTS editorial_guard_events_append_only ON __S__.editorial_events;
CREATE TRIGGER editorial_guard_events_append_only
    BEFORE UPDATE OR DELETE ON __S__.editorial_events
    FOR EACH ROW EXECUTE FUNCTION __S__.editorial_guard_immutable();
DROP TRIGGER IF EXISTS editorial_guard_items_via_transition ON __S__.editorial_items;
CREATE TRIGGER editorial_guard_items_via_transition
    BEFORE INSERT OR UPDATE OR DELETE ON __S__.editorial_items
    FOR EACH ROW EXECUTE FUNCTION __S__.editorial_guard_via_transition();
DROP TRIGGER IF EXISTS editorial_guard_versions_via_transition ON __S__.editorial_versions;
CREATE TRIGGER editorial_guard_versions_via_transition
    BEFORE INSERT ON __S__.editorial_versions
    FOR EACH ROW EXECUTE FUNCTION __S__.editorial_guard_via_transition();
DROP TRIGGER IF EXISTS editorial_guard_events_via_transition ON __S__.editorial_events;
CREATE TRIGGER editorial_guard_events_via_transition
    BEFORE INSERT ON __S__.editorial_events
    FOR EACH ROW EXECUTE FUNCTION __S__.editorial_guard_via_transition();

-- SECURITY DEFINER EXECUTE LOCKDOWN: Postgres grants EXECUTE to PUBLIC by default.
REVOKE ALL ON FUNCTION __S__.editorial_guard_immutable() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION __S__.editorial_guard_via_transition() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION __S__.editorial_create_item(UUID, TEXT, TEXT, UUID, TEXT[], JSONB, TEXT)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION __S__.editorial_transition(UUID, UUID, TEXT, UUID, TEXT[], TEXT, JSONB, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION __S__.editorial_create_item(UUID, TEXT, TEXT, UUID, TEXT[], JSONB, TEXT)
    TO service_role;
GRANT EXECUTE ON FUNCTION __S__.editorial_transition(UUID, UUID, TEXT, UUID, TEXT[], TEXT, JSONB, TEXT)
    TO service_role;
"""


def _sql_text_lit(value: str | None) -> str:
    return "NULL::text" if value is None else "'" + value.replace("'", "''") + "'"


def editorial_tables(schema: str, workflow: object | None = None) -> str:
    """Emit the editorial-workflow DDL for ``<schema>`` (migration-authoring helper).

    Three tables (``editorial_items`` / ``editorial_versions`` — write-once /
    ``editorial_events`` — append-only), ``editorial_rules()`` GENERATED from the
    Python workflow, the immutability + write-via-transition triggers, and the two
    SECURITY DEFINER entry points ``editorial_create_item`` / ``editorial_transition``
    that re-check legality + separation of duties in the DB. RLS deny-by-default
    (service-role only). Pure string emission; applying it is a migration decision.

    ``schema`` must be a plain lower-case identifier — it is interpolated into DDL.
    """
    import re

    from noctusai_lib.domain.editorial.workflow import ACTIONS, DEFAULT_WORKFLOW, STATES

    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema or ""):
        raise ValueError(f"invalid schema name {schema!r}")
    wf = workflow or DEFAULT_WORKFLOW
    lit = _sql_text_lit
    rows = ",\n".join(
        "        ("
        + ", ".join([
            lit(t.action.value), lit(t.from_state.value if t.from_state else None),
            lit(t.to_state.value), lit(t.grant.value),
            *("true" if f else "false" for f in (
                t.needs_motivo, t.not_author, t.not_editorial_approver,
                t.needs_security_signoff, t.creates_version,
            )),
        ])
        + ")"
        for t in wf.transitions
    )
    motivo_actions = sorted({t.action.value for t in wf.transitions if t.needs_motivo})
    out = _EDITORIAL_SQL
    for key, value in (
        ("__RULES__", rows),
        ("__STATES__", ", ".join(lit(s) for s in STATES)),
        ("__ACTIONS__", ", ".join(lit(a) for a in ACTIONS)),
        ("__MOTIVO_ACTIONS__", ", ".join(lit(a) for a in motivo_actions)),
        ("__GUC__", EDITORIAL_IN_TRANSITION_GUC),
        ("__S__", schema),
    ):
        out = out.replace(key, value)
    return out.strip() + "\n"
