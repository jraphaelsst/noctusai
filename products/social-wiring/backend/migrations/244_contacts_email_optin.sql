-- ============================================================================
-- Migration 244 — contacts.email_optin + email_confirmed_at (double opt-in).
--
-- WHY: email-marketing P1b(d). A contact created through a public form / API,
-- or imported with `double_opt_in=true`, must confirm their address before any
-- marketing email reaches them. `contacts.status` is SHARED with WhatsApp
-- contacts (migration 015), so opt-in lives in its own column:
--   'not_required' — the default; every existing row and every manual /
--                    WhatsApp / ERP-sync contact (no confirmation asked);
--   'pending'      — a confirmation email was (or must be) sent; excluded from
--                    campaign and automation sends by recipient resolution;
--   'confirmed'    — the contact clicked the signed link (email_confirmed_at).
-- Additive + idempotent (replay-safe).
-- ============================================================================

ALTER TABLE social_wiring.contacts
    ADD COLUMN IF NOT EXISTS email_optin        TEXT NOT NULL DEFAULT 'not_required',
    ADD COLUMN IF NOT EXISTS email_confirmed_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'contacts_email_optin_check'
          AND conrelid = 'social_wiring.contacts'::regclass
    ) THEN
        ALTER TABLE social_wiring.contacts
            ADD CONSTRAINT contacts_email_optin_check
            CHECK (email_optin IN ('not_required', 'pending', 'confirmed'));
    END IF;
END $$;

COMMENT ON COLUMN social_wiring.contacts.email_optin IS
    'Double opt-in state for marketing email: not_required | pending | confirmed. Pending contacts receive no campaign / automation email.';
COMMENT ON COLUMN social_wiring.contacts.email_confirmed_at IS
    'When the contact confirmed their address through the signed /confirmar-email link (NULL unless email_optin = confirmed).';
