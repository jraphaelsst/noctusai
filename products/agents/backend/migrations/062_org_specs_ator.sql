-- ============================================================================
-- 062_org_specs_ator.sql -- Julia-line S9 follow-up: who changed an org spec, shown to the org.
--
-- `agent_org_specs.updated_by` already holds the person (a noc user id). A change made from social-wiring is
-- PRODUCT-ATTESTED: the channel token vouches for the acting user it forwards. This adds the display name of that person
-- (so the SW UI can say "alterado por X em Y" without a cross-product lookup) and the id of the channel token that carried
-- the write (which product/grant), so the audit has both the token and the person.
--
-- Forward-only + idempotent (ADD COLUMN IF NOT EXISTS). No CHECK: the 200-char cap on the name is the API's (AtorAtestado).
-- ============================================================================

SET search_path = agents, public;

ALTER TABLE agents.agent_org_specs ADD COLUMN IF NOT EXISTS updated_by_nome TEXT NULL;
ALTER TABLE agents.agent_org_specs ADD COLUMN IF NOT EXISTS updated_by_token UUID NULL;
