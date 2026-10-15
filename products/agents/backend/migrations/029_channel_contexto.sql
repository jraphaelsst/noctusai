-- Lais F-AG (contract lais-build-contract §2.1(g)) — per-turn `contexto` stamp.
--
-- A channel turn may carry a `contexto` (knowledge + essential questions +
-- state) rendered by social-wiring. agents stamps the assistant row with the
-- sha256 of that contexto so a transcript row says which context it ran with.
-- Only column added; nullable (every pre-existing row and every non-channel
-- turn keeps NULL).

SET search_path = agents, public;

ALTER TABLE agents.messages
    ADD COLUMN IF NOT EXISTS contexto_hash TEXT NULL;
