-- =============================================================================
-- 009_webhook_retention.sql
--
-- compliance-audit-reconciliation Phase 6 — finding 8: webhook_deliveries
-- stores full payloads (including PII like team-invite emails) with no
-- retention policy. LGPD minimization: data should not live forever just
-- because it was useful once.
--
-- Decision (2026-04-22, evidence-backed):
--   * Retention window: 30 days for all deliveries. Longer makes the store a
--     secondary long-lived PII log; shorter breaks legitimate audit/replay
--     windows for debugging failed integrations.
--   * Policy: keep FULL payload inside the retention window (so `retry_delivery`
--     still works). Cleanup removes the entire row after the window closes —
--     no partial redaction, no archival sink.
--   * Cleanup: `webhook_retention_service.run_cleanup(db)` — callable manually
--     via admin endpoint until a scheduler is in place.
--
-- Payload-level redaction (e.g. hashing emails inside the stored JSON) is an
-- event-classification exercise deferred to a follow-up project
-- `webhook-event-classification` because it needs per-event decisions.
-- =============================================================================


ALTER TABLE webhook_deliveries
    ADD COLUMN IF NOT EXISTS retention_until TIMESTAMPTZ
        DEFAULT (now() + INTERVAL '30 days');

UPDATE webhook_deliveries
SET retention_until = created_at + INTERVAL '30 days'
WHERE retention_until IS NULL;

ALTER TABLE webhook_deliveries
    ALTER COLUMN retention_until SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_retention
    ON webhook_deliveries(retention_until);
