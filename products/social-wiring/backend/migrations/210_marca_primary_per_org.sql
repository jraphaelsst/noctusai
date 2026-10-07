-- 210 — an org OWNS its brand: one primary marca per org, one primary kit per marca
--
-- Owner decision 2026-10-07: every client is its own org with its own visual
-- identity, and an org's products inherit it (Store is Gilson's product and
-- wears his identity; Nós no Limiar is Mônica's product and wears hers).
-- A marca stays the brand record (it also owns connected accounts, 046), so
-- "the org's brand" is a FLAG on it, never a FK from public.organizations
-- into a product schema. Same idiom as integration_accounts.is_default (005)
-- and mc_brand_kits.is_template (204): a partial unique index.

ALTER TABLE social_wiring.marcas
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN social_wiring.marcas.is_primary IS
    'The org''s own brand identity (at most one per org); the org''s products inherit it.';
CREATE UNIQUE INDEX IF NOT EXISTS uq_marcas_one_primary_per_org
    ON social_wiring.marcas (org_id) WHERE is_primary;

ALTER TABLE social_wiring.mc_brand_kits
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN social_wiring.mc_brand_kits.is_primary IS
    'The marca''s canonical kit (at most one per marca) — the identity its products render.';
CREATE UNIQUE INDEX IF NOT EXISTS uq_mc_brand_kits_one_primary_per_marca
    ON social_wiring.mc_brand_kits (marca_id) WHERE is_primary;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'mc_brand_kits_primary_has_marca') THEN
        ALTER TABLE social_wiring.mc_brand_kits
            ADD CONSTRAINT mc_brand_kits_primary_has_marca
            CHECK (NOT is_primary OR (marca_id IS NOT NULL AND NOT is_template));
    END IF;
END $$;
