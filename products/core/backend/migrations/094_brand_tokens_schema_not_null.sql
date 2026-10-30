-- Migration: 094_brand_tokens_schema_not_null
-- Schema: public (core)
--
-- WHY: 089's CHECK (tokens->>'schema' = 'noctus.brand-tokens/v1') evaluates to NULL — and a
-- CHECK that is NULL PASSES — when the document has no "schema" key at all ('{}', or a JSON
-- null). The probe org_brand_identities.tokens.schema_check caught it in prod on 2026-10-30:
-- INSERT ... tokens='{}' was permitted. The API validates tokens before writing, so no bad row
-- exists (checked: 1 row, 0 would fail), but the DB backstop must refuse the "no schema" case
-- the rule was written for.
--
-- WHAT: replace the constraint with a NULL-safe form (coalesce → '' never equals the schema id).
-- Idempotent: DROP IF EXISTS + ADD; existing rows are validated by the ADD.

ALTER TABLE public.org_brand_identities
    DROP CONSTRAINT IF EXISTS org_brand_identities_tokens_schema;

ALTER TABLE public.org_brand_identities
    ADD CONSTRAINT org_brand_identities_tokens_schema
        CHECK (coalesce(tokens->>'schema', '') = 'noctus.brand-tokens/v1');
