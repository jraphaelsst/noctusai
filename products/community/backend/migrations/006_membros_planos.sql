-- ============================================================
-- Schema lock — pin name resolution to community, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = community, public;

-- ============================================================================
-- Migration 006 — Module 1: Membros + Planos + Aplicações
--
-- Contract: community-m1-contract.md (2026-09-16). Persists manager-defined
-- paid tiers (`planos`), member records (`membros`), a manager-defined
-- application form (`aplicacao_perguntas`) and its public submissions
-- (`aplicacoes`). Payment-driven status transitions are module 2's job —
-- this migration only stores `membros.status` and lets a manager set it.
--
-- `updated_at` auto-touch follows the platform convention
-- (`noctusai_lib.sql.triggers.updated_at_trigger`): one shared
-- `community.set_updated_at()` function, one BEFORE UPDATE trigger per
-- table.
-- ============================================================================

CREATE OR REPLACE FUNCTION community.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- planos
-- ----------------------------------------------------------------------------

CREATE TABLE community.planos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
    ciclo TEXT NOT NULL CHECK (ciclo IN ('mensal', 'anual')),
    entitlements JSONB NOT NULL DEFAULT '{}'::jsonb,
    ativo BOOLEAN NOT NULL DEFAULT true,
    ordem INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT planos_org_nome_unique UNIQUE (org_id, nome)
);

ALTER TABLE community.planos ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_planos
    BEFORE UPDATE ON community.planos
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "planos_select_own_org" ON community.planos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "planos_insert_own_org" ON community.planos
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "planos_update_own_org" ON community.planos
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "planos_delete_own_org" ON community.planos
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- membros
-- ----------------------------------------------------------------------------

CREATE TABLE community.membros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    telefone TEXT,
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'ativo', 'atrasado', 'pausado', 'cancelado')),
    plano_id UUID NULL REFERENCES community.planos(id) ON DELETE SET NULL,
    origem TEXT NOT NULL CHECK (origem IN ('checkout', 'aplicacao', 'convite')),
    tags TEXT[] NOT NULL DEFAULT '{}',
    user_id UUID NULL,
    observacoes TEXT,
    entrou_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT membros_org_email_unique UNIQUE (org_id, email)
);

CREATE INDEX idx_community_membros_org_status ON community.membros(org_id, status);
CREATE INDEX idx_community_membros_org_plano ON community.membros(org_id, plano_id);

ALTER TABLE community.membros ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_membros
    BEFORE UPDATE ON community.membros
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "membros_select_own_org" ON community.membros
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "membros_insert_own_org" ON community.membros
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "membros_update_own_org" ON community.membros
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "membros_delete_own_org" ON community.membros
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- ----------------------------------------------------------------------------
-- aplicacao_perguntas (manager-defined application-form questions)
-- ----------------------------------------------------------------------------

CREATE TABLE community.aplicacao_perguntas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    pergunta TEXT NOT NULL,
    tipo TEXT NOT NULL
        CHECK (tipo IN ('texto', 'texto_longo', 'escolha_unica', 'escolha_multipla', 'booleano')),
    opcoes TEXT[] NOT NULL DEFAULT '{}',
    obrigatoria BOOLEAN NOT NULL DEFAULT true,
    ordem INTEGER NOT NULL DEFAULT 0,
    ativa BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE community.aplicacao_perguntas ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_aplicacao_perguntas
    BEFORE UPDATE ON community.aplicacao_perguntas
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "aplicacao_perguntas_select_own_org" ON community.aplicacao_perguntas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "aplicacao_perguntas_insert_own_org" ON community.aplicacao_perguntas
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "aplicacao_perguntas_update_own_org" ON community.aplicacao_perguntas
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "aplicacao_perguntas_delete_own_org" ON community.aplicacao_perguntas
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- The public application form must render before sign-in — anon gets
-- SELECT-only, and only the manager-published (`ativa = true`) rows.
-- Deliberately NOT org-scoped: this product is single-tenant (see
-- MASTER-PROMPT.md — "Single community, no multi-tenancy beyond the
-- seed's org scoping"), so the schema holds exactly one org's rows and
-- `ativa = true` is the only predicate the anon caller can evaluate
-- anyway (no `current_org_id()` — anon has no JWT to resolve one from).
CREATE POLICY "aplicacao_perguntas_select_anon_ativas" ON community.aplicacao_perguntas
    FOR SELECT TO anon
    USING (ativa = true);

-- ----------------------------------------------------------------------------
-- aplicacoes (public submissions against the questions above)
-- ----------------------------------------------------------------------------

CREATE TABLE community.aplicacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    telefone TEXT,
    respostas JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aprovada', 'rejeitada')),
    motivo TEXT,
    revisado_por UUID NULL,
    revisado_em TIMESTAMPTZ NULL,
    membro_id UUID NULL REFERENCES community.membros(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_community_aplicacoes_org_status ON community.aplicacoes(org_id, status);

ALTER TABLE community.aplicacoes ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE TRIGGER set_updated_at_aplicacoes
    BEFORE UPDATE ON community.aplicacoes
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();

CREATE POLICY "aplicacoes_select_own_org" ON community.aplicacoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "aplicacoes_insert_own_org" ON community.aplicacoes
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "aplicacoes_update_own_org" ON community.aplicacoes
    FOR UPDATE TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY "aplicacoes_delete_own_org" ON community.aplicacoes
    FOR DELETE TO authenticated
    USING (org_id = public.current_org_id());

-- The public form submits here directly, before any sign-in exists.
-- Anon may INSERT only — no anon SELECT policy exists on this table, so
-- an anon caller can never read back another applicant's submission.
CREATE POLICY "aplicacoes_insert_anon" ON community.aplicacoes
    FOR INSERT TO anon
    WITH CHECK (true);
