-- ============================================================================
-- Migration 018 — anon holds no privilege on this schema's sequences.
--
-- WHY: the product template's 001 granted ALL on SEQUENCES (existing + DEFAULT
-- PRIVILEGES) to anon, alongside the table grants every product has since
-- revoked. anon has no table write anywhere, so it never needs nextval(); the
-- grant only let the public anon key burn sequence values and read last_value.
-- Found 2026-10-10 by verify_db_guards seed.anon_only_reads_status_pagina after
-- seed 010 (tables clean; the sequence default ACL remained). The template's
-- 001 no longer grants it (the root), and this forward migration clears what
-- the applied 001 left in prod — applied files are immutable (ledger sha256).
-- Idempotent. GuardProbe: verify_db_guards `academia_de_reciclagem.anon_holds_no_sequence_privilege`.
-- ============================================================================

REVOKE ALL ON ALL SEQUENCES IN SCHEMA academia_de_reciclagem FROM anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA academia_de_reciclagem REVOKE ALL ON SEQUENCES FROM anon;
