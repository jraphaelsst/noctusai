-- Migration: 096_noctus_users_telefone
-- Schema: public (core)
--
-- WHY: owner decision 2026-11-03 -- "MY number must be set in noc's app. Everywhere that
-- uses it consumes from noc." The platform user's WhatsApp number becomes ONE core field
-- (single source of truth). Other products (social-wiring Julia report destination, agents
-- evaluation-mode allow-list) store a USER ID and resolve the phone from core at use time
-- (noctusai_lib.integrations.persistence.table_reads.resolve_user_phones).
--
-- WHAT: public.noctus_users.telefone TEXT NULL, canonical E.164 (noctusai_lib.primitives.phone).
-- NOT organizations.telefone (that is the company phone). The DB CHECK is the backstop for
-- the backend's normalization -- a malformed value can never be stored by any writer.
-- RLS unchanged: the column rides the existing noctus_users policies; writes go through the
-- backend (service role) PATCH /api/auth/profile, which only ever targets the caller's row.
-- Idempotent: ADD COLUMN IF NOT EXISTS + DROP/ADD constraint.

ALTER TABLE public.noctus_users
    ADD COLUMN IF NOT EXISTS telefone TEXT;

ALTER TABLE public.noctus_users
    DROP CONSTRAINT IF EXISTS noctus_users_telefone_e164;

ALTER TABLE public.noctus_users
    ADD CONSTRAINT noctus_users_telefone_e164
        CHECK (telefone IS NULL OR telefone ~ '^\+[1-9][0-9]{7,14}$');

COMMENT ON COLUMN public.noctus_users.telefone IS
    'User WhatsApp number, E.164 (+5511999999999). Single source of truth: products store the user id and resolve the phone from here. NULL = not set.';
