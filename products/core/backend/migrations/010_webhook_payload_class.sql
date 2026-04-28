-- 010 · Webhook payload classification
--
-- Shipped by `products/core/projects/webhook-event-classification/` (2026-04-24)
-- under `projects/seed-core-consolidation/` §7.5 user directive.
--
-- Adds `payload_class` to `webhook_deliveries` so each stored row records
-- WHICH classification policy was applied at dispatch time. Default for
-- every event today is `metadata_only` (safest LGPD-minimization posture);
-- individual events can be elevated to `full` / `redacted` / `hashed` via
-- the registry at `app/services/webhook_classification.py` when a concrete
-- integration requires it.
--
-- Existing rows: payload_class stays NULL. `retry_delivery` keeps working
-- for those rows until their 30-day retention window closes and they're
-- purged by the scheduler.
--
-- Class semantics (enforced in application code + CHECK below):
--   full          — entire JSON payload stored; retry works.
--   redacted      — PII fields stripped; retry works with reduced data.
--   hashed        — SHA-256 of payload stored; retry CANNOT reconstruct.
--   metadata_only — empty JSONB ({}) stored; retry fails loudly.

ALTER TABLE webhook_deliveries
  ADD COLUMN IF NOT EXISTS payload_class TEXT
  CHECK (payload_class IS NULL OR payload_class IN ('full', 'redacted', 'hashed', 'metadata_only'));

COMMENT ON COLUMN webhook_deliveries.payload_class IS
  'Classification applied at dispatch time (full/redacted/hashed/metadata_only). '
  'NULL for pre-classification rows (before 2026-04-24). '
  'See app/services/webhook_classification.py for the event→class registry.';

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_payload_class
  ON webhook_deliveries(payload_class)
  WHERE payload_class IS NOT NULL;
