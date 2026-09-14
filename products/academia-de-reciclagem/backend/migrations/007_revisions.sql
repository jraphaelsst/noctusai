-- ============================================================================
-- Migration 007 — kb_revisions (A.10), approval_consumptions, and the
-- write-path RPC functions PgKnowledgeStore calls.
--
-- WHY THE WRITE PATHS ARE POSTGRES FUNCTIONS, NOT APP-LAYER MULTI-CALLS
-- -----------------------------------------------------------------------
-- The platform's DB access is exclusively PostgREST (see
-- `noctusai_seed.database.DatabaseModule` — no asyncpg/psycopg anywhere in
-- the codebase). Every `.table(...).execute()` call is its OWN Postgres
-- transaction; there is no client-side way to span two PostgREST calls in
-- one transaction. The contract's invariant ("every write to A.1–A.8
-- inserts exactly one kb_revisions row in the SAME transaction... a write
-- without one is a bug") is therefore only honestly achievable by putting
-- the entity write AND the revision insert in ONE Postgres function,
-- invoked as ONE `.rpc()` call — exactly the pattern this schema already
-- uses for `try_acquire_sync_lease` (social_wiring/070_sync_leases.sql).
-- `app/knowledge/pg.py` calls these; `app/knowledge/fake.py` mirrors the
-- same invariants in Python for the (DB-less) test suite.
--
-- SECURITY: every function below is SECURITY DEFINER and does its OWN
-- org_id filtering — none of them trust RLS. PostgREST auto-exposes every
-- function in an exposed schema as `/rpc/<name>`, so at the end of this
-- file EXECUTE is revoked from PUBLIC/anon/authenticated and granted only
-- to service_role — these are backend-internal RPCs, never a direct
-- browser/product-token surface.
--
-- Custom SQLSTATE convention used by RAISE EXCEPTION below (pg.py maps
-- these onto app/knowledge/errors.py):
--   NA404 -> NotFound   NA409 -> Conflict   NA422 -> Invalid
--   NA001 -> AssertionUsed   (plus the standard 23505 unique_violation,
--   which also maps to Conflict — e.g. a slug/codigo collision).
--
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = academia_de_reciclagem, public;

-- ============================================================================
-- A.10 kb_revisions — append-only history for every entity in 006.
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.kb_revisions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL,
    entity_type        TEXT NOT NULL CHECK (entity_type IN (
                            'kb_entry', 'decision', 'open_question', 'roadmap_phase',
                            'task', 'content_draft', 'timeline_event', 'research_source'
                        )),
    entity_id          UUID NOT NULL,
    rev_no             INT NOT NULL,
    op                 TEXT NOT NULL CHECK (op IN ('create', 'update', 'archive', 'supersede', 'import')),
    snapshot           JSONB NOT NULL,
    author_kind        TEXT NOT NULL CHECK (author_kind IN ('human', 'agent', 'import')),
    user_id            UUID,
    agent_id           UUID,
    approval_id        UUID,
    channel            TEXT,
    conversation_id    UUID,
    motivo             TEXT,
    git_sha            TEXT,
    git_author_raw     TEXT,
    git_committed_at   TIMESTAMPTZ,
    git_message        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT kb_revisions_entity_rev_unique UNIQUE (entity_type, entity_id, rev_no)
);

