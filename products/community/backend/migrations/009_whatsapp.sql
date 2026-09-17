-- ============================================================
-- Schema lock — pin name resolution to community, public
-- ============================================================
SET search_path = community, public;

-- ============================================================================
-- Migration 009 — Module 3: WhatsApp (grupos, sincronização, transmissões,
-- ingest, flags)
--
-- Contract: community-m3-contract.md (2026-09-16), including the tech-lead
-- decisions D1-D4, §5 (ban-risk) and §6 (LGPD).
--
-- Reuses `noctusai_lib.integrations.whatsapp` (WAHA client, group ops,
-- webhook router, dedup) and `noctusai_lib.domain.engagement` +
-- `noctusai_lib.domain.jobs` (background send worker: retry/lease/
-- dedupe_key). No new gateway/client adapter here — see the contract's
-- "Reuse" section.
--
-- Tier→group mapping needs NO new table — module 1's
-- `planos.entitlements.grupos_whatsapp` already holds it (elements are
-- `community.grupos.id` values).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- grupos
-- ----------------------------------------------------------------------------

CREATE TABLE community.grupos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT true,
    somente_admin BOOLEAN NOT NULL DEFAULT false,
    participantes_observados INTEGER NOT NULL DEFAULT 0,
    sincronizado_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT grupos_org_chat_unique UNIQUE (org_id, chat_id)
);

ALTER TABLE community.grupos ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_grupos
    BEFORE UPDATE ON community.grupos
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "grupos_select_own_org" ON community.grupos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "grupos_insert_own_org" ON community.grupos
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "grupos_update_own_org" ON community.grupos
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "grupos_delete_own_org" ON community.grupos
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- grupo_membros — observed roster mirror
-- ----------------------------------------------------------------------------

CREATE TABLE community.grupo_membros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    grupo_id UUID NOT NULL REFERENCES community.grupos(id) ON DELETE CASCADE,
    participante_jid TEXT NOT NULL,
    membro_id UUID NULL REFERENCES community.membros(id) ON DELETE SET NULL,
    papel TEXT NOT NULL DEFAULT 'participante'
        CHECK (papel IN ('participante', 'admin', 'superadmin')),
    visto_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT grupo_membros_grupo_jid_unique UNIQUE (grupo_id, participante_jid)
);

CREATE INDEX idx_community_grupo_membros_org_membro ON community.grupo_membros(org_id, membro_id);

ALTER TABLE community.grupo_membros ENABLE ROW LEVEL SECURITY;

CREATE POLICY "grupo_membros_select_own_org" ON community.grupo_membros
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "grupo_membros_insert_own_org" ON community.grupo_membros
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "grupo_membros_update_own_org" ON community.grupo_membros
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "grupo_membros_delete_own_org" ON community.grupo_membros
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- lotes_sincronizacao — manager-confirmed state machine (contract §Sincronização)
-- ----------------------------------------------------------------------------

CREATE TABLE community.lotes_sincronizacao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    grupo_id UUID NOT NULL REFERENCES community.grupos(id) ON DELETE CASCADE,
    acao TEXT NOT NULL CHECK (acao IN ('adicionar', 'remover')),
    estado TEXT NOT NULL DEFAULT 'proposto'
        CHECK (estado IN ('proposto', 'confirmado', 'aplicado', 'aplicado_parcial', 'cancelado', 'expirado')),
    total_itens INTEGER NOT NULL DEFAULT 0,
    proposto_por UUID,
    confirmado_por UUID,
    proposto_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmado_em TIMESTAMPTZ,
    aplicado_em TIMESTAMPTZ,
    expira_em TIMESTAMPTZ NOT NULL,
    motivo_falha TEXT
);

CREATE INDEX idx_community_lotes_org_estado ON community.lotes_sincronizacao(org_id, estado);

ALTER TABLE community.lotes_sincronizacao ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lotes_sincronizacao_select_own_org" ON community.lotes_sincronizacao
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "lotes_sincronizacao_insert_own_org" ON community.lotes_sincronizacao
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "lotes_sincronizacao_update_own_org" ON community.lotes_sincronizacao
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "lotes_sincronizacao_delete_own_org" ON community.lotes_sincronizacao
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- lote_itens
-- ----------------------------------------------------------------------------

