-- ============================================================================
-- Migration 086 — WhatsApp connections become ORG-scoped, not per-user
--
-- WHY THIS EXISTS
-- ---------------
-- `whatsapp_connections` was the ONE table in social_wiring whose authenticated
-- SELECT policy carried a per-user leg on top of the org predicate:
--
--     USING (org_id = current_org_id() AND user_id = (SELECT auth.uid()))
--
-- Every other table in the schema (whatsapp_chats included) is org-only. The
-- per-user leg came from the original intent of one WhatsApp line per user.
-- That intent is being deferred: for now a connection is a SHARED ORG ASSET —
-- one number acting as the platform's WhatsApp notification line, serving
-- every member of the org. Owner's decision, 2026-09-02.
--
-- The symptom the old shape produced: a second member of the same org saw an
-- empty connections list even though the line was right there in their org —
-- the same class of "sync works, list empty" confusion migration 011 fixed for
-- the org predicate itself.
--
-- WHAT ABOUT `user_id`?
-- ---------------------
-- The column STAYS, NOT NULL, and is still written on create. It is now
-- CREATOR PROVENANCE (who set the line up) rather than a scoping predicate.
-- Keeping it means the eventual per-user-lines-within-an-org step has its
-- history intact; dropping it would have thrown that away for no gain.
-- When that step lands it must introduce its OWN explicit column/flag — never
-- silently re-narrow this policy, or org members lose the shared line again.
--
-- The service_role policy is untouched: the backend uses the service-role
-- client, so the store's explicit `.eq("org_id", ...)` filter is the real
-- enforcement on the API path. This policy governs direct-from-browser reads.
--
-- IDEMPOTENT: DROP POLICY IF EXISTS before CREATE POLICY. Re-running is safe.
-- ============================================================================

DROP POLICY IF EXISTS "whatsapp_connections_select_own" ON social_wiring.whatsapp_connections;

-- Name changes from `_select_own` to `_select_own_org` to match the naming of
-- every other org-scoped policy in this schema (migration 011's convention) —
-- "own" now means "own ORG", and the name should not keep implying "own user".
CREATE POLICY "whatsapp_connections_select_own_org" ON social_wiring.whatsapp_connections
  FOR SELECT TO authenticated
  USING (org_id = current_org_id());

-- ---------------------------------------------------------------------------
-- The uniqueness rule has to move with the scope.
--
-- `UNIQUE (org_id, user_id, label)` still believed lines were per-user: two
-- members of the same org could each create a line labelled "Atendimento" and
-- both would be accepted, producing two identically-named entries in what is
-- now ONE shared org list with no way to tell them apart. The label is the
-- org's handle for the line, so it must be unique per org.
--
-- Safe to tighten: verified zero (org_id, label) duplicates on prod before
-- applying. If a future apply hits a duplicate it will fail LOUDLY here rather
-- than silently keeping the looser rule — which is the correct outcome.
-- ---------------------------------------------------------------------------
ALTER TABLE social_wiring.whatsapp_connections
  DROP CONSTRAINT IF EXISTS whatsapp_connections_org_id_user_id_label_key;

ALTER TABLE social_wiring.whatsapp_connections
  DROP CONSTRAINT IF EXISTS whatsapp_connections_org_id_label_key;

ALTER TABLE social_wiring.whatsapp_connections
  ADD CONSTRAINT whatsapp_connections_org_id_label_key UNIQUE (org_id, label);

COMMENT ON COLUMN social_wiring.whatsapp_connections.user_id IS
  'Creator provenance — who set this line up. NOT a scoping predicate: the '
  'connection is a shared org asset (migration 086). Do not filter reads on '
  'this column; per-user lines within an org need their own explicit flag.';
