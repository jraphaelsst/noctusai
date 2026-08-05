-- 045_notification_recipients_per_client.sql — scope alert recipients to a client
--
-- 🔴 MIGRATION FILE ONLY. Applying this is a separate, explicitly-consented
-- step (`noctus.dev.migrate_product target=045_... confirm=true`). Landing the
-- file does NOT touch the database.
--
-- WHY
-- ───
-- `notification_recipients` was org-wide only: every active row received every
-- alert for the whole org. With more than one client under one org — today
-- "João Raphael" and "One Consultoria" — that is wrong in both directions: One's
-- leads reach João's phone, and there is no way to give One its own recipient.
--
-- WHY NULLABLE, AND WHAT NULL MEANS
-- ─────────────────────────────────
-- `client_id IS NULL` means ORG-WIDE: a fallback recipient who hears about
-- anything not claimed by a specific client. It is nullable rather than
-- backfilled because:
--   • every existing row IS legitimately org-wide (that was the only semantics
--     available when it was written) — inventing a client for them would be
--     fabricating intent the operator never expressed; and
--   • a lead that cannot be attributed to a client must still alert SOMEBODY.
--     The org-wide tier is what stops "no client matched" from degrading into
--     silence, which is the exact failure this whole area just had.
--
-- Resolution order is therefore: client-specific recipients if the lead
-- resolves to a client AND that client has ≥1 active recipient; otherwise the
-- org-wide tier. Never both — a client with its own roster should not also
-- spam the org fallback.
--
-- ON DELETE SET NULL, not CASCADE: deleting a client must not silently delete
-- the people who were being alerted. Demoting them to org-wide is recoverable
-- and visible; deleting them is neither.

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.notification_recipients
    ADD COLUMN IF NOT EXISTS client_id UUID
        REFERENCES social_wiring.clients(id) ON DELETE SET NULL;

COMMENT ON COLUMN social_wiring.notification_recipients.client_id IS
    'Client this recipient is scoped to. NULL = org-wide fallback, used when a '
    'lead resolves to no client, or to a client with no active recipient of '
    'its own. See migration 045.';

-- The dispatch query is always "active recipients for (org, client-or-NULL)".
-- Partial on is_active because the inactive rows are dead weight for every
-- read this index exists to serve.
CREATE INDEX IF NOT EXISTS idx_notification_recipients_org_client
    ON social_wiring.notification_recipients (org_id, client_id)
    WHERE is_active;

-- ── Meta Page → client attribution ──────────────────────────────────────────
-- A Meta lead arrives carrying a `page_id` and nothing else that identifies a
-- client. `integration_accounts` cannot answer it: its `meta` row stores an
-- INSTAGRAM business id in `channel_info.channel_id`, not the Facebook Page id
-- the webhook sends (verified 2026-08-05 — 17841401961186685 vs the Page's
-- 204862512706377). So the mapping is stored where the page_id already lives.
--
-- NULL means "not attributed yet", which routes to the org-wide tier. No
-- guessing: a wrong client attribution sends one client's lead PII to another
-- client's contacts, which is worse than a correct fallback.
ALTER TABLE social_wiring.meta_ads_lead_forms
    ADD COLUMN IF NOT EXISTS client_id UUID
        REFERENCES social_wiring.clients(id) ON DELETE SET NULL;

COMMENT ON COLUMN social_wiring.meta_ads_lead_forms.client_id IS
    'Which client this lead form / Page belongs to, for notification routing. '
    'NULL = unattributed; alerts fall back to the org-wide recipients. Set '
    'from the UI — never inferred, because a wrong guess leaks one client''s '
    'lead PII to another client''s contacts. See migration 045.';

CREATE INDEX IF NOT EXISTS idx_meta_ads_lead_forms_client
    ON social_wiring.meta_ads_lead_forms (client_id)
    WHERE client_id IS NOT NULL;

-- RLS: both tables already carry org-scoped policies (`notification_recipients`
-- from the upload-notification work, `meta_ads_lead_forms` from 030/033). A new
-- nullable column is covered by an existing row-level policy — policies filter
-- ROWS, not columns — so no policy change is required or wanted here.