CREATE TABLE community.lote_itens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    lote_id UUID NOT NULL REFERENCES community.lotes_sincronizacao(id) ON DELETE CASCADE,
    membro_id UUID NULL REFERENCES community.membros(id) ON DELETE SET NULL,
    participante_jid TEXT NOT NULL,
    resultado TEXT NOT NULL DEFAULT 'pendente'
        CHECK (resultado IN ('pendente', 'adicionado', 'removido', 'convite_necessario', 'falhou')),
    codigo_waha INTEGER,
    processado_em TIMESTAMPTZ,
    CONSTRAINT lote_itens_lote_jid_unique UNIQUE (lote_id, participante_jid)
);

ALTER TABLE community.lote_itens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lote_itens_select_own_org" ON community.lote_itens
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "lote_itens_insert_own_org" ON community.lote_itens
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "lote_itens_update_own_org" ON community.lote_itens
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "lote_itens_delete_own_org" ON community.lote_itens
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- transmissoes
-- ----------------------------------------------------------------------------

CREATE TABLE community.transmissoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    corpo TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('anuncio', 'lembrete_evento', 'conteudo')),
    estado TEXT NOT NULL DEFAULT 'rascunho'
        CHECK (estado IN ('rascunho', 'agendada', 'enviando', 'enviada', 'falhou')),
    agendada_para TIMESTAMPTZ,
    enviada_em TIMESTAMPTZ,
    criada_por UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE community.transmissoes ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_transmissoes
    BEFORE UPDATE ON community.transmissoes
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "transmissoes_select_own_org" ON community.transmissoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "transmissoes_insert_own_org" ON community.transmissoes
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "transmissoes_update_own_org" ON community.transmissoes
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "transmissoes_delete_own_org" ON community.transmissoes
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- transmissao_destinos
-- ----------------------------------------------------------------------------

CREATE TABLE community.transmissao_destinos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    transmissao_id UUID NOT NULL REFERENCES community.transmissoes(id) ON DELETE CASCADE,
    grupo_id UUID NOT NULL REFERENCES community.grupos(id),
    estado TEXT NOT NULL DEFAULT 'pendente'
        CHECK (estado IN ('pendente', 'enviado', 'falhou')),
    provider_message_id TEXT,
    erro TEXT,
    enviado_em TIMESTAMPTZ,
    CONSTRAINT transmissao_destinos_transmissao_grupo_unique UNIQUE (transmissao_id, grupo_id)
);

ALTER TABLE community.transmissao_destinos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "transmissao_destinos_select_own_org" ON community.transmissao_destinos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "transmissao_destinos_insert_own_org" ON community.transmissao_destinos
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "transmissao_destinos_update_own_org" ON community.transmissao_destinos
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "transmissao_destinos_delete_own_org" ON community.transmissao_destinos
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- grupo_mensagens — forward-only ingest
--
-- `unique(org_id, provider_message_id)` is the DB idempotency backstop
-- under the Redis pre-filter dedup the seed webhook router already runs
-- (contract §3, item 19).
-- ----------------------------------------------------------------------------

CREATE TABLE community.grupo_mensagens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    grupo_id UUID NOT NULL REFERENCES community.grupos(id) ON DELETE CASCADE,
    provider_message_id TEXT NOT NULL,
    autor_jid TEXT,
    membro_id UUID NULL REFERENCES community.membros(id) ON DELETE SET NULL,
    conteudo TEXT,
    tem_midia BOOLEAN NOT NULL DEFAULT false,
    recebida_em TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT grupo_mensagens_org_provider_unique UNIQUE (org_id, provider_message_id)
);

CREATE INDEX idx_community_grupo_mensagens_org_grupo ON community.grupo_mensagens(org_id, grupo_id);

ALTER TABLE community.grupo_mensagens ENABLE ROW LEVEL SECURITY;

CREATE POLICY "grupo_mensagens_select_own_org" ON community.grupo_mensagens
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "grupo_mensagens_insert_own_org" ON community.grupo_mensagens
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "grupo_mensagens_update_own_org" ON community.grupo_mensagens
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "grupo_mensagens_delete_own_org" ON community.grupo_mensagens
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- No anon policy, no anon grant. Ingest writes go through the
-- SERVICE-ROLE client (the webhook has no JWT) — same convention as
-- every other public-surface write in this product.