-- One approved call may legitimately write several revisions (a supersede
-- writes two — the new decision and the old one), so this is NOT a plain
-- unique-on-approval_id; it is scoped to (entity_type, entity_id) too, and
-- only enforced when approval_id is actually set.
CREATE UNIQUE INDEX IF NOT EXISTS kb_revisions_approval_entity_unique
    ON academia_de_reciclagem.kb_revisions (approval_id, entity_type, entity_id)
    WHERE approval_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_kb_revisions_org ON academia_de_reciclagem.kb_revisions(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_kb_revisions_import_dedup
    ON academia_de_reciclagem.kb_revisions(entity_type, entity_id, op, git_sha)
    WHERE op = 'import';

ALTER TABLE academia_de_reciclagem.kb_revisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "kb_revisions_select_own_org" ON academia_de_reciclagem.kb_revisions;
CREATE POLICY "kb_revisions_select_own_org" ON academia_de_reciclagem.kb_revisions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.kb_revisions;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.kb_revisions FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Append-only, belt AND suspenders: the GRANT-level revoke is the primary
-- enforcement (it applies even to a role that would otherwise pass RLS via
-- `service_role_bypass`'s FOR ALL); the trigger is defence in depth for a
-- future role this revoke list doesn't yet name.
REVOKE UPDATE, DELETE ON academia_de_reciclagem.kb_revisions FROM anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.kb_revisions_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
BEGIN
    RAISE EXCEPTION 'kb_revisions is append-only: % is not permitted (id=%)', TG_OP, OLD.id
        USING ERRCODE = '0A000';
END;
$$;

CREATE OR REPLACE TRIGGER kb_revisions_immutable_trg
    BEFORE UPDATE OR DELETE ON academia_de_reciclagem.kb_revisions
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.kb_revisions_immutable();

-- Attach the FK that 006 could not (kb_revisions didn't exist yet).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'kb_entries_current_revision_id_fkey'
    ) THEN
        ALTER TABLE academia_de_reciclagem.kb_entries
            ADD CONSTRAINT kb_entries_current_revision_id_fkey
            FOREIGN KEY (current_revision_id) REFERENCES academia_de_reciclagem.kb_revisions (id);
    END IF;
END;
$$;


-- ============================================================================
-- approval_consumptions — the single-use replay guard for X-Approval-Assertion
-- (contract §A.10 note, §D). Its INSERT happens first, inside the SAME
-- transaction as the write(s) it authorizes; a duplicate jti is a 23505
-- unique_violation on the PK, translated by `_consume_approval` below into
-- the custom 'NA001' (assertion_used) so the caller gets a clean 409, not a
-- raw constraint-violation leak.
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.approval_consumptions (
    jti          UUID PRIMARY KEY,
    org_id       UUID NOT NULL,
    consumed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE academia_de_reciclagem.approval_consumptions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "approval_consumptions_select_own_org" ON academia_de_reciclagem.approval_consumptions;
CREATE POLICY "approval_consumptions_select_own_org" ON academia_de_reciclagem.approval_consumptions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.approval_consumptions;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.approval_consumptions FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- Helpers shared by every write-path function below.
-- ============================================================================

-- _consume_approval — the single-use guard. A no-op when p_approval_id is
-- NULL (a human/SSO write, or a human_personal product token per §B.0,
-- needs no assertion at all). Called EXACTLY ONCE per store-level write
-- call (not once per revision row) — a supersede writes two revisions from
-- one consumed approval, per the A.10 note.
CREATE OR REPLACE FUNCTION academia_de_reciclagem._consume_approval(
    p_org_id UUID,
    p_approval_id UUID
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
BEGIN
    IF p_approval_id IS NULL THEN
        RETURN;
    END IF;
    BEGIN
        INSERT INTO academia_de_reciclagem.approval_consumptions (jti, org_id)
        VALUES (p_approval_id, p_org_id);
    EXCEPTION WHEN unique_violation THEN
        RAISE EXCEPTION 'assertion_used: approval % already consumed', p_approval_id
            USING ERRCODE = 'NA001';
    END;
END;
$$;

-- _allocate_code — atomic `UPDATE ... SET ultimo = ultimo + 1 RETURNING`,
-- expressed as an INSERT ... ON CONFLICT DO UPDATE so the first allocation
-- for a (org_id, prefix) pair doesn't need a separate seed row (mirrors
-- `try_acquire_sync_lease`'s single-statement atomic upsert).
CREATE OR REPLACE FUNCTION academia_de_reciclagem._allocate_code(
    p_org_id UUID,
    p_prefix TEXT,
    p_width INT
) RETURNS TEXT
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_next INT;
BEGIN
    INSERT INTO academia_de_reciclagem.code_counters (org_id, prefix, ultimo)
    VALUES (p_org_id, p_prefix, 1)
    ON CONFLICT (org_id, prefix) DO UPDATE
       SET ultimo = academia_de_reciclagem.code_counters.ultimo + 1
    RETURNING ultimo INTO v_next;

    RETURN p_prefix || '-' || lpad(v_next::text, p_width, '0');
END;
$$;

-- _append_revision — inserts exactly one kb_revisions row and returns it as
-- jsonb. `p_id` lets a caller pre-generate the revision id (kb_entries
-- needs it to set `current_revision_id` in the SAME INSERT as the entity
-- row, avoiding a self-referential chicken/egg update).
--
-- NOC-REMEDIATE[concurrent-rev-no-race]: `rev_no` is a read-then-write
-- (MAX+1), not a locking read. The UNIQUE (entity_type, entity_id, rev_no)
-- constraint turns a race into a 23505 on the loser rather than a silently
-- wrong rev_no, but there is no retry here. This product's access pattern
-- (one admin UI, one agent control plane, both gated by the approval flow)
-- does not exercise concurrent writers on the SAME entity today; hardening
-- to `SELECT ... FOR UPDATE` on a per-entity lock row is deferred until
-- observed. — 2026-09-14
CREATE OR REPLACE FUNCTION academia_de_reciclagem._append_revision(
    p_org_id UUID,
    p_entity_type TEXT,
    p_entity_id UUID,
    p_op TEXT,
    p_snapshot JSONB,
    p_prov JSONB,
    p_id UUID DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_id UUID := COALESCE(p_id, gen_random_uuid());
    v_rev_no INT;
    v_row academia_de_reciclagem.kb_revisions;
BEGIN
    SELECT COALESCE(MAX(rev_no), 0) + 1 INTO v_rev_no
      FROM academia_de_reciclagem.kb_revisions
     WHERE entity_type = p_entity_type AND entity_id = p_entity_id;

    INSERT INTO academia_de_reciclagem.kb_revisions (
        id, org_id, entity_type, entity_id, rev_no, op, snapshot,
        author_kind, user_id, agent_id, approval_id, channel, conversation_id,
        motivo, git_sha, git_author_raw, git_committed_at, git_message
    ) VALUES (
        v_id, p_org_id, p_entity_type, p_entity_id, v_rev_no, p_op, p_snapshot,
        p_prov->>'author_kind',
        (p_prov->>'user_id')::uuid,
        (p_prov->>'agent_id')::uuid,
        (p_prov->>'approval_id')::uuid,
        p_prov->>'channel',
        (p_prov->>'conversation_id')::uuid,
        p_prov->>'motivo',
        p_prov->>'git_sha',
        p_prov->>'git_author_raw',
        (p_prov->>'git_committed_at')::timestamptz,
        p_prov->>'git_message'
    )
    RETURNING * INTO v_row;

    RETURN to_jsonb(v_row);
END;
$$;


-- ============================================================================
-- kb_entries write paths
-- ============================================================================

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_kb_entry(
    p_org_id UUID,
    p_slug TEXT,
    p_categoria TEXT,
    p_subcategoria TEXT,
    p_titulo TEXT,
    p_resumo TEXT,
    p_tags TEXT[],
    p_corpo_md TEXT,
    p_frontmatter JSONB,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_rev_id UUID := gen_random_uuid();
    v_row academia_de_reciclagem.kb_entries;
BEGIN
    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    INSERT INTO academia_de_reciclagem.kb_entries (
        org_id, slug, categoria, subcategoria, titulo, resumo, tags,
        corpo_md, frontmatter, current_revision_id
    ) VALUES (
        p_org_id, p_slug, p_categoria, p_subcategoria, p_titulo, p_resumo,
        COALESCE(p_tags, '{}'), p_corpo_md, COALESCE(p_frontmatter, '{}'::jsonb), v_rev_id
    )
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'kb_entry', v_row.id, 'create', to_jsonb(v_row), p_prov, v_rev_id
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.update_kb_entry(
    p_org_id UUID,
    p_slug TEXT,
    p_changes JSONB,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.kb_entries;
    v_new_slug TEXT;
    v_rev_id UUID := gen_random_uuid();
BEGIN
    SELECT * INTO v_row FROM academia_de_reciclagem.kb_entries
     WHERE org_id = p_org_id AND slug = p_slug;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'kb_entry not found: %', p_slug USING ERRCODE = 'NA404';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    v_new_slug := COALESCE(p_changes->>'novo_slug', v_row.slug);

    UPDATE academia_de_reciclagem.kb_entries SET
        slug          = v_new_slug,
        titulo        = COALESCE(p_changes->>'titulo', titulo),
        resumo        = COALESCE(p_changes->>'resumo', resumo),
        tags          = CASE WHEN p_changes ? 'tags'
                              THEN COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_changes->'tags') x), '{}')
                              ELSE tags END,
        corpo_md      = COALESCE(p_changes->>'corpo_md', corpo_md),
        categoria     = COALESCE(p_changes->>'categoria', categoria),
        subcategoria  = COALESCE(p_changes->>'subcategoria', subcategoria),
        current_revision_id = v_rev_id
     WHERE id = v_row.id
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'kb_entry', v_row.id, 'update', to_jsonb(v_row), p_prov, v_rev_id
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.archive_kb_entry(
    p_org_id UUID,
    p_slug TEXT,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.kb_entries;
    v_rev_id UUID := gen_random_uuid();
BEGIN
    SELECT * INTO v_row FROM academia_de_reciclagem.kb_entries
     WHERE org_id = p_org_id AND slug = p_slug;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'kb_entry not found: %', p_slug USING ERRCODE = 'NA404';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    UPDATE academia_de_reciclagem.kb_entries
       SET arquivado = true, current_revision_id = v_rev_id
     WHERE id = v_row.id
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'kb_entry', v_row.id, 'archive', to_jsonb(v_row), p_prov, v_rev_id
    );

    RETURN to_jsonb(v_row);
END;
$$;


-- ============================================================================
-- decisions write paths
-- ============================================================================

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_decision(
    p_org_id UUID,
    p_titulo TEXT,
    p_contexto TEXT,
    p_decisao TEXT,
    p_motivo TEXT,
    p_alternativas_rejeitadas TEXT,
    p_relacionadas TEXT[],
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_codigo TEXT;
    v_row academia_de_reciclagem.decisions;
BEGIN
    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    v_codigo := academia_de_reciclagem._allocate_code(p_org_id, 'D', 2);

    INSERT INTO academia_de_reciclagem.decisions (
        org_id, codigo, titulo, contexto, decisao, motivo,
        alternativas_rejeitadas, data, estado, relacionadas
    ) VALUES (
        p_org_id, v_codigo, p_titulo, p_contexto, p_decisao, p_motivo,
        p_alternativas_rejeitadas, current_date, 'vigente', COALESCE(p_relacionadas, '{}')
    )
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'decision', v_row.id, 'create', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.supersede_decision(
    p_org_id UUID,
    p_codigo TEXT,
    p_titulo TEXT,
    p_contexto TEXT,
    p_decisao TEXT,
    p_motivo TEXT,
    p_alternativas_rejeitadas TEXT,
    p_relacionadas TEXT[],
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_old academia_de_reciclagem.decisions;
    v_new academia_de_reciclagem.decisions;
    v_new_codigo TEXT;
BEGIN
    SELECT * INTO v_old FROM academia_de_reciclagem.decisions
     WHERE org_id = p_org_id AND codigo = p_codigo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'decision not found: %', p_codigo USING ERRCODE = 'NA404';
    END IF;
    IF v_old.estado = 'superseded' THEN
        RAISE EXCEPTION 'decision already superseded: %', p_codigo USING ERRCODE = 'NA409';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    v_new_codigo := academia_de_reciclagem._allocate_code(p_org_id, 'D', 2);

    INSERT INTO academia_de_reciclagem.decisions (
        org_id, codigo, titulo, contexto, decisao, motivo,
        alternativas_rejeitadas, data, estado, substitui, relacionadas
    ) VALUES (
        p_org_id, v_new_codigo, p_titulo, p_contexto, p_decisao, p_motivo,
        p_alternativas_rejeitadas, current_date, 'vigente', p_codigo, COALESCE(p_relacionadas, '{}')
    )
    RETURNING * INTO v_new;

    -- The append-only trigger permits exactly this: estado + superseded_by.
    UPDATE academia_de_reciclagem.decisions
       SET estado = 'superseded', superseded_by = v_new_codigo
     WHERE id = v_old.id
    RETURNING * INTO v_old;

    -- Both revisions carry op='supersede' — two effects of the SAME
    -- approved act (already consumed once above), not an independent
    -- create + update.
    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'decision', v_new.id, 'supersede', to_jsonb(v_new), p_prov
    );
    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'decision', v_old.id, 'supersede', to_jsonb(v_old), p_prov
    );

    RETURN jsonb_build_object('nova', to_jsonb(v_new), 'substituida', to_jsonb(v_old));
END;
$$;


-- ============================================================================
-- open_questions write paths
-- ============================================================================

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_open_question(
    p_org_id UUID,
    p_pergunta TEXT,
    p_por_que_importa TEXT,
    p_bloqueia TEXT,
    p_destino_kb TEXT,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_codigo TEXT;
    v_row academia_de_reciclagem.open_questions;
BEGIN
    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    v_codigo := academia_de_reciclagem._allocate_code(p_org_id, 'Q', 2);

    INSERT INTO academia_de_reciclagem.open_questions (
        org_id, codigo, pergunta, por_que_importa, bloqueia, destino_kb, estado
    ) VALUES (
        p_org_id, v_codigo, p_pergunta, p_por_que_importa, p_bloqueia, p_destino_kb, 'aberta'
    )
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'open_question', v_row.id, 'create', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.answer_open_question(
    p_org_id UUID,
    p_codigo TEXT,
    p_resposta TEXT,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.open_questions;
BEGIN
    SELECT * INTO v_row FROM academia_de_reciclagem.open_questions
     WHERE org_id = p_org_id AND codigo = p_codigo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'open_question not found: %', p_codigo USING ERRCODE = 'NA404';
    END IF;
    IF v_row.estado = 'respondida' THEN
        RAISE EXCEPTION 'open_question already answered: %', p_codigo USING ERRCODE = 'NA409';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    UPDATE academia_de_reciclagem.open_questions
       SET resposta = p_resposta, estado = 'respondida', respondida_em = now()
     WHERE id = v_row.id
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'open_question', v_row.id, 'update', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;


-- ============================================================================
-- roadmap_phases / tasks write paths
-- ============================================================================

CREATE OR REPLACE FUNCTION academia_de_reciclagem.update_roadmap_phase(
    p_org_id UUID,
    p_codigo TEXT,
    p_changes JSONB,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.roadmap_phases;
BEGIN
    SELECT * INTO v_row FROM academia_de_reciclagem.roadmap_phases
     WHERE org_id = p_org_id AND codigo = p_codigo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'roadmap_phase not found: %', p_codigo USING ERRCODE = 'NA404';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    UPDATE academia_de_reciclagem.roadmap_phases SET
        estado           = COALESCE(p_changes->>'estado', estado),
        titulo           = COALESCE(p_changes->>'titulo', titulo),
        objetivo         = COALESCE(p_changes->>'objetivo', objetivo),
        concluida_quando = COALESCE(p_changes->>'concluida_quando', concluida_quando)
     WHERE id = v_row.id
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'roadmap_phase', v_row.id, 'update', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_task(
    p_org_id UUID,
    p_titulo TEXT,
    p_fase TEXT,
    p_detalhe TEXT,
    p_bloqueada_por TEXT,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_codigo TEXT;
    v_row academia_de_reciclagem.tasks;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM academia_de_reciclagem.roadmap_phases
         WHERE org_id = p_org_id AND codigo = p_fase
    ) THEN
        RAISE EXCEPTION 'unknown fase: %', p_fase USING ERRCODE = 'NA422';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    v_codigo := academia_de_reciclagem._allocate_code(p_org_id, 'T', 3);

    INSERT INTO academia_de_reciclagem.tasks (
        org_id, codigo, titulo, fase, detalhe, estado, bloqueada_por
    ) VALUES (
        p_org_id, v_codigo, p_titulo, p_fase, p_detalhe, 'pendente', p_bloqueada_por
    )
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'task', v_row.id, 'create', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.update_task(
    p_org_id UUID,
    p_codigo TEXT,
    p_changes JSONB,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.tasks;
BEGIN
    SELECT * INTO v_row FROM academia_de_reciclagem.tasks
     WHERE org_id = p_org_id AND codigo = p_codigo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task not found: %', p_codigo USING ERRCODE = 'NA404';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    UPDATE academia_de_reciclagem.tasks SET
        estado        = COALESCE(p_changes->>'estado', estado),
        detalhe       = COALESCE(p_changes->>'detalhe', detalhe),
        bloqueada_por = COALESCE(p_changes->>'bloqueada_por', bloqueada_por)
     WHERE id = v_row.id
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'task', v_row.id, 'update', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;


-- ============================================================================
-- content_drafts / timeline_events / research_sources write paths
-- ============================================================================

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_content_draft(
    p_org_id UUID,
    p_tipo TEXT,
    p_titulo TEXT,
    p_corpo_md TEXT,
    p_referencia TEXT,
    p_fontes TEXT[],
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_codigo TEXT;
    v_row academia_de_reciclagem.content_drafts;
BEGIN
    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    v_codigo := academia_de_reciclagem._allocate_code(p_org_id, 'C', 3);

    INSERT INTO academia_de_reciclagem.content_drafts (
        org_id, codigo, tipo, titulo, corpo_md, referencia, fontes
    ) VALUES (
        p_org_id, v_codigo, p_tipo, p_titulo, p_corpo_md, p_referencia, COALESCE(p_fontes, '{}')
    )
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'content_draft', v_row.id, 'create', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_timeline_event(
    p_org_id UUID,
    p_data DATE,
    p_titulo TEXT,
    p_descricao TEXT,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.timeline_events;
BEGIN
    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    INSERT INTO academia_de_reciclagem.timeline_events (org_id, data, titulo, descricao)
    VALUES (p_org_id, COALESCE(p_data, current_date), p_titulo, p_descricao)
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'timeline_event', v_row.id, 'create', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;

CREATE OR REPLACE FUNCTION academia_de_reciclagem.create_research_source(
    p_org_id UUID,
    p_url TEXT,
    p_titulo TEXT,
    p_trecho_citado TEXT,
    p_resumo TEXT,
    p_kb_slug TEXT,
    p_vigencia_confirmada BOOLEAN,
    p_exige_da_empresa TEXT,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_row academia_de_reciclagem.research_sources;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM academia_de_reciclagem.kb_entries
         WHERE org_id = p_org_id AND slug = p_kb_slug
    ) THEN
        RAISE EXCEPTION 'kb_slug not found: %', p_kb_slug USING ERRCODE = 'NA404';
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    INSERT INTO academia_de_reciclagem.research_sources (
        org_id, url, titulo, trecho_citado, resumo, kb_slug,
        vigencia_confirmada, exige_da_empresa, accessed_at
    ) VALUES (
        p_org_id, p_url, p_titulo, p_trecho_citado, p_resumo, p_kb_slug,
        COALESCE(p_vigencia_confirmada, false), p_exige_da_empresa, now()
    )
    RETURNING * INTO v_row;

    PERFORM academia_de_reciclagem._append_revision(
        p_org_id, 'research_source', v_row.id, 'create', to_jsonb(v_row), p_prov
    );

    RETURN to_jsonb(v_row);
END;
$$;


-- ============================================================================
-- Import (A2 depends on these two)
-- ============================================================================

-- seed_counters — bookkeeping only, never revisioned (A.9 counters aren't
-- one of A.1–A.8's user-content entities).
CREATE OR REPLACE FUNCTION academia_de_reciclagem.seed_counters(
    p_org_id UUID,
    p_counters JSONB
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_prefix TEXT;
    v_value_text TEXT;
BEGIN
    FOR v_prefix, v_value_text IN SELECT key, value FROM jsonb_each_text(p_counters)
    LOOP
        INSERT INTO academia_de_reciclagem.code_counters (org_id, prefix, ultimo)
        VALUES (p_org_id, v_prefix, v_value_text::int)
        ON CONFLICT (org_id, prefix) DO UPDATE
           SET ultimo = GREATEST(academia_de_reciclagem.code_counters.ultimo, EXCLUDED.ultimo);
    END LOOP;
END;
$$;

-- import_entity — upsert-by-natural-key across all 8 entity types + one
-- 'import' revision. Idempotent on (git_sha, natural_key): a re-import of
-- the same bundle line is detected via a prior 'import' revision for the
-- SAME resolved entity at the SAME git_sha, and returns the current row
-- unchanged (no new revision, no re-write).
--
-- Natural-key resolution per contract §A.11: `slug` for kb_entry, `codigo`
-- for decision/open_question/task/content_draft/roadmap_phase, `data|titulo`
-- for timeline_event, `url|kb_slug` for research_source.
CREATE OR REPLACE FUNCTION academia_de_reciclagem.import_entity(
    p_org_id UUID,
    p_entity_type TEXT,
    p_natural_key TEXT,
    p_snapshot JSONB,
    p_prov JSONB
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_entity_id UUID;
    v_git_sha TEXT := p_prov->>'git_sha';
    v_already BOOLEAN;
    v_row JSONB;
    v_rev JSONB;
    v_parts TEXT[];
BEGIN
    CASE p_entity_type
        WHEN 'kb_entry' THEN
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.kb_entries
             WHERE org_id = p_org_id AND slug = p_natural_key;
        WHEN 'decision' THEN
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.decisions
             WHERE org_id = p_org_id AND codigo = p_natural_key;
        WHEN 'open_question' THEN
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.open_questions
             WHERE org_id = p_org_id AND codigo = p_natural_key;
        WHEN 'roadmap_phase' THEN
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.roadmap_phases
             WHERE org_id = p_org_id AND codigo = p_natural_key;
        WHEN 'task' THEN
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.tasks
             WHERE org_id = p_org_id AND codigo = p_natural_key;
        WHEN 'content_draft' THEN
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.content_drafts
             WHERE org_id = p_org_id AND codigo = p_natural_key;
        WHEN 'timeline_event' THEN
            v_parts := string_to_array(p_natural_key, '|');
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.timeline_events
             WHERE org_id = p_org_id AND data = v_parts[1]::date AND titulo = v_parts[2];
        WHEN 'research_source' THEN
            v_parts := string_to_array(p_natural_key, '|');
            SELECT id INTO v_entity_id FROM academia_de_reciclagem.research_sources
             WHERE org_id = p_org_id AND url = v_parts[1] AND kb_slug = v_parts[2];
        ELSE
            RAISE EXCEPTION 'import_entity: unknown entity_type %', p_entity_type USING ERRCODE = 'NA422';
    END CASE;

    IF v_entity_id IS NOT NULL AND v_git_sha IS NOT NULL THEN
        SELECT EXISTS (
            SELECT 1 FROM academia_de_reciclagem.kb_revisions
             WHERE entity_type = p_entity_type AND entity_id = v_entity_id
               AND op = 'import' AND git_sha = v_git_sha
        ) INTO v_already;
        IF v_already THEN
            CASE p_entity_type
                WHEN 'kb_entry' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.kb_entries t WHERE t.id = v_entity_id;
                WHEN 'decision' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.decisions t WHERE t.id = v_entity_id;
                WHEN 'open_question' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.open_questions t WHERE t.id = v_entity_id;
                WHEN 'roadmap_phase' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.roadmap_phases t WHERE t.id = v_entity_id;
                WHEN 'task' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.tasks t WHERE t.id = v_entity_id;
                WHEN 'content_draft' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.content_drafts t WHERE t.id = v_entity_id;
                WHEN 'timeline_event' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.timeline_events t WHERE t.id = v_entity_id;
                WHEN 'research_source' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.research_sources t WHERE t.id = v_entity_id;
            END CASE;
            RETURN v_row;
        END IF;
    END IF;

    PERFORM academia_de_reciclagem._consume_approval(p_org_id, (p_prov->>'approval_id')::uuid);

    IF v_entity_id IS NULL THEN
        CASE p_entity_type
            WHEN 'kb_entry' THEN
                INSERT INTO academia_de_reciclagem.kb_entries (
                    org_id, slug, categoria, subcategoria, titulo, resumo, tags,
                    corpo_md, frontmatter, arquivado
                ) VALUES (
                    p_org_id, p_snapshot->>'slug', p_snapshot->>'categoria', p_snapshot->>'subcategoria',
                    p_snapshot->>'titulo', p_snapshot->>'resumo',
                    COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_snapshot->'tags') x), '{}'),
                    p_snapshot->>'corpo_md', COALESCE(p_snapshot->'frontmatter', '{}'::jsonb),
                    COALESCE((p_snapshot->>'arquivado')::boolean, false)
                ) RETURNING id INTO v_entity_id;
            WHEN 'decision' THEN
                INSERT INTO academia_de_reciclagem.decisions (
                    org_id, codigo, titulo, contexto, decisao, motivo,
                    alternativas_rejeitadas, data, estado, substitui, superseded_by, relacionadas
                ) VALUES (
                    p_org_id, p_natural_key, p_snapshot->>'titulo', p_snapshot->>'contexto',
                    p_snapshot->>'decisao', p_snapshot->>'motivo', p_snapshot->>'alternativas_rejeitadas',
                    (p_snapshot->>'data')::date, COALESCE(p_snapshot->>'estado', 'vigente'),
                    p_snapshot->>'substitui', p_snapshot->>'superseded_by',
                    COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_snapshot->'relacionadas') x), '{}')
                ) RETURNING id INTO v_entity_id;
            WHEN 'open_question' THEN
                INSERT INTO academia_de_reciclagem.open_questions (
                    org_id, codigo, pergunta, por_que_importa, bloqueia, destino_kb,
                    estado, resposta, respondida_em
                ) VALUES (
                    p_org_id, p_natural_key, p_snapshot->>'pergunta', p_snapshot->>'por_que_importa',
                    p_snapshot->>'bloqueia', p_snapshot->>'destino_kb',
                    COALESCE(p_snapshot->>'estado', 'aberta'), p_snapshot->>'resposta',
                    (p_snapshot->>'respondida_em')::timestamptz
                ) RETURNING id INTO v_entity_id;
            WHEN 'roadmap_phase' THEN
                INSERT INTO academia_de_reciclagem.roadmap_phases (
                    org_id, codigo, titulo, objetivo, concluida_quando, estado, ordem
                ) VALUES (
                    p_org_id, p_natural_key, p_snapshot->>'titulo', p_snapshot->>'objetivo',
                    p_snapshot->>'concluida_quando', COALESCE(p_snapshot->>'estado', 'pendente'),
                    COALESCE((p_snapshot->>'ordem')::int, 0)
                ) RETURNING id INTO v_entity_id;
            WHEN 'task' THEN
                INSERT INTO academia_de_reciclagem.tasks (
                    org_id, codigo, titulo, fase, detalhe, estado, bloqueada_por
                ) VALUES (
                    p_org_id, p_natural_key, p_snapshot->>'titulo', p_snapshot->>'fase',
                    p_snapshot->>'detalhe', COALESCE(p_snapshot->>'estado', 'pendente'),
                    p_snapshot->>'bloqueada_por'
                ) RETURNING id INTO v_entity_id;
            WHEN 'content_draft' THEN
                INSERT INTO academia_de_reciclagem.content_drafts (
                    org_id, codigo, tipo, titulo, corpo_md, referencia, fontes
                ) VALUES (
                    p_org_id, p_natural_key, p_snapshot->>'tipo', p_snapshot->>'titulo',
                    p_snapshot->>'corpo_md', p_snapshot->>'referencia',
                    COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_snapshot->'fontes') x), '{}')
                ) RETURNING id INTO v_entity_id;
            WHEN 'timeline_event' THEN
                INSERT INTO academia_de_reciclagem.timeline_events (org_id, data, titulo, descricao)
                VALUES (p_org_id, (p_snapshot->>'data')::date, p_snapshot->>'titulo', p_snapshot->>'descricao')
                RETURNING id INTO v_entity_id;
            WHEN 'research_source' THEN
                INSERT INTO academia_de_reciclagem.research_sources (
                    org_id, url, titulo, trecho_citado, resumo, kb_slug,
                    vigencia_confirmada, exige_da_empresa, accessed_at
                ) VALUES (
                    p_org_id, p_snapshot->>'url', p_snapshot->>'titulo', p_snapshot->>'trecho_citado',
                    p_snapshot->>'resumo', p_snapshot->>'kb_slug',
                    COALESCE((p_snapshot->>'vigencia_confirmada')::boolean, false),
                    p_snapshot->>'exige_da_empresa',
                    COALESCE((p_snapshot->>'accessed_at')::timestamptz, now())
                ) RETURNING id INTO v_entity_id;
        END CASE;
    ELSE
        -- `decisions` is append-only in the general write API (§A.2), but
        -- the IMPORTER is the one authorized writer that replays git
        -- history verbatim, including a decision's own historical edits —
        -- so this path overwrites every domain column directly rather than
        -- going through the CRUD trigger's estado/superseded_by-only gate.
        CASE p_entity_type
            WHEN 'kb_entry' THEN
                UPDATE academia_de_reciclagem.kb_entries SET
                    categoria = p_snapshot->>'categoria', subcategoria = p_snapshot->>'subcategoria',
                    titulo = p_snapshot->>'titulo', resumo = p_snapshot->>'resumo',
                    tags = COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_snapshot->'tags') x), '{}'),
                    corpo_md = p_snapshot->>'corpo_md',
                    frontmatter = COALESCE(p_snapshot->'frontmatter', '{}'::jsonb),
                    arquivado = COALESCE((p_snapshot->>'arquivado')::boolean, false)
                 WHERE id = v_entity_id;
            WHEN 'decision' THEN
                UPDATE academia_de_reciclagem.decisions SET
                    titulo = p_snapshot->>'titulo', contexto = p_snapshot->>'contexto',
                    decisao = p_snapshot->>'decisao', motivo = p_snapshot->>'motivo',
                    alternativas_rejeitadas = p_snapshot->>'alternativas_rejeitadas',
                    data = (p_snapshot->>'data')::date,
                    estado = COALESCE(p_snapshot->>'estado', estado),
                    substitui = p_snapshot->>'substitui', superseded_by = p_snapshot->>'superseded_by',
                    relacionadas = COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_snapshot->'relacionadas') x), '{}')
                 WHERE id = v_entity_id;
            WHEN 'open_question' THEN
                UPDATE academia_de_reciclagem.open_questions SET
                    pergunta = p_snapshot->>'pergunta', por_que_importa = p_snapshot->>'por_que_importa',
                    bloqueia = p_snapshot->>'bloqueia', destino_kb = p_snapshot->>'destino_kb',
                    estado = COALESCE(p_snapshot->>'estado', estado),
                    resposta = p_snapshot->>'resposta',
                    respondida_em = (p_snapshot->>'respondida_em')::timestamptz
                 WHERE id = v_entity_id;
            WHEN 'roadmap_phase' THEN
                UPDATE academia_de_reciclagem.roadmap_phases SET
                    titulo = p_snapshot->>'titulo', objetivo = p_snapshot->>'objetivo',
                    concluida_quando = p_snapshot->>'concluida_quando',
                    estado = COALESCE(p_snapshot->>'estado', estado),
                    ordem = COALESCE((p_snapshot->>'ordem')::int, ordem)
                 WHERE id = v_entity_id;
            WHEN 'task' THEN
                UPDATE academia_de_reciclagem.tasks SET
                    titulo = p_snapshot->>'titulo', fase = p_snapshot->>'fase',
                    detalhe = p_snapshot->>'detalhe', estado = COALESCE(p_snapshot->>'estado', estado),
                    bloqueada_por = p_snapshot->>'bloqueada_por'
                 WHERE id = v_entity_id;
            WHEN 'content_draft' THEN
                UPDATE academia_de_reciclagem.content_drafts SET
                    tipo = p_snapshot->>'tipo', titulo = p_snapshot->>'titulo', corpo_md = p_snapshot->>'corpo_md',
                    referencia = p_snapshot->>'referencia',
                    fontes = COALESCE((SELECT array_agg(x) FROM jsonb_array_elements_text(p_snapshot->'fontes') x), '{}')
                 WHERE id = v_entity_id;
            WHEN 'timeline_event' THEN
                UPDATE academia_de_reciclagem.timeline_events SET
                    data = (p_snapshot->>'data')::date, titulo = p_snapshot->>'titulo',
                    descricao = p_snapshot->>'descricao'
                 WHERE id = v_entity_id;
            WHEN 'research_source' THEN
                UPDATE academia_de_reciclagem.research_sources SET
                    titulo = p_snapshot->>'titulo', trecho_citado = p_snapshot->>'trecho_citado',
                    resumo = p_snapshot->>'resumo',
                    vigencia_confirmada = COALESCE((p_snapshot->>'vigencia_confirmada')::boolean, vigencia_confirmada),
                    exige_da_empresa = p_snapshot->>'exige_da_empresa'
                 WHERE id = v_entity_id;
        END CASE;
    END IF;

    v_rev := academia_de_reciclagem._append_revision(
        p_org_id, p_entity_type, v_entity_id, 'import', p_snapshot, p_prov
    );

    IF p_entity_type = 'kb_entry' THEN
        UPDATE academia_de_reciclagem.kb_entries
           SET current_revision_id = (v_rev->>'id')::uuid
         WHERE id = v_entity_id;
    END IF;

    CASE p_entity_type
        WHEN 'kb_entry' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.kb_entries t WHERE t.id = v_entity_id;
        WHEN 'decision' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.decisions t WHERE t.id = v_entity_id;
        WHEN 'open_question' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.open_questions t WHERE t.id = v_entity_id;
        WHEN 'roadmap_phase' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.roadmap_phases t WHERE t.id = v_entity_id;
        WHEN 'task' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.tasks t WHERE t.id = v_entity_id;
        WHEN 'content_draft' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.content_drafts t WHERE t.id = v_entity_id;
        WHEN 'timeline_event' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.timeline_events t WHERE t.id = v_entity_id;
        WHEN 'research_source' THEN SELECT to_jsonb(t) INTO v_row FROM academia_de_reciclagem.research_sources t WHERE t.id = v_entity_id;
    END CASE;

    RETURN v_row;
