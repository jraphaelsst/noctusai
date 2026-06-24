-- 015_contacts_whatsapp_identity.sql — WhatsApp identity columns on contacts
--
-- Project: sw-contacts-identity-be (2026-06-24).
--
-- Extends social_wiring.contacts to hold the WhatsApp-native identity
-- so one human maps to exactly one contact regardless of how many JID
-- forms WhatsApp uses (phone @c.us, @s.whatsapp.net, one or more @lid).
--
-- Design decisions:
--   - email is made NULLABLE so WhatsApp-sourced contacts (phone only,
--     no email) can be stored.  The pre-existing UNIQUE(org_id,email)
--     constraint is on the column, NOT a partial index, so NULL email
--     rows are not affected by it (SQL NULL != NULL).
--   - whatsapp_phone = digits only, canonical dedup key (no @, no +).
--   - whatsapp_lids  = all known @lid JIDs for this human (union across
--     sessions).
--   - whatsapp_jid   = canonical send JID (<phone>@c.us).
--   - source CHECK constraint is extended to include 'whatsapp'.
--     The constraint is dropped by name and re-added (idempotent guard).
--   - A partial unique index deduplicates (org_id, whatsapp_phone)
--     while ignoring contacts with no WhatsApp identity.
--   - status_pagina row for the FE email_membros route added
--     (mirrors the contacts router page the FE will expose).
--
-- Forward-only + idempotent. Apply after 014. The tech-lead applies
-- this to the live noctusai Supabase via noctus.dev.migrate_product.

SET search_path = social_wiring, public;

-- ── 1. email nullable ────────────────────────────────────────────────────────
ALTER TABLE social_wiring.contacts
    ALTER COLUMN email DROP NOT NULL;

-- ── 2. new WhatsApp identity columns ────────────────────────────────────────
ALTER TABLE social_wiring.contacts
    ADD COLUMN IF NOT EXISTS whatsapp_phone TEXT;

ALTER TABLE social_wiring.contacts
    ADD COLUMN IF NOT EXISTS whatsapp_lids TEXT[] DEFAULT '{}';

ALTER TABLE social_wiring.contacts
    ADD COLUMN IF NOT EXISTS whatsapp_jid TEXT;

-- ── 3. extend source CHECK to include 'whatsapp' ────────────────────────────
-- Drop the existing named constraint (if present) then re-add it.
-- Guard: the DROP is conditional via a DO block so repeated applies
-- are safe even when the constraint was already dropped.
DO $$
DECLARE
    _cname TEXT;
BEGIN
    SELECT conname INTO _cname
    FROM   pg_constraint
    WHERE  conrelid = 'social_wiring.contacts'::regclass
      AND  contype  = 'c'
      AND  conname  LIKE '%source%'
    LIMIT 1;

    IF _cname IS NOT NULL THEN
        EXECUTE format('ALTER TABLE social_wiring.contacts DROP CONSTRAINT %I', _cname);
    END IF;
END;
$$;

ALTER TABLE social_wiring.contacts
    ADD CONSTRAINT contacts_source_check
    CHECK (source IN ('manual', 'import', 'sync:erp', 'form', 'api', 'whatsapp'));

-- ── 4. partial unique index: (org_id, whatsapp_phone) ───────────────────────
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_contacts_org_wa_phone
    ON social_wiring.contacts (org_id, whatsapp_phone)
    WHERE whatsapp_phone IS NOT NULL;

-- ── 5. status_pagina — email_membros (FE Contatos page) ─────────────────────
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('email_membros', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