-- ----------------------------------------------------------------------------
-- mensagem_flags — AI-flag hand-off to a human moderator
-- ----------------------------------------------------------------------------

CREATE TABLE community.mensagem_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    mensagem_id UUID NOT NULL REFERENCES community.grupo_mensagens(id) ON DELETE CASCADE,
    categoria TEXT,
    severidade TEXT NOT NULL CHECK (severidade IN ('baixa', 'media', 'alta')),
    justificativa TEXT,
    modelo TEXT,
    prompt_versao TEXT,
    estado TEXT NOT NULL DEFAULT 'aberta'
        CHECK (estado IN ('aberta', 'resolvida', 'descartada')),
    resolvido_por UUID,
    resolvido_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_community_mensagem_flags_org_estado_sev ON community.mensagem_flags(org_id, estado, severidade);

ALTER TABLE community.mensagem_flags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "mensagem_flags_select_own_org" ON community.mensagem_flags
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "mensagem_flags_insert_own_org" ON community.mensagem_flags
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "mensagem_flags_update_own_org" ON community.mensagem_flags
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "mensagem_flags_delete_own_org" ON community.mensagem_flags
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ============================================================================
-- jobs — generic background-job queue (Job / JobRepository / Worker)
--
-- Instantiated from noctusai_lib/domain/jobs/migrations/jobs.sql.template
-- (schema `social_wiring` -> `community`, no other changes) — backs the
-- transmissões broadcast send (contract §3, item 17: "enqueues one jobs
-- row per destino ... paced on whatsapp_groups").
--
-- RLS ON, zero policies: a job queue is an internal worker surface
-- written/read only by `service_role` (bypasses RLS). No org-scoped
-- policy is added — nothing in this product exposes job rows directly
-- to an end user.
-- ============================================================================

CREATE TABLE community.jobs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type              TEXT NOT NULL,
    payload           JSONB NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'running', 'completed', 'failed', 'dead_letter')),
    retry_count       INT NOT NULL DEFAULT 0,
    max_retries       INT NOT NULL DEFAULT 3,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_for     TIMESTAMPTZ,
    dedupe_key        TEXT,
    worker_id         TEXT,
    lease_expires_at  TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_community_jobs_dedupe_key
    ON community.jobs (dedupe_key);

CREATE INDEX IF NOT EXISTS ix_community_jobs_status_scheduled
    ON community.jobs (status, scheduled_for, created_at);

CREATE INDEX IF NOT EXISTS ix_community_jobs_status_lease
    ON community.jobs (status, lease_expires_at);

CREATE INDEX IF NOT EXISTS ix_community_jobs_type
    ON community.jobs (type);

