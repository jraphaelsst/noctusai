-- Migration 014: Add tema (theme preference) column to profiles
-- Persists user's light/dark mode choice across devices.

ALTER TABLE erp.profiles
ADD COLUMN IF NOT EXISTS tema TEXT NOT NULL DEFAULT 'light'
CHECK (tema IN ('light', 'dark'));
