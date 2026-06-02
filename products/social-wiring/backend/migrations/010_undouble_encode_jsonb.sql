-- ============================================================
-- 010 · Fix double-encoded JSONB on integration_accounts.
--
-- Root cause: integration_account_service.py called json.dumps()
-- before passing channel_info / metadata to the supabase-py client.
-- supabase-py serializes JSONB parameters itself, so passing the
-- already-serialised STRING caused the column to store a JSON string
-- value inside JSONB rather than a JSON object (jsonb_typeof = 'string').
-- SQL-side access like `metadata->>'channel_id'` therefore returned NULL.
--
-- Fix applied to the write path (same commit: feat/yt-jsonb-fix).
-- This migration corrects existing corrupt rows in prod.
--
-- Safe to re-run: the WHERE guard makes each UPDATE a no-op when the
-- column already holds a proper object/array/null/number/boolean.
-- DO NOT APPLY this file manually — the tech-lead applies it during deploy.
-- ============================================================

UPDATE social_wiring.integration_accounts
SET channel_info = (channel_info #>> '{}')::jsonb
WHERE jsonb_typeof(channel_info) = 'string';

UPDATE social_wiring.integration_accounts
SET metadata = (metadata #>> '{}')::jsonb
WHERE jsonb_typeof(metadata) = 'string';
