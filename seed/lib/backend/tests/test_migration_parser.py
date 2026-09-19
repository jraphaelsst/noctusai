"""Unit tests for the migration DDL parser.

Covers the cases surfaced during `projects/mock-supabase-schema-validation`
Phase 0 discovery:

  - Schema-qualified CREATE TABLE (208 occurrences in real corpus)
  - Bare-tablename CREATE TABLE → public coercion (22 occurrences)
  - Multi-line ALTER TABLE ADD COLUMN IF NOT EXISTS with paren'd DEFAULT
  - DO-block-wrapped ALTER TABLE ADD COLUMN (erp 004_mvp_expansion.sql pattern)
  - CREATE FUNCTION body skip (120 blocks in real corpus)
  - Table-level-constraint exclusion (PRIMARY KEY / FOREIGN KEY / CONSTRAINT / …)
  - Multi-column types with nested parens (NUMERIC(10,2), CHECK (col IN ('a','b')))
  - Pass-through on unparseable shapes
"""
from __future__ import annotations

from noctusai_lib.testing.migration_parser import parse_sql


def test_schema_qualified_create_table():
    sql = """
    CREATE TABLE IF NOT EXISTS therapy.session_records (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        appointment_id UUID NOT NULL UNIQUE,
        combined_transcript_text TEXT,
        therapist_notes_private TEXT,
        total_segments INT DEFAULT 1,
        ai_generated_at TIMESTAMPTZ,
        audio_deleted_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    """
    result = parse_sql(sql)
    assert "therapy.session_records" in result
    cols = result["therapy.session_records"]
    assert cols == {
        "id",
        "appointment_id",
        "combined_transcript_text",
        "therapist_notes_private",
        "total_segments",
        "ai_generated_at",
        "audio_deleted_at",
        "created_at",
    }


