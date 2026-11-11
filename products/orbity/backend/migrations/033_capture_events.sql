-- Public lead capture: one append-only event per submission the honeypot discarded (owner decision 2026-11-10), so the bot
-- rate is measurable. No PII: the org, the kind and the time only (no ip, no payload). Service-role only.
SET search_path = orbity, public;

CREATE TABLE IF NOT EXISTS orbity.capture_events (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('honeypot_discarded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orbity_capture_events_org_created ON orbity.capture_events (org_id, created_at DESC);

ALTER TABLE orbity.capture_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON orbity.capture_events;
CREATE POLICY "service_role_bypass" ON orbity.capture_events FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON orbity.capture_events FROM PUBLIC, anon, authenticated;
GRANT ALL ON orbity.capture_events TO service_role;
COMMENT ON TABLE orbity.capture_events IS 'tier:org';
