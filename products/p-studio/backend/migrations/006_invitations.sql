-- ============================================================================
-- 006_invitations.sql — P Studio
-- Schema: p_studio (+ public para a função de papel)
--
-- P Studio foi construído fora do noc com `standard_routers=["health"]` só —
-- nunca herdou "notificacoes"/"team", os dois routers mínimos que todo outro
-- produto da frota registra (ver `products/igig/backend/app/main.py`). Esta
-- migration é o lado SQL de trazer o produto para o mínimo da casa (o lado
-- Python é `app/main.py`, mesmo commit).
--
-- `notificacoes` e `team.list_members`/`team.remove_member` só tocam tabelas
-- da PLATAFORMA (`public.notifications`, `public.noctus_users` — via
-- `deps.get_core_client()`), já provisionadas para todo produto; nada de novo
-- é necessário para essas duas rotas.
--
-- `team.invite`/`accept`/`validate`/`invitations`/`cancel`, porém, usam o
-- cliente admin SCOPED AO SCHEMA DO PRODUTO (`deps.get_admin_client()`) contra
-- uma tabela `invitations` — ver `noctusai_lib.domain.invitations`
-- (create_invitation / validate_invitation / accept_invitation /
-- cancel_invitation / list_pending_invitations). P Studio nunca teve essa
-- tabela porque nasceu fora do noc. Sem ela, todo o fluxo de convite quebra
-- em runtime com 500 "Could not find the table 'p_studio.invitations'".
--
-- Forma canônica: `templates/product-seed/backend/migrations/001_seed.sql`
-- (colunas) + `products/igig/backend/migrations/002_invitations_accepted_columns.sql`
-- (accepted_at/accepted_by, exigidas por `accept_invitation(..., accepted_by=...)`)
-- + `products/igig/backend/migrations/004_rls_current_org_id.sql` (policy
-- qualificada `public.current_org_id()` — a forma que 001_p_studio_schema.sql
-- já usa em toda tabela org-scoped deste produto).
--
-- Forward-only e idempotente (não existe CREATE TABLE/POLICY IF NOT EXISTS
-- para policy, daí o DROP antes; a tabela usa IF NOT EXISTS).
-- ============================================================================

SET search_path = p_studio, public;

CREATE TABLE IF NOT EXISTS p_studio.invitations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    email        TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'member',
    invited_by   UUID NOT NULL,
    token        TEXT UNIQUE NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'accepted', 'expired', 'canceled')),
    expires_at   TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Populadas por `accept_invitation(..., accepted_by=user_id)` — ver
    -- noctusai_lib.domain.invitations.accept_invitation.
    accepted_at  TIMESTAMPTZ,
    accepted_by  UUID REFERENCES auth.users(id)
);

ALTER TABLE p_studio.invitations ENABLE ROW LEVEL SECURITY;

-- Somente leitura direta por org (o fluxo de convite/aceite em si passa pelo
-- admin client no router e ignora RLS de propósito — `validate_invite` busca
-- pelo token sem sessão nenhuma, antes de o convidado ter qualquer org_id).
-- Esta policy cobre o caso de uma tela futura listar convites via cliente
-- autenticado comum, no mesmo formato de `igig.invitations`.
DROP POLICY IF EXISTS "invitations_select_own_org" ON p_studio.invitations;
CREATE POLICY "invitations_select_own_org" ON p_studio.invitations
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE INDEX IF NOT EXISTS idx_p_studio_invitations_org   ON p_studio.invitations(org_id);
CREATE INDEX IF NOT EXISTS idx_p_studio_invitations_token ON p_studio.invitations(token);