CREATE OR REPLACE FUNCTION community.claim_next_job(
    p_worker_id     TEXT,
    p_job_types     TEXT[] DEFAULT NULL,
    p_lease_seconds NUMERIC DEFAULT 600
) RETURNS SETOF community.jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
BEGIN
    RETURN QUERY
    UPDATE community.jobs
    SET status = 'running',
        worker_id = p_worker_id,
        lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
        updated_at = v_now
    WHERE id = (
        SELECT id
        FROM community.jobs
        WHERE (
                (status = 'pending' AND (scheduled_for IS NULL OR scheduled_for <= v_now))
                OR (status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at <= v_now)
              )
          AND (p_job_types IS NULL OR type = ANY (p_job_types))
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION community.fail_job(
    p_job_id              UUID,
    p_error               TEXT,
    p_max_retries         INT,
    p_backoff_seconds     NUMERIC,
    p_backoff_multiplier  NUMERIC,
    p_max_backoff_seconds NUMERIC,
    p_dead_letter         BOOLEAN DEFAULT FALSE
) RETURNS SETOF community.jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_now TIMESTAMPTZ := now();
BEGIN
    RETURN QUERY
    UPDATE community.jobs
    SET status = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN 'dead_letter'
            ELSE 'pending'
        END,
        retry_count = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN retry_count
            ELSE retry_count + 1
        END,
        scheduled_for = CASE
            WHEN p_dead_letter OR retry_count >= p_max_retries THEN scheduled_for
            ELSE v_now + make_interval(
                secs => LEAST(
                    p_backoff_seconds * (p_backoff_multiplier ^ retry_count),
                    p_max_backoff_seconds
                )
            )
        END,
        last_error = p_error,
        worker_id = NULL,
        lease_expires_at = NULL,
        updated_at = v_now
    WHERE id = p_job_id
    RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION community.complete_job(
    p_job_id UUID
) RETURNS SETOF community.jobs
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE community.jobs
    SET status = 'completed',
        worker_id = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_job_id AND status <> 'completed'
    RETURNING *;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT * FROM community.jobs WHERE id = p_job_id AND status = 'completed';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION community.extend_lease(
    p_job_id        UUID,
    p_worker_id     TEXT,
    p_lease_seconds NUMERIC DEFAULT 600
) RETURNS SETOF community.jobs
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE community.jobs
    SET lease_expires_at = now() + make_interval(secs => p_lease_seconds),
        updated_at = now()
    WHERE id = p_job_id AND status = 'running' AND worker_id = p_worker_id
    RETURNING *;
END;
$$;

ALTER TABLE community.jobs ENABLE ROW LEVEL SECURITY;
-- Deliberately no CREATE POLICY — zero policies + RLS enabled denies
-- every non-service-role caller; service_role bypasses RLS.

-- ============================================================================
-- engajamento_pontos — the PointsLedger table (contract §3 engagement
-- hand-off: "EngagementEvent(...) -> evaluate(...) -> make_points_ledger(...)")
--
-- The contract's table list (§2) does not enumerate this table, but the
-- engagement hand-off it explicitly requires cannot be wired without a
-- backing store: `noctusai_lib.domain.engagement.ledger.
-- RealSupabasePointsLedger` is schema/table-scoped with NO org_id in its
-- query builder (member_id/idempotency_key only — see that module's
-- docstring for the exact required shape). Community is single-tenant
-- (one org per instance) and this table is written ONLY by the webhook
-- ingest path via the service-role client — never by an authenticated
-- end-user request. Following amendment A12's own precedent in this
-- product (`webhook_eventos`: "no org_id, so an org-scoped policy is
-- impossible: enable RLS with zero policies"), this table gets the same
-- treatment. Surfaced explicitly in the delivery note — not a silent
-- addition beyond the contract's letter.
-- ============================================================================

CREATE TABLE community.engajamento_pontos (
    member_id TEXT NOT NULL,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    points INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, idempotency_key)
);

CREATE INDEX idx_community_engajamento_pontos_member ON community.engajamento_pontos(member_id);

ALTER TABLE community.engajamento_pontos ENABLE ROW LEVEL SECURITY;
-- Deliberately no CREATE POLICY — zero policies + RLS enabled; the
-- webhook ingest writes via the service-role client only.

-- ============================================================================
-- Seed pages (contract §2: "Also seed the status_pagina rows for the
-- three new pages.")
-- ============================================================================

INSERT INTO community.status_pagina (nome_pagina, status) VALUES
    ('whatsapp', 'producao'),
    ('whatsapp_sincronizacao', 'producao'),
    ('whatsapp_transmissoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ============================================================================
-- Least-privilege grants + RLS assertion (mirrors migration 008's amendment
-- A7 defense — idempotent re-assertion, cheap insurance against a future
-- refactor that drops an ENABLE ROW LEVEL SECURITY line).
-- ============================================================================

REVOKE ALL ON ALL TABLES IN SCHEMA community FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA community REVOKE ALL ON TABLES FROM anon;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'grupos', 'grupo_membros', 'lotes_sincronizacao', 'lote_itens',
        'transmissoes', 'transmissao_destinos', 'grupo_mensagens',
        'mensagem_flags', 'jobs', 'engajamento_pontos'
    ]
    LOOP
        IF NOT (
            SELECT relrowsecurity FROM pg_class
            WHERE oid = ('community.' || tbl)::regclass
        ) THEN
            RAISE EXCEPTION 'migration 009: RLS is not enabled on community.%', tbl;
        END IF;
    END LOOP;
END $$;

-- NOC-REMEDIATE[whatsapp-retention]: no scheduled job yet purges
-- `grupo_mensagens` (90 days), `mensagem_flags` (1 year after
-- resolution), `lotes_*`/`transmissoes` (1/2 years) per contract §6.
-- This product has no scheduler wiring to hang a cleanup job off yet
-- (same gap migration 008 already flagged for `webhook_eventos`). — 2026-09-17
