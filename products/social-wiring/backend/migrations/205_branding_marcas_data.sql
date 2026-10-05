-- ============================================================================
-- Migration 205 · social_wiring: Branding — the owner's marca data (DATA ONLY)
-- ============================================================================
-- Owner decisions 2026-10-05 (DECISIONS.md, "Branding data"), kept in its OWN
-- file so the data step can be reviewed apart from the schema (204).
--
--   * New marcas (owners are brands): Gilson Tangerino (pessoa_fisica),
--     Nós no Limiar (empresa), NoctusAI (empresa).
--   * The existing EMPTY brand kit "One Design"
--     (ddfd4c20-fdab-4466-94a0-21f411f55adc) is attached to One Consultoria
--     (c2b77620-c550-48e1-b789-b680c7e6bb0d), to be filled from the Branding
--     Template later.
--
-- SCOPE GUARD: every statement is bound to the owner's org
-- (6dd73140-74a4-41c6-aeff-bc94b5312b53) AND guarded on that org existing, so
-- the file is a NO-OP on any other database/org. Idempotent: marcas are keyed
-- on (org_id, slug) with ON CONFLICT DO NOTHING; the kit attach only fills an
-- EMPTY marca_id on a kit that has no content yet.
--
-- Depends on 204 only for the `marca_id` link semantics (the column itself is
-- 046's). FORWARD-ONLY. 🔴 MIGRATION FILE ONLY — not applied to any DB by this
-- change; apply via noctus.dev.migrate_product with explicit consent.
-- ============================================================================

SET search_path = social_wiring, public;

DO $$
DECLARE
  v_org CONSTANT uuid := '6dd73140-74a4-41c6-aeff-bc94b5312b53';
BEGIN
  -- No-op anywhere the owner's org does not exist.
  IF NOT EXISTS (SELECT 1 FROM public.organizations WHERE id = v_org) THEN
    RAISE NOTICE '205: org % not present — skipping (no-op).', v_org;
    RETURN;
  END IF;

  INSERT INTO social_wiring.marcas (org_id, slug, name, kind)
  VALUES
    (v_org, 'gilson-tangerino', 'Gilson Tangerino', 'pessoa_fisica'),
    (v_org, 'nos-no-limiar',    'Nós no Limiar',    'empresa'),
    (v_org, 'noctusai',         'NoctusAI',         'empresa')
  ON CONFLICT (org_id, slug) DO NOTHING;

  -- Attach the empty "One Design" kit to One Consultoria. Both ids must exist
  -- in the owner's org; an already-attached kit is left exactly as it is.
  UPDATE social_wiring.mc_brand_kits k
     SET marca_id = 'c2b77620-c550-48e1-b789-b680c7e6bb0d'
   WHERE k.id = 'ddfd4c20-fdab-4466-94a0-21f411f55adc'
     AND k.org_id = v_org
     AND k.marca_id IS NULL
     AND EXISTS (SELECT 1 FROM social_wiring.marcas m
                  WHERE m.id = 'c2b77620-c550-48e1-b789-b680c7e6bb0d'
                    AND m.org_id = v_org);
END
$$;
