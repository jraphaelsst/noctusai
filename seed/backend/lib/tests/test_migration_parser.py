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
