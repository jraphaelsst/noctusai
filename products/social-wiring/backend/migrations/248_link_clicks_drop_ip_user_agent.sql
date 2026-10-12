-- 248 — link_clicks stores nothing personal: drop ip_address + user_agent.
--
-- Owner decision 2026-10-11 (LGPD): click tracking counts clicks per link and
-- recipient only. The writer (routers/tracking.py) stopped sending these two
-- columns in the same commit. Any value already captured is destroyed with the
-- column. Idempotent.
ALTER TABLE social_wiring.link_clicks DROP COLUMN IF EXISTS ip_address;
ALTER TABLE social_wiring.link_clicks DROP COLUMN IF EXISTS user_agent;
