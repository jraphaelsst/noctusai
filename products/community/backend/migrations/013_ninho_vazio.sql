-- ============================================================
-- Schema lock — pin name resolution to community, public
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = community, public;

-- ============================================================================
-- Migration 013 — Ninho Vazio: member accounts, tiers, grace period,
-- cashflow, relationship timeline, grupoterapia.
--
-- Contract: products/community/projects/ninho-vazio/CONTRACT.md (2026-09-28).
--
-- Five things change, in this order:
--   1. A new org role, `membro` (an end customer with a login), and the
--      staff predicate `community.eh_equipe()`. EVERY pre-existing
--      org-scoped policy is narrowed to staff — before this migration any
--      authenticated org user could read the whole back office, which was
--      harmless only while no customer ever had a login.
--   2. Member-self SELECT policies, so a `membro` reads only their own rows.
--   3. Billing lifecycle columns: grace window (`carencia`), expiry, the
--      paid-through date, and a per-org billing settings row.
--   4. `lancamentos` (cashflow) and `membro_eventos` (CRM timeline; closes
--      NOC-REMEDIATE[status-history] from membros_service).
--   5. Grupoterapia sessions + speaking-seat reservations, with the seat
--      capacity enforced by a row-locking function (never check-then-insert
--      from the API).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Staff predicate
--
-- ALLOW-list. The community org is the platform org, shared with other
-- products' users (17 `corretor` rows on 2026-09-28): a deny-list of just
-- 'membro' would have made every broker a community moderator. Unknown,
-- NULL and future roles are NOT staff. Mirrored by
-- `app.dependencies.COMMUNITY_STAFF_ORG_ROLES` — keep the two identical.
-- `noctus_users.role = 'admin'` is the platform admin.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION community.eh_equipe()
  RETURNS boolean
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT COALESCE(
    (SELECT org_role IN ('owner', 'admin', 'moderador', 'dev') OR role = 'admin'
       FROM public.noctus_users WHERE id = (SELECT auth.uid())),
    false
  );
$f$;

-- The caller's org read straight from their profile, WITHOUT the role
-- filter the fleet-wide `public.current_org_id()` applies to customer roles
-- (it returns NULL for a `membro`, so no other product's org-scoped policy
-- can match them). Community's member-self policies need the org anyway.
CREATE OR REPLACE FUNCTION community.org_do_usuario()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;

-- The caller's own membro id (NULL for staff / non-members).
CREATE OR REPLACE FUNCTION community.meu_membro_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'community', 'public'
AS $f$
  SELECT id FROM community.membros
   WHERE user_id = (SELECT auth.uid()) AND org_id = community.org_do_usuario()
   LIMIT 1;
$f$;

REVOKE ALL ON FUNCTION community.eh_equipe() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION community.org_do_usuario() FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION community.meu_membro_id() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION community.eh_equipe() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION community.org_do_usuario() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION community.meu_membro_id() TO authenticated, service_role;

-- Narrow every existing org-scoped `authenticated` policy to staff.
-- Generic on purpose: migrations 006/008/009/011 created ~60 such policies,
-- and naming them one by one is how one gets missed. Idempotent — a policy
-- already mentioning eh_equipe is skipped. status_pagina is excluded: members
-- need their nav too.
DO $$
DECLARE
    p RECORD;
BEGIN
    FOR p IN
        SELECT schemaname, tablename, policyname, cmd, qual, with_check
          FROM pg_policies
         WHERE schemaname = 'community'
           AND ('authenticated' = ANY (roles) OR 'public' = ANY (roles))
           AND tablename <> 'status_pagina'
           AND COALESCE(qual, '') || COALESCE(with_check, '') LIKE '%current_org_id()%'
           AND COALESCE(qual, '') || COALESCE(with_check, '') NOT LIKE '%eh_equipe%'
    LOOP
        IF p.cmd = 'INSERT' THEN
            EXECUTE format(
                'ALTER POLICY %I ON %I.%I WITH CHECK ((%s) AND community.eh_equipe())',
                p.policyname, p.schemaname, p.tablename, p.with_check);
        ELSIF p.with_check IS NOT NULL THEN
            EXECUTE format(
                'ALTER POLICY %I ON %I.%I USING ((%s) AND community.eh_equipe()) WITH CHECK ((%s) AND community.eh_equipe())',
                p.policyname, p.schemaname, p.tablename, p.qual, p.with_check);
        ELSE
            EXECUTE format(
                'ALTER POLICY %I ON %I.%I USING ((%s) AND community.eh_equipe())',
                p.policyname, p.schemaname, p.tablename, p.qual);
        END IF;
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- 2. membros: new origin + member-self read
-- ----------------------------------------------------------------------------