END;
$$;


-- import_bundle — the ALL-OR-NOTHING wrapper `PgKnowledgeStore.transaction()`
-- calls exactly once on a clean exit (contract §B.6 "All-or-nothing: a
-- single transaction"). `pg.py` cannot span multiple `.rpc()` calls in one
-- Postgres transaction (see this file's header), so instead it BATCHES
-- `import_entity`/`seed_counters` calls made inside `async with
-- store.transaction():` in memory and, only if the block exits without an
-- exception, sends the whole batch here in ONE call — one function
-- invocation, one real transaction, nothing written until the block
-- actually completes.
CREATE OR REPLACE FUNCTION academia_de_reciclagem.import_bundle(
    p_org_id UUID,
    p_items JSONB,     -- array of {"entity_type","natural_key","snapshot","prov"}
    p_counters JSONB   -- {prefix: value}, or NULL
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
DECLARE
    v_item JSONB;
    v_results JSONB := '[]'::jsonb;
BEGIN
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_results := v_results || jsonb_build_array(
            academia_de_reciclagem.import_entity(
                p_org_id,
                v_item->>'entity_type',
                v_item->>'natural_key',
                v_item->'snapshot',
                v_item->'prov'
            )
        );
    END LOOP;

    IF p_counters IS NOT NULL THEN
        PERFORM academia_de_reciclagem.seed_counters(p_org_id, p_counters);
    END IF;

    RETURN v_results;
END;
$$;


-- ============================================================================
-- Lock every function in this schema down to service_role. PostgREST
-- auto-exposes any function in an exposed schema as `/rpc/<name>`; without
-- this, `create_kb_entry` etc. — SECURITY DEFINER, RLS-bypassing — would be
-- directly callable by any anon/authenticated PostgREST client, skipping
-- the app's entire §B.0 auth/scope/assertion model. These are
-- backend-internal RPCs, invoked only by PgKnowledgeStore's admin client.
-- ============================================================================

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA academia_de_reciclagem FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA academia_de_reciclagem TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA academia_de_reciclagem REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA academia_de_reciclagem GRANT EXECUTE ON FUNCTIONS TO service_role;