def test_bare_tablename_coerces_to_public():
    sql = """
    CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL,
        org_id UUID,
        type TEXT NOT NULL DEFAULT 'system',
        title TEXT NOT NULL,
        message TEXT,
        metadata JSONB NOT NULL DEFAULT '{}',
        read BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    result = parse_sql(sql)
    assert "public.notifications" in result
    assert "user_id" in result["public.notifications"]
    assert "metadata" in result["public.notifications"]


def test_session_summary_versions_the_compliance_audit_culprit():
    """The exact table where lgpd_service filtered by nonexistent `session_id`
    and `therapist_id`. Validator must recognize the real columns."""
    sql = """
    CREATE TABLE IF NOT EXISTS therapy.session_summary_versions (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
        track TEXT NOT NULL CHECK (track IN ('base', 'clinical')),
        version_number INT NOT NULL,
        summary TEXT NOT NULL,
        key_points TEXT[],
        tags TEXT[],
        source TEXT NOT NULL DEFAULT 'ai_generated' CHECK (source IN ('ai_generated', 'ai_auto_fallback', 'manual_edit')),
        observation_snapshot_ids UUID[],
        created_at TIMESTAMPTZ DEFAULT now()
    );
    """
    result = parse_sql(sql)
    cols = result["therapy.session_summary_versions"]
    assert "session_record_id" in cols
    assert "track" in cols
    # These are the exact columns lgpd_service incorrectly assumed:
    assert "session_id" not in cols
    assert "therapist_id" not in cols


def test_multi_line_alter_add_column_with_paren_default():
    sql = """
    ALTER TABLE webhook_deliveries
        ADD COLUMN IF NOT EXISTS retention_until TIMESTAMPTZ
            DEFAULT (now() + INTERVAL '30 days');
    """
    result = parse_sql(sql)
    assert "public.webhook_deliveries" in result
    assert "retention_until" in result["public.webhook_deliveries"]


def test_alter_drop_column():
    sql = """
    CREATE TABLE erp.ativos (id UUID, nome TEXT, legacy_field TEXT);
    ALTER TABLE erp.ativos DROP COLUMN legacy_field;
    """
    result = parse_sql(sql)
    assert "legacy_field" not in result["erp.ativos"]
    assert "nome" in result["erp.ativos"]


def test_do_block_with_conditional_add_column():
    """ERP 004_mvp_expansion pattern — ALTER TABLE inside DO $$ ... $$."""
    sql = """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'erp' AND table_name = 'ativos' AND column_name = 'filial_id'
      ) THEN
        ALTER TABLE erp.ativos ADD COLUMN filial_id uuid;
      END IF;
    END $$;
    """
    result = parse_sql(sql)
    assert "erp.ativos" in result
    assert "filial_id" in result["erp.ativos"]


def test_function_body_is_skipped():
    """CREATE FUNCTION with dollar-quoted body must not leak 'column-like' symbols."""
    sql = """
    CREATE OR REPLACE FUNCTION erp.fn_example()
    RETURNS TRIGGER AS $$
    BEGIN
        -- these look like column declarations but are plpgsql variables
        DECLARE foo INTEGER;
        DECLARE bar TEXT;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TABLE erp.after_fn (
        id UUID PRIMARY KEY,
        value TEXT
    );
    """
    result = parse_sql(sql)
    # Function body did not produce a phantom table.
    assert "erp.fn_example" not in result
    # Post-function CREATE TABLE still parsed.
    assert result["erp.after_fn"] == {"id", "value"}


def test_constraint_lines_excluded():
    sql = """
    CREATE TABLE erp.demo (
        id UUID PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        org_id UUID,
        CONSTRAINT fk_org FOREIGN KEY (org_id) REFERENCES orgs(id),
        UNIQUE (email),
        CHECK (name <> '')
    );
    """
    result = parse_sql(sql)
    cols = result["erp.demo"]
    assert cols == {"id", "name", "email", "org_id"}
    # Constraint keywords must NOT appear as columns.
    assert "CONSTRAINT" not in cols
    assert "UNIQUE" not in cols
    assert "CHECK" not in cols
    assert "fk_org" not in cols


# ---------------------------------------------------------------------------
# Constraint-keyword tokenization — both spellings, every keyword
# (2026-09-18: `UNIQUE(a, b)` with no space before the paren was parsed as
# a column literally named `UNIQUE`; five real tables in the fleet corpus
# hit this shape. `\b` matches on either side of `(` exactly as it does
# before whitespace, so the fix is one regex built from the SAME
# `_CONSTRAINT_KEYWORDS` tuple the spaced form already used — every
# keyword needs the no-space case exercised, not just the one that fired.)
# ---------------------------------------------------------------------------


def test_unique_constraint_unspaced_not_parsed_as_column():
    """`social_wiring.contacts`' real shape (001_social-wiring.sql):
    `UNIQUE(org_id, email)` — no space before the paren."""
    sql = """
    CREATE TABLE social_wiring.contacts (
        id UUID PRIMARY KEY,
        org_id UUID,
        email TEXT,
        UNIQUE(org_id, email)
    );
    """
    result = parse_sql(sql)
    cols = result["social_wiring.contacts"]
    assert cols == {"id", "org_id", "email"}
    assert "UNIQUE" not in cols


def test_unique_constraint_spaced_not_parsed_as_column():
    """The other real spelling in the corpus (core's `002_missing_tables.sql`):
    `UNIQUE (org_id, key)` — a space before the paren."""
    sql = """
    CREATE TABLE core.settings (
        id UUID PRIMARY KEY,
        org_id UUID,
        key TEXT,
        UNIQUE (org_id, key)
    );
    """
    result = parse_sql(sql)
    cols = result["core.settings"]
    assert cols == {"id", "org_id", "key"}
    assert "UNIQUE" not in cols


def test_primary_key_unspaced_not_parsed_as_column():
    sql = """
    CREATE TABLE erp.demo (
        org_id UUID,
        codigo TEXT,
        PRIMARY KEY(org_id, codigo)
    );
    """
    result = parse_sql(sql)
    cols = result["erp.demo"]
    assert cols == {"org_id", "codigo"}
    assert "PRIMARY" not in cols


def test_foreign_key_unspaced_not_parsed_as_column():
    sql = """
    CREATE TABLE erp.demo (
        id UUID PRIMARY KEY,
        org_id UUID,
        FOREIGN KEY(org_id) REFERENCES orgs(id)
    );
    """
    result = parse_sql(sql)
    cols = result["erp.demo"]
    assert cols == {"id", "org_id"}
    assert "FOREIGN" not in cols


def test_check_unspaced_not_parsed_as_column():
    sql = """
    CREATE TABLE erp.demo (
        id UUID PRIMARY KEY,
        status TEXT,
        CHECK(status <> '')
    );
    """
    result = parse_sql(sql)
    cols = result["erp.demo"]
    assert cols == {"id", "status"}
    assert "CHECK" not in cols


def test_constraint_unspaced_not_parsed_as_column():
    sql = """
    CREATE TABLE erp.demo (
        id UUID PRIMARY KEY,
        org_id UUID,
        CONSTRAINT(fk_org) FOREIGN KEY (org_id) REFERENCES orgs(id)
    );
    """
    # (Not valid Postgres — CONSTRAINT always takes a bare name, never a
    # paren'd one — but the tokenizer must still not read the keyword
    # itself as a column name for ANY spelling of the boundary.)
    result = parse_sql(sql)
    cols = result["erp.demo"]
    assert cols == {"id", "org_id"}
    assert "CONSTRAINT" not in cols


def test_exclude_unspaced_not_parsed_as_column():
    """`EXCLUDE` never appears unspaced in the real corpus (it always
    takes a `USING gist (...)` clause with intervening tokens), but the
    keyword itself must never be readable as a column name."""
    sql = """
    CREATE TABLE erp.demo (
        id UUID PRIMARY KEY,
        during TSTZRANGE,
        EXCLUDE(during WITH &&)
    );
    """
    result = parse_sql(sql)
    cols = result["erp.demo"]
    assert cols == {"id", "during"}
    assert "EXCLUDE" not in cols


def test_like_unspaced_not_parsed_as_column():
    """`LIKE` never appears unspaced in the real corpus either — same
    defensive coverage as EXCLUDE above. A real column alongside the
    `LIKE(...)` clause proves the keyword text is excluded rather than
    becoming a phantom column (an all-`LIKE` body has nothing else to
    assert against)."""
    sql = """
    CREATE TABLE erp.demo_copy (
        id UUID PRIMARY KEY,
        LIKE(erp.demo)
    );
    """
    result = parse_sql(sql)
    cols = result["erp.demo_copy"]
    assert cols == {"id"}
    assert "LIKE" not in cols


def test_nested_parens_in_types_and_defaults():
    sql = """
    CREATE TABLE erp.priced (
        id UUID PRIMARY KEY,
        amount NUMERIC(10, 2) NOT NULL,
        status TEXT CHECK (status IN ('active', 'paused', 'archived')),
        computed_at TIMESTAMPTZ DEFAULT (now() AT TIME ZONE 'UTC')
    );
    """
    result = parse_sql(sql)
    cols = result["erp.priced"]
    assert cols == {"id", "amount", "status", "computed_at"}


def test_inline_comments_stripped():
    sql = """
    -- 001_example.sql — testing parser
    CREATE TABLE erp.commented (
        id UUID PRIMARY KEY,  -- primary key column
        name TEXT NOT NULL    -- display name
    );
    -- trailing comment
    """
    result = parse_sql(sql)
    assert result["erp.commented"] == {"id", "name"}


def test_unparseable_statement_is_skipped_not_raised():
    """If a weird dialect arrives, the parser logs a warning and skips the
    offending table — it does not crash the whole test session."""
    sql = """
    -- This statement is intentionally weird: the CREATE TABLE has no closing paren.
    CREATE TABLE erp.broken (
        id UUID PRIMARY KEY,
        -- oops, never closes

    CREATE TABLE erp.recovers (
        id UUID PRIMARY KEY,
        value TEXT
    );
    """
    # Must not raise. The recoverable table still parses because
    # our statement walker only advances past `;` at paren-depth 0,
    # so the unclosed broken table swallows the recovers one. Either
    # outcome is acceptable — the critical invariant is "does not crash".
    result = parse_sql(sql)
    assert isinstance(result, dict)


def test_alter_add_column_preserves_existing_table_columns():
    sql = """
    CREATE TABLE erp.contas (
        id UUID PRIMARY KEY,
        nome TEXT
    );

    ALTER TABLE erp.contas
        ADD COLUMN IF NOT EXISTS saldo NUMERIC(10, 2) DEFAULT 0;

    ALTER TABLE erp.contas
        ADD COLUMN ativo BOOLEAN DEFAULT true;
    """
    result = parse_sql(sql)
    assert result["erp.contas"] == {"id", "nome", "saldo", "ativo"}


def test_empty_sql_returns_empty_map():
    assert parse_sql("") == {}
    assert parse_sql("-- just a comment") == {}


def test_string_literal_with_semicolon_does_not_break_statement_split():
    sql = """
    CREATE TABLE erp.settings (
        id UUID PRIMARY KEY,
        greeting TEXT DEFAULT 'hello; world'
    );

    CREATE TABLE erp.after_string (
        id UUID PRIMARY KEY,
        value TEXT
    );
    """
    result = parse_sql(sql)
    assert result["erp.settings"] == {"id", "greeting"}
    assert result["erp.after_string"] == {"id", "value"}


def test_case_insensitive_keywords():
    sql = """
    create table lowercase.foo (
        id uuid primary key,
        name text
    );
    alter table lowercase.foo add column extra int;
    """
    result = parse_sql(sql)
    assert "lowercase.foo" in result
    assert result["lowercase.foo"] == {"id", "name", "extra"}


# -- multi-clause ALTER TABLE ------------------------------------------------


def test_alter_table_registers_every_add_column_not_just_the_first():
    """A single ALTER may carry many ADD COLUMN clauses, and ~20 fleet
    migrations do. The previous combined regex captured only the first:
    `finditer` resumed past the match and then needed another ALTER TABLE
    head that was not there, so every later column was silently missing
    from the mock schema registry."""
    sql = """
    ALTER TABLE social_wiring.leads
        ADD COLUMN IF NOT EXISTS external_source  TEXT,
        ADD COLUMN IF NOT EXISTS external_lead_id TEXT;
    """

    schema_map = parse_sql(sql)

    assert schema_map["social_wiring.leads"] == {"external_source", "external_lead_id"}


def test_alter_table_registers_three_or_more_columns():
    sql = """
    ALTER TABLE erp.clientes
      ADD COLUMN IF NOT EXISTS lead_score INTEGER CHECK (lead_score >= 0),
      ADD COLUMN IF NOT EXISTS lead_score_justificativa TEXT,
      ADD COLUMN IF NOT EXISTS lead_score_atualizado_em TIMESTAMPTZ;
    """

    assert parse_sql(sql)["erp.clientes"] == {
        "lead_score", "lead_score_justificativa", "lead_score_atualizado_em",
    }


def test_two_alter_statements_do_not_bleed_into_each_other():
    """Clause attribution is per-head: a body runs only to the NEXT ALTER
    head, so a second table's columns never land on the first."""
    sql = """
    ALTER TABLE app.first ADD COLUMN a TEXT;
    ALTER TABLE app.second ADD COLUMN b TEXT, ADD COLUMN c TEXT;
    """

    schema_map = parse_sql(sql)

    assert schema_map["app.first"] == {"a"}
    assert schema_map["app.second"] == {"b", "c"}


def test_multi_clause_drop_column_removes_every_named_column():
    sql = """
    CREATE TABLE app.t (id UUID, a TEXT, b TEXT, c TEXT);
    ALTER TABLE app.t
        DROP COLUMN IF EXISTS a,
        DROP COLUMN IF EXISTS b;
    """

    assert parse_sql(sql)["app.t"] == {"id", "c"}


def test_add_and_drop_in_one_statement_are_both_applied():
    sql = """
    CREATE TABLE app.t (id UUID, old TEXT);
    ALTER TABLE app.t ADD COLUMN new TEXT, DROP COLUMN old;
    """

    assert parse_sql(sql)["app.t"] == {"id", "new"}


class TestRename:
    """`ALTER TABLE ... RENAME` — unsupported until migration 060
    (social-wiring `negociacoes_venda` -> `atendimentos`) needed it.

    The gap was not neutral. An unhandled table rename left the NEW name
    absent from the schema map, which silently disables validation for that
    table, while the OLD column name survived on the other side — so an
    honest query against the new column failed with "table has no column X"
    naming a column the migration plainly creates. One rename produced a
    false failure and a silent hole simultaneously.
    """

    def test_table_rename_carries_its_columns(self):
        schema = parse_sql(
            """
            CREATE TABLE social_wiring.negociacoes_venda (
                id UUID PRIMARY KEY,
                org_id UUID NOT NULL,
                titulo TEXT
            );
            ALTER TABLE social_wiring.negociacoes_venda RENAME TO atendimentos;
            """
        )
        assert "social_wiring.atendimentos" in schema
        assert "social_wiring.negociacoes_venda" not in schema, (
            "the old name must not linger — a query against it should fail"
        )
        assert {"id", "org_id", "titulo"} <= schema["social_wiring.atendimentos"]

    def test_column_rename_swaps_old_for_new(self):
        schema = parse_sql(
            """
            CREATE TABLE social_wiring.processos_venda (
                id UUID PRIMARY KEY,
                negociacao_venda_id UUID NOT NULL
            );
            ALTER TABLE social_wiring.processos_venda
                RENAME COLUMN negociacao_venda_id TO atendimento_id;
            """
        )
        cols = schema["social_wiring.processos_venda"]
        assert "atendimento_id" in cols
        assert "negociacao_venda_id" not in cols

    def test_rename_inside_a_do_block_is_seen(self):
        """Renames are guarded by DO blocks for idempotency — Postgres has
        no `RENAME COLUMN IF EXISTS`. The walker treats DO as atomic, so the
        clause must still be found inside the body."""
        schema = parse_sql(
            """
            CREATE TABLE social_wiring.processos_venda (
                id UUID PRIMARY KEY,
                negociacao_venda_id UUID NOT NULL
            );
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM information_schema.columns
                         WHERE table_name='processos_venda'
                           AND column_name='negociacao_venda_id') THEN
                ALTER TABLE social_wiring.processos_venda
                  RENAME COLUMN negociacao_venda_id TO atendimento_id;
              END IF;
            END $$;
            """
        )
        cols = schema["social_wiring.processos_venda"]
        assert "atendimento_id" in cols
        assert "negociacao_venda_id" not in cols

    def test_add_column_after_a_rename_lands_on_the_new_table(self):
        schema = parse_sql(
            """
            CREATE TABLE social_wiring.old_name (id UUID PRIMARY KEY);
            ALTER TABLE social_wiring.old_name RENAME TO new_name;
            ALTER TABLE social_wiring.new_name ADD COLUMN IF NOT EXISTS extra_col TEXT;
            """
        )
        assert schema["social_wiring.new_name"] == {"id", "extra_col"}
        assert "social_wiring.old_name" not in schema

    def test_rename_if_exists_is_handled(self):
        schema = parse_sql(
            """
            CREATE TABLE social_wiring.a (id UUID PRIMARY KEY);
            ALTER TABLE IF EXISTS social_wiring.a RENAME TO b;
            """
        )
        assert "social_wiring.b" in schema


# ---------------------------------------------------------------------------
# Dynamic DDL blind spots (2026-09-18) — a table identifier resolved at
# runtime via `EXECUTE format('...%I...', t)` cannot be seen by a regex
# parser; the fix is not to pretend it can, but to STOP staying silent
# about it. Real shape: `social-wiring`'s `046_clients_to_marcas.sql`, six
# tables' `client_id` renamed to `marca_id` inside a `FOREACH t IN ARRAY
# [...] LOOP EXECUTE format('ALTER TABLE social_wiring.%I RENAME COLUMN
# client_id TO marca_id', t)`.
# ---------------------------------------------------------------------------


def test_dynamic_rename_column_is_a_named_blind_spot_not_a_phantom_column():
    sql = """
    DO $$
    DECLARE
      t TEXT;
    BEGIN
      FOREACH t IN ARRAY ARRAY['integration_accounts', 'whatsapp_connections']
      LOOP
        EXECUTE format('ALTER TABLE social_wiring.%I RENAME COLUMN client_id TO marca_id', t);
      END LOOP;
    END
    $$;
    """
    blind: list[dict] = []
    schema = parse_sql(sql, source_label="046_clients_to_marcas.sql", blind_spots=blind)
    # No table was fabricated for either name — the parser never guesses.
    assert "social_wiring.integration_accounts" not in schema
    assert "social_wiring.whatsapp_connections" not in schema
    assert len(blind) == 1
    spot = blind[0]
    assert spot["class"] == "rename_column"
    assert spot["old_column"] == "client_id"
    assert spot["new_column"] == "marca_id"
    assert spot["file"] == "046_clients_to_marcas.sql"


def test_dynamic_add_column_is_a_named_blind_spot():
    sql = """
    DO $$
    BEGIN
      EXECUTE format('ALTER TABLE erp.%I ADD COLUMN IF NOT EXISTS marca_id UUID', 'foo');
    END
    $$;
    """
    blind: list[dict] = []
    parse_sql(sql, source_label="099_dynamic_add.sql", blind_spots=blind)
    assert len(blind) == 1
    assert blind[0]["class"] == "add_column"
    assert blind[0]["column"] == "marca_id"
    assert blind[0]["file"] == "099_dynamic_add.sql"


def test_dynamic_drop_column_is_a_named_blind_spot():
    sql = """
    DO $$
    BEGIN
      EXECUTE format('ALTER TABLE erp.%I DROP COLUMN legacy_flag', 'foo');
    END
    $$;
    """
    blind: list[dict] = []
    parse_sql(sql, source_label="099_dynamic_drop.sql", blind_spots=blind)
    assert len(blind) == 1
    assert blind[0]["class"] == "drop_column"
    assert blind[0]["column"] == "legacy_flag"


def test_dynamic_add_column_does_not_fabricate_a_phantom_schema_table():
    """Found while building the blind-spot detector, not in the original
    diagnosis: `_ALTER_TABLE_HEAD_RE` used to backtrack on `erp.%I` (the
    dynamic table placeholder isn't a valid `_IDENT`) and bind `table` to
    the SCHEMA name instead — `_alter_table_segments` then ran the static
    ADD-COLUMN scan against that bogus head and fabricated a phantom table
    `public.erp` holding the dynamic clause's column. RENAME COLUMN never
    hit this because its mutation is gated on `existing is not None`; ADD
    COLUMN has no such gate. No corpus migration currently uses dynamic
    ADD/DROP COLUMN, so this never fired live — but the same class of
    statement this slice's blind-spot detector now exists FOR must not
    also corrupt the static schema map."""
    sql = """
    DO $$
    BEGIN
      EXECUTE format('ALTER TABLE erp.%I ADD COLUMN IF NOT EXISTS x TEXT', 'foo');
    END
    $$;
    """
    schema = parse_sql(sql)
    assert schema == {}
    assert "public.erp" not in schema


def test_dynamic_ddl_blind_spots_default_off_is_a_pure_noop():
    """Omitting `blind_spots` (every pre-existing caller, incl.
    `MockSupabaseClient`) must not change parse behaviour at all."""
    sql = """
    DO $$
    BEGIN
      EXECUTE format('ALTER TABLE erp.%I ADD COLUMN IF NOT EXISTS x TEXT', 'foo');
    END
    $$;
    """
    # No blind_spots kwarg passed — must not raise, must not populate
    # anything the caller can't ask for.
    schema = parse_sql(sql)
    assert schema == {}


def test_dynamic_policy_and_index_renames_are_not_blind_spots():
    """RLS-policy / index / constraint-NAME-only dynamic EXECUTEs are out
    of this parser's scope already (it never tracked those) — they must
    not become noise in the blind-spot list. Real shape: the OTHER three
    dynamic statements in `046_clients_to_marcas.sql` (constraint rename,
    index rename, policy rename) that sit right next to the one genuine
    column-rename blind spot."""
    sql = """
    DO $$
    DECLARE r RECORD;
    BEGIN
      FOR r IN SELECT 1
      LOOP
        EXECUTE format('ALTER TABLE %s RENAME CONSTRAINT %I TO %I', 'x', 'a', 'b');
      END LOOP;
    END
    $$;
    DO $$
    DECLARE r RECORD;
    BEGIN
      FOR r IN SELECT 1
      LOOP
        EXECUTE format('ALTER INDEX social_wiring.%I RENAME TO %I', 'a', 'b');
      END LOOP;
    END
    $$;
    DO $$
    DECLARE r RECORD;
    BEGIN
      FOR r IN SELECT 1
      LOOP
        EXECUTE format('ALTER POLICY %I ON social_wiring.marcas RENAME TO %I', 'a', 'b');
      END LOOP;
    END
    $$;
    """
    blind: list[dict] = []
    parse_sql(sql, blind_spots=blind)
    assert blind == []


def test_dynamic_rls_enable_is_not_a_blind_spot():
    """The overwhelming majority of the corpus's dynamic EXECUTEs are
    `ENABLE ROW LEVEL SECURITY` / `DROP POLICY` loops over every table in a
    schema (erp/igig/social-wiring/core all do this) — these must stay
    silent, not flood the blind-spot list with noise on every migration
    run."""
    sql = """
    DO $$
    DECLARE tbl TEXT;
    BEGIN
      FOR tbl IN SELECT table_name FROM information_schema.tables
      LOOP
        EXECUTE format('ALTER TABLE erp.%I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I ON erp.%I', tbl || '_select_policy', tbl);
      END LOOP;
    END
    $$;
    """
    blind: list[dict] = []
    parse_sql(sql, blind_spots=blind)
    assert blind == []