ALTER TABLE community.membros DROP CONSTRAINT IF EXISTS membros_origem_check;
ALTER TABLE community.membros ADD CONSTRAINT membros_origem_check
    CHECK (origem IN ('checkout', 'aplicacao', 'convite', 'cadastro'));

-- One login ↔ one membro per org.
CREATE UNIQUE INDEX IF NOT EXISTS membros_org_user_unique
    ON community.membros (org_id, user_id) WHERE user_id IS NOT NULL;

-- Deliberately NO member-self SELECT on `membros`: the row carries staff-only
-- `observacoes` and `tags` (sensitive for this audience — LGPD). Members read
-- their own record only through `/api/portal/*`, which projects the columns
-- (the API resolves the row with the service-role client, keyed on the JWT).
DROP POLICY IF EXISTS "membros_select_self" ON community.membros;

DROP POLICY IF EXISTS "planos_select_ativos_membro" ON community.planos;
CREATE POLICY "planos_select_ativos_membro" ON community.planos
    FOR SELECT TO authenticated
    USING (ativo AND org_id = community.org_do_usuario());

-- ----------------------------------------------------------------------------
-- 3. Billing lifecycle
--
-- estado vocabulary (pt-BR ↔ seed SubscriptionState):
--   iniciada=INCOMPLETE · ativa=ACTIVE · inadimplente=PAST_DUE ·
--   carencia=GRACE · pausada · cancelada=CANCELED · expirada=EXPIRED
-- ----------------------------------------------------------------------------

ALTER TABLE community.assinaturas DROP CONSTRAINT IF EXISTS assinaturas_estado_check;
ALTER TABLE community.assinaturas ADD CONSTRAINT assinaturas_estado_check
    CHECK (estado IN ('iniciada', 'ativa', 'inadimplente', 'carencia',
                      'pausada', 'cancelada', 'expirada'));

ALTER TABLE community.assinaturas
    ADD COLUMN IF NOT EXISTS inadimplente_desde TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS carencia_ate TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pago_ate TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS proxima_cobranca DATE,
    ADD COLUMN IF NOT EXISTS expirada_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancelamento_solicitado_por TEXT
        CHECK (cancelamento_solicitado_por IN ('membro', 'equipe', 'sistema')),
    ADD COLUMN IF NOT EXISTS cancelamento_motivo TEXT,
    ADD COLUMN IF NOT EXISTS gateway_cancelamento_pendente BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_community_assinaturas_carencia
    ON community.assinaturas (carencia_ate) WHERE estado = 'carencia';
CREATE INDEX IF NOT EXISTS idx_community_assinaturas_pago_ate
    ON community.assinaturas (pago_ate) WHERE estado = 'cancelada';

DROP POLICY IF EXISTS "assinaturas_select_self" ON community.assinaturas;
CREATE POLICY "assinaturas_select_self" ON community.assinaturas
    FOR SELECT TO authenticated
    USING (membro_id = community.meu_membro_id());

DROP POLICY IF EXISTS "pagamentos_select_self" ON community.pagamentos;
CREATE POLICY "pagamentos_select_self" ON community.pagamentos
    FOR SELECT TO authenticated
    USING (membro_id = community.meu_membro_id());

CREATE TABLE IF NOT EXISTS community.configuracoes_cobranca (
    org_id UUID PRIMARY KEY,
    dias_carencia INTEGER NOT NULL DEFAULT 5 CHECK (dias_carencia BETWEEN 0 AND 60),
    automacoes_ativas BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE community.configuracoes_cobranca ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE TRIGGER set_updated_at_configuracoes_cobranca
    BEFORE UPDATE ON community.configuracoes_cobranca
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();
DROP POLICY IF EXISTS "configuracoes_cobranca_select_equipe" ON community.configuracoes_cobranca;
CREATE POLICY "configuracoes_cobranca_select_equipe" ON community.configuracoes_cobranca
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND community.eh_equipe());
DROP POLICY IF EXISTS "configuracoes_cobranca_write_equipe" ON community.configuracoes_cobranca;
CREATE POLICY "configuracoes_cobranca_write_equipe" ON community.configuracoes_cobranca
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id() AND community.eh_equipe())
    WITH CHECK (org_id = public.current_org_id() AND community.eh_equipe());

