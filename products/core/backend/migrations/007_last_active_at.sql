-- Migration 007: Add last_active_at column to noctus_users
--
-- Tracks the last time a user refreshed their token, providing
-- visibility into user activity for admin dashboards and security auditing.

ALTER TABLE noctus_users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;
