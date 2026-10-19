-- ============================================================================
-- 035_julia_v2_threads_constraints.sql -- M4 of the shared-thread migration
-- (Julia v2, A-THREAD; contract section 6.5 M4, risk 6).
--
-- !! APPLY ONLY AFTER THE M2 BACKFILL IS VERIFIED (033) AND M3 (linking every
-- !! thread to its lead_ref) HAS RUN. Verify FIRST, on the target database:
-- !!
-- !!   SELECT count(*) FROM agents.conversations
-- !!    WHERE channel IS NOT NULL AND (tipo <> 'thread_lead' OR lead_ref_id IS NULL);   -- must be 0
-- !!   SELECT org_id, channel, channel_ref, count(*) FROM agents.conversations
-- !!    WHERE tipo = 'thread_lead' GROUP BY 1, 2, 3 HAVING count(*) > 1;               -- must be 0 rows
-- !!
-- !! This file refuses to run (RAISE) when either check is not clean, so applying
-- !! it early is a loud no-op, never a half-applied constraint swap.
--
-- 1. The identity of a thread is (org, channel, channel_ref) -- the AGENT is no
--    longer part of it (the thread is shared): the unique index swaps from
--    (org, agent, channel, channel_ref) (025) to (org, channel, channel_ref).
--    The new index is built BEFORE the old one is dropped.
-- 2. Every thread has a lead: the full section 6.1 CHECK
--    (tipo <> 'thread_lead' OR (channel IS NOT NULL AND lead_ref_id IS NOT NULL)).
--
-- CONCURRENTLY is deliberately NOT used: the migration runner executes a file as
-- ONE statement batch (an implicit transaction), where CREATE INDEX CONCURRENTLY
-- is rejected. The guard above makes the plain build safe: the table holds one row
-- per lead conversation and the build takes a short lock.
--
-- Idempotent. NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

DO $$
DECLARE
    v_sem_lead BIGINT;
    v_duplicadas BIGINT;
BEGIN
    SELECT count(*) INTO v_sem_lead FROM agents.conversations
     WHERE channel IS NOT NULL AND (tipo <> 'thread_lead' OR lead_ref_id IS NULL);
    IF v_sem_lead > 0 THEN
        RAISE EXCEPTION 'threads_nao_vinculadas: % channel conversation(s) still without a lead_ref / thread_lead tipo (run M3 first)', v_sem_lead;
    END IF;
    SELECT count(*) INTO v_duplicadas FROM (
        SELECT 1 FROM agents.conversations WHERE tipo = 'thread_lead'
         GROUP BY org_id, channel, channel_ref HAVING count(*) > 1
    ) d;
    IF v_duplicadas > 0 THEN
        RAISE EXCEPTION 'threads_duplicadas: % channel identity(ies) with more than one thread', v_duplicadas;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_threads_channel
    ON agents.conversations (org_id, channel, channel_ref)
    WHERE tipo = 'thread_lead';

DROP INDEX IF EXISTS agents.uq_agents_conversations_channel_ref;

ALTER TABLE agents.conversations DROP CONSTRAINT IF EXISTS conversations_thread_channel_check;
ALTER TABLE agents.conversations DROP CONSTRAINT IF EXISTS conversations_thread_lead_check;
ALTER TABLE agents.conversations
    ADD CONSTRAINT conversations_thread_lead_check
        CHECK (tipo <> 'thread_lead' OR (channel IS NOT NULL AND lead_ref_id IS NOT NULL));
