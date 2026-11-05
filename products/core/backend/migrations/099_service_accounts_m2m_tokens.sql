-- 099: service accounts + M2M token support (Julia-line CONTRACT §D6, owner decisions 2026-11-04).
--
-- (098 is claimed by feat/nosnolimiar-rename; 095 was never used.)
--   1. public.service_accounts       -- non-human principals ("noc-agent": Claude automation, not Julia).
--   2. public.api_tokens.service_account_id (nullable FK) -- which service account a token belongs to.
--   3. platform_settings.exigir_mfa_para_tokens = 'false' -- MFA to mint/rotate a token, ships OFF
--      (the owner does not use MFA yet; the switch is on core's dashboard).
-- RLS is the same as api_tokens (074): on, one service_role policy, nobody else. Re-runnable.
SET search_path = public, public;

CREATE TABLE IF NOT EXISTS public.service_accounts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at  TIMESTAMPTZ
);
ALTER TABLE public.service_accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.service_accounts;
CREATE POLICY "service_role_bypass" ON public.service_accounts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

INSERT INTO public.service_accounts (slug, name, description) VALUES
    ('noc-agent', 'noc-agent', 'Automação da NoctusAI (Claude e ferramentas mecanizadas). Não é o token de nenhum agente de produto.')
ON CONFLICT (slug) DO NOTHING;

ALTER TABLE public.api_tokens
    ADD COLUMN IF NOT EXISTS service_account_id UUID REFERENCES public.service_accounts(id);
CREATE INDEX IF NOT EXISTS idx_api_tokens_service_account
    ON public.api_tokens(service_account_id) WHERE service_account_id IS NOT NULL;

INSERT INTO public.platform_settings (key, value, description, is_secret) VALUES
    ('exigir_mfa_para_tokens', 'false',
     'Exigir MFA (aal2) para gerar ou rotacionar tokens de API. false = não exige (padrão: ainda não usamos MFA).', false)
ON CONFLICT (key) DO NOTHING;
