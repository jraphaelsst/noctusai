-- 131_fotos_notificacoes_preferencias.sql -- social_wiring: per-user opt-in
-- for Edição de Fotos "batch ready" notifications
--
-- Plan §1 (Notifications): "in-app + email + WhatsApp. Creator always;
-- agency admins opt in per user; platform admin can switch the whole
-- notification off/on." The platform switch already lives on
-- `fotos_platform_settings.notificacoes_globais_ativas` (123), the org
-- switch on `fotos_org_settings.notificacoes_ativas` (123) -- this table
-- is the missing third layer: which AGENCY ADMIN (owner | admin | manager)
-- individually opted in to be notified of a batch they did not create,
-- plus the WhatsApp number that channel sends to.
--
-- `noctus_users` (Core `public`) carries no phone column at all -- see
-- KB CONTEXT/INTEGRATIONS/whatsapp.md -- so the WhatsApp number is
-- captured HERE, per user, E.164 (`chat_id_for_phone` expects it
-- unprefixed-digits-ready). NULL = WhatsApp channel skipped for that
-- user; email always resolves from `noctus_users.email`.
--
-- The creator of a batch is ALWAYS notified (contract, handled in
-- services/notifier.py without consulting this table). Not gated by role
-- at the DB layer: any authenticated org member can write their OWN row
-- (self-service opt-in page), but the fan-out only ever reads rows for
-- users whose `noctus_users.org_role` is in `AGENCY_ADMIN_ROLES`
-- (owner | admin | manager) -- a corretor's row is inert by construction,
-- same shape as `fotos_referencias`/`fotos_guias_estilo` being
-- platform-scope tables curators can touch without a role check baked
-- into the RLS policy itself.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.fotos_notificacoes_preferencias (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    user_id         UUID NOT NULL,
    -- Master per-user opt-in for the "batch ready" notification (creator
    -- bypasses this -- they are notified regardless of this row).
    ativo           BOOLEAN NOT NULL DEFAULT false,
    -- E.164 (e.g. '+5511999998888'); NULL = WhatsApp channel skipped for
    -- this user even when ativo=true (email + in-app still fire).
    whatsapp_number TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_fotos_notificacoes_preferencias_org
    ON social_wiring.fotos_notificacoes_preferencias (org_id);

ALTER TABLE social_wiring.fotos_notificacoes_preferencias ENABLE ROW LEVEL SECURITY;

-- Self-service: a user reads/writes their OWN preference row only. The
-- admin-roster fan-out (services/notifier.py) reads through the
-- service-role client, so it never needs a broader authenticated policy
-- here -- same reasoning as fotos_platform_settings' narrow read policy.
CREATE POLICY "fotos_notificacoes_preferencias_self" ON social_wiring.fotos_notificacoes_preferencias
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id() AND user_id = auth.uid())
    WITH CHECK (org_id = public.current_org_id() AND user_id = auth.uid());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_notificacoes_preferencias
    FOR ALL TO service_role USING (true) WITH CHECK (true);
