-- ============================================================================
-- Migration 174 -- social_wiring: the CPF axis of the clientes review queue.
--
-- WHAT THIS IS
-- ------------
-- One person appearing as two `clientes` rows because two independent
-- card_hub deals each created their own party record for them (evidence:
-- prod P2 cards 890/893 and 882/881 -- the SAME uploaded document, by hash,
-- extracted the same CPF onto two different `clientes` rows). Migration 097's
-- header already named the fix: "duplicate-CPF detection belongs with the
-- existing dedup surface" -- `identidade_service`'s review groups and
-- `cliente_revisao_rejeitadas` (050), never a UNIQUE constraint on
-- `clientes.cpf` (097 explains why that would break the XLSX importer and
-- the existing merge-after-the-fact flow).
--
-- 🔴 THIS IS A SECOND, INDEPENDENT AXIS -- NOT A REPLACEMENT
-- ------------------------------------------------------------
-- `list_review_groups` (existing) clusters `identidade_incerta` leads by
-- `cliente_touches.chave_canonica` (phone/email) -- the marketing-funnel
-- axis. A card_hub deal party (migration 073/098) is created directly, is
-- never `identidade_incerta`, and never gets a `cliente_touches` row, so it
-- can never surface there. `app.services.clientes_service.
-- list_cpf_review_groups` is the new, independent query that finds these
-- groups by normalized, check-digit-valid CPF instead -- computed LIVE on
-- every call, same as the phone/email queue, so there is no batch job and
-- no staleness window.
--
-- WHY THIS TOUCHES `cliente_revisao_rejeitadas` AND NOT A NEW TABLE
-- --------------------------------------------------------------------
-- Its own comment on `chave_canonica` already says what the column is for:
-- "the REAL shared key the candidates only ever hold". For the phone/email
-- axis that key is an E.164 phone or a lowercased email; for the CPF axis it
-- is the normalized 11-digit CPF. The two key spaces never collide (a phone
-- key always starts with `+`, an email key always contains `@`, a CPF key is
-- exactly 11 digits) so ONE column, ONE unique index, and ONE router
-- pagination/reject code path serve both axes with no ambiguity. Widening
-- the `motivo` CHECK is the only schema change either axis needs.
--
-- `cliente_merges.motivo` gets the identical widening for the identical
-- reason: `merge_clientes` (used by BOTH axes' confirm action) snapshots
-- `motivo` into that table's own CHECK-constrained column.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision,
-- after the user has stated the row counts this will touch.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cliente_revisao_rejeitadas
    DROP CONSTRAINT IF EXISTS cliente_revisao_rejeitadas_motivo_check;
ALTER TABLE social_wiring.cliente_revisao_rejeitadas
    ADD CONSTRAINT cliente_revisao_rejeitadas_motivo_check
    CHECK (motivo IN ('C4', 'C5', 'C6', 'CPF'));

COMMENT ON COLUMN social_wiring.cliente_revisao_rejeitadas.chave_canonica IS
    'The review group''s identifying key. For the phone/email axis (048/050)
    an E.164 phone or a lowercased email, carried on cliente_touches. For the
    CPF axis (174) the normalized 11-digit CPF -- see
    clientes_service.list_cpf_review_groups. The two key spaces never
    collide by construction (phone starts with "+", email contains "@", CPF
    is exactly 11 digits), so one column serves both.';

ALTER TABLE social_wiring.cliente_merges
    DROP CONSTRAINT IF EXISTS cliente_merges_motivo_check;
ALTER TABLE social_wiring.cliente_merges
    ADD CONSTRAINT cliente_merges_motivo_check
    CHECK (motivo IN ('C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'CPF'));

NOTIFY pgrst, 'reload schema';
