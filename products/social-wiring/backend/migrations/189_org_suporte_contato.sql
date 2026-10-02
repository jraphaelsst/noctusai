-- ============================================================================
-- 189 — the office's SUPPORT contact (owner decision 2026-10-02)
--
-- The "Tenho dúvida — falar com o suporte" button on the Receita "positiva
-- com efeitos de negativa" ciência gate (186 / certidao_pcen) used to route to
-- the first active `notification_recipients` row. The owner decided support
-- must be SEPARATE from the notification number: a lead-alert inbox is not a
-- help desk. So the support contact is its own answer, set in Configurações →
-- Imobiliária, and the button reads ONLY this — no fallback to the
-- notification recipients (an unset contact renders "nenhum contato de
-- suporte configurado", never a guess).
--
-- Lives on `org_dados_cadastrais` (100) — the org-keyed row of the office's
-- own operational answers (117 already added its signing-platform and
-- pendências defaults there). Same RLS, same upsert-on-org_id save path.
--
-- `suporte_whatsapp` is E.164 (the platform phone canon,
-- noctusai_lib.primitives.phone); the API normalizes before write and the
-- CHECK refuses anything else that reaches the table. At least one channel
-- when a name is set is enforced at the API boundary, not here — the form
-- saves partially-filled by design (see 100's header).
-- Forward-only, idempotent, no data touched.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.org_dados_cadastrais
    ADD COLUMN IF NOT EXISTS suporte_nome text,
    ADD COLUMN IF NOT EXISTS suporte_whatsapp text,
    ADD COLUMN IF NOT EXISTS suporte_email text;

DO $chk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'org_dados_cadastrais_suporte_whatsapp_e164'
    ) THEN
        ALTER TABLE social_wiring.org_dados_cadastrais
            ADD CONSTRAINT org_dados_cadastrais_suporte_whatsapp_e164
            CHECK (suporte_whatsapp IS NULL OR suporte_whatsapp ~ '^\+[1-9][0-9]{7,14}$');
    END IF;
END
$chk$;

COMMENT ON COLUMN social_wiring.org_dados_cadastrais.suporte_whatsapp IS
    'Support contact WhatsApp (E.164). Read by the PCEN "Tenho dúvida" button; '
    'deliberately separate from notification_recipients (owner, 2026-10-02).';

NOTIFY pgrst, 'reload schema';