-- ----------------------------------------------------------------------------
-- 4a. lancamentos — cashflow
--
-- `pagamento_id` UNIQUE makes webhook replays idempotent: a paid charge
-- books exactly one entrada; its refund books exactly one saida
-- (categoria='estorno', its own row keyed by `estorno_de`).
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS community.lancamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida')),
    categoria TEXT NOT NULL CHECK (char_length(categoria) BETWEEN 1 AND 60),
    descricao TEXT CHECK (char_length(descricao) <= 300),
    valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
    data DATE NOT NULL,
    origem TEXT NOT NULL CHECK (origem IN ('pagamento', 'estorno', 'manual')),
    pagamento_id UUID NULL REFERENCES community.pagamentos(id) ON DELETE SET NULL,
    estorno_de UUID NULL REFERENCES community.pagamentos(id) ON DELETE SET NULL,
    membro_id UUID NULL REFERENCES community.membros(id) ON DELETE SET NULL,
    criado_por UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS lancamentos_pagamento_unique
    ON community.lancamentos (pagamento_id) WHERE pagamento_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS lancamentos_estorno_unique
    ON community.lancamentos (estorno_de) WHERE estorno_de IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_community_lancamentos_org_data
    ON community.lancamentos (org_id, data);
ALTER TABLE community.lancamentos ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE TRIGGER set_updated_at_lancamentos
    BEFORE UPDATE ON community.lancamentos
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();
DROP POLICY IF EXISTS "lancamentos_equipe" ON community.lancamentos;
CREATE POLICY "lancamentos_equipe" ON community.lancamentos
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id() AND community.eh_equipe())
    WITH CHECK (org_id = public.current_org_id() AND community.eh_equipe());

-- ----------------------------------------------------------------------------
-- 4b. membro_eventos — relationship timeline (append-only)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS community.membro_eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    membro_id UUID NOT NULL REFERENCES community.membros(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN
        ('status', 'plano', 'pagamento', 'assinatura', 'nota', 'contato',
         'acesso', 'grupoterapia', 'sistema')),
    descricao TEXT NOT NULL CHECK (char_length(descricao) BETWEEN 1 AND 2000),
    dados JSONB NOT NULL DEFAULT '{}'::jsonb,
    autor_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_community_membro_eventos_membro
    ON community.membro_eventos (org_id, membro_id, created_at DESC);
ALTER TABLE community.membro_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "membro_eventos_select_equipe" ON community.membro_eventos;
CREATE POLICY "membro_eventos_select_equipe" ON community.membro_eventos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id() AND community.eh_equipe());
DROP POLICY IF EXISTS "membro_eventos_insert_equipe" ON community.membro_eventos;
CREATE POLICY "membro_eventos_insert_equipe" ON community.membro_eventos
    FOR INSERT TO authenticated
    WITH CHECK (org_id = public.current_org_id() AND community.eh_equipe());
-- No UPDATE/DELETE policy: the timeline is append-only.

-- ----------------------------------------------------------------------------
-- 5. Grupoterapia
--
-- Watching needs no reservation (tier gate only). Speaking needs a seat,
-- and `vagas_fala` is enforced by `reservar_vaga_fala` under a row lock.
-- `link_sala` is never exposed by RLS to members: they have no SELECT
-- policy on grupoterapia_sessoes; the portal API reads it with the
-- service-role client AFTER the tier check.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS community.grupoterapia_sessoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL CHECK (char_length(titulo) BETWEEN 1 AND 120),
    descricao TEXT CHECK (char_length(descricao) <= 2000),
    inicio TIMESTAMPTZ NOT NULL,
    duracao_minutos INTEGER NOT NULL DEFAULT 90 CHECK (duracao_minutos BETWEEN 15 AND 480),
    link_sala TEXT CHECK (char_length(link_sala) <= 500),
    vagas_fala INTEGER NOT NULL DEFAULT 8 CHECK (vagas_fala BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'agendada'
        CHECK (status IN ('agendada', 'realizada', 'cancelada')),
    criado_por UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_community_gt_sessoes_org_inicio
    ON community.grupoterapia_sessoes (org_id, inicio);
ALTER TABLE community.grupoterapia_sessoes ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE TRIGGER set_updated_at_grupoterapia_sessoes
    BEFORE UPDATE ON community.grupoterapia_sessoes
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();
DROP POLICY IF EXISTS "gt_sessoes_equipe" ON community.grupoterapia_sessoes;
CREATE POLICY "gt_sessoes_equipe" ON community.grupoterapia_sessoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id() AND community.eh_equipe())
    WITH CHECK (org_id = public.current_org_id() AND community.eh_equipe());

CREATE TABLE IF NOT EXISTS community.grupoterapia_reservas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    sessao_id UUID NOT NULL REFERENCES community.grupoterapia_sessoes(id) ON DELETE CASCADE,
    membro_id UUID NOT NULL REFERENCES community.membros(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'confirmada' CHECK (status IN ('confirmada', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sessao_id, membro_id)
);
ALTER TABLE community.grupoterapia_reservas ENABLE ROW LEVEL SECURITY;
CREATE OR REPLACE TRIGGER set_updated_at_grupoterapia_reservas
    BEFORE UPDATE ON community.grupoterapia_reservas
    FOR EACH ROW EXECUTE FUNCTION community.set_updated_at();
DROP POLICY IF EXISTS "gt_reservas_equipe" ON community.grupoterapia_reservas;
CREATE POLICY "gt_reservas_equipe" ON community.grupoterapia_reservas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id() AND community.eh_equipe())
    WITH CHECK (org_id = public.current_org_id() AND community.eh_equipe());
DROP POLICY IF EXISTS "gt_reservas_select_self" ON community.grupoterapia_reservas;
CREATE POLICY "gt_reservas_select_self" ON community.grupoterapia_reservas
    FOR SELECT TO authenticated
    USING (membro_id = community.meu_membro_id());

-- Reserve a speaking seat. Called by the API with the SERVICE-ROLE client
-- only after the API verified the member's tier is 'falar'. Returns one of:
--   'confirmada'  seat taken (or already held — idempotent)
--   'lotada'      no seat left
--   'indisponivel' session not 'agendada' or already started
CREATE OR REPLACE FUNCTION community.reservar_vaga_fala(p_sessao UUID, p_membro UUID)
  RETURNS text
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'community', 'public'
AS $f$
DECLARE
    s community.grupoterapia_sessoes%ROWTYPE;
    ocupadas integer;
BEGIN
    SELECT * INTO s FROM community.grupoterapia_sessoes WHERE id = p_sessao FOR UPDATE;
    IF NOT FOUND OR s.status <> 'agendada' OR s.inicio <= now() THEN
        RETURN 'indisponivel';
    END IF;
    IF EXISTS (SELECT 1 FROM community.grupoterapia_reservas
                WHERE sessao_id = p_sessao AND membro_id = p_membro AND status = 'confirmada') THEN
        RETURN 'confirmada';
    END IF;
    SELECT count(*) INTO ocupadas FROM community.grupoterapia_reservas
     WHERE sessao_id = p_sessao AND status = 'confirmada';
    IF ocupadas >= s.vagas_fala THEN
        RETURN 'lotada';
    END IF;
    INSERT INTO community.grupoterapia_reservas (org_id, sessao_id, membro_id, status)
    VALUES (s.org_id, p_sessao, p_membro, 'confirmada')
    ON CONFLICT (sessao_id, membro_id) DO UPDATE SET status = 'confirmada';
    RETURN 'confirmada';
END;
$f$;
REVOKE ALL ON FUNCTION community.reservar_vaga_fala(UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION community.reservar_vaga_fala(UUID, UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- Nav rows. membros/planos/inscricoes/financeiro never had rows (their nav
-- items were hidden unless inserted by hand — fix-on-contact), and the
-- whatsapp sub-pages were seeded with underscores while the nav keys use
-- hyphens.
-- ----------------------------------------------------------------------------

INSERT INTO community.status_pagina (nome_pagina, status) VALUES
    ('membros', 'producao'),
    ('planos', 'producao'),
    ('inscricoes', 'producao'),
    ('financeiro', 'producao'),
    ('whatsapp-sincronizacao', 'producao'),
    ('whatsapp-transmissoes', 'producao'),
    ('grupoterapia', 'producao'),
    ('portal', 'producao'),
    ('portal-grupoterapia', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Least privilege + RLS assertion (same defense as 008/009).
-- ----------------------------------------------------------------------------

REVOKE ALL ON ALL TABLES IN SCHEMA community FROM anon;

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'configuracoes_cobranca', 'lancamentos', 'membro_eventos',
        'grupoterapia_sessoes', 'grupoterapia_reservas'
    ]
    LOOP
        IF NOT (SELECT relrowsecurity FROM pg_class
                 WHERE oid = ('community.' || tbl)::regclass) THEN
            RAISE EXCEPTION 'migration 013: RLS is not enabled on community.%', tbl;
        END IF;
    END LOOP;
    -- Every authenticated/public policy outside status_pagina must carry the
    -- staff predicate, or be one of the NAMED member-facing policies below.
    -- A name allow-list, not a text match on `auth.uid()`: a future
    -- `org_id IN (SELECT … auth.uid())` policy must fail here, not pass.
    IF EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'community'
           AND ('authenticated' = ANY (roles) OR 'public' = ANY (roles))
           AND tablename <> 'status_pagina'
           AND COALESCE(qual, '') || COALESCE(with_check, '') NOT LIKE '%eh_equipe()%'
           AND policyname NOT IN (
               'planos_select_ativos_membro',
               'assinaturas_select_self',
               'pagamentos_select_self',
               'gt_reservas_select_self')
    ) THEN
        RAISE EXCEPTION 'migration 013: a community policy is neither staff-gated nor a named member-self policy';
    END IF;
END $$;
