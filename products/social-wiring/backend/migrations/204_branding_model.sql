-- ============================================================================
-- Migration 204 · social_wiring: Branding — the richer brand-kit model
-- ============================================================================
-- Owner decisions 2026-10-05 (products/social-wiring/projects/core-studio/
-- DECISIONS.md, "Branding" + "Branding data"):
--   * "Kits de marca" becomes Branding: several clients, several design
--     systems, each with the RICH model (tokens, brand book, components, logos,
--     references) — in the DATABASE ONLY. No repo catalog, no link to an
--     external artifact (deleting an artifact must not break anything).
--   * The Branding Template is a ROW (`is_template`); "create branding from
--     template" copies it.
--   * Owners are BRANDS (`marcas`), not only people. `mc_brand_kits.marca_id`
--     (the column migration 046 renamed from `client_id`) is the link.
--
-- SHAPE
--   mc_brand_kits         + tokens JSONB       the design system's tokens.json
--                                              (validated server-side)
--                         + brand_book TEXT    the README markdown
--                         + sections JSONB     extra markdown sections
--                                              [{title, markdown}]
--                         + is_template BOOL   the org's Branding Template row
--   mc_brand_components   one row per design-system component: name, guideline
--                         markdown, preview html (rendered ONLY in a sandboxed
--                         iframe, never in the page DOM)
--   mc_brand_references   + storage_path / content_type / size_bytes: the same
--                         "references" mechanism now also carries UPLOADED
--                         assets (logos, post models, fonts) in a PRIVATE bucket
--                         (signed URLs minted per request). kind gains 'logo'
--                         and 'font'.
--   storage bucket        social-wiring-branding (PRIVATE, org-first keys,
--                         object RLS on the first path segment — the 127 shape)
--
-- `design_tokens` (migration 002) is UNTOUCHED: it remains the explicit,
-- FLAT override the SVG render mode reads (design/tokens.py). `tokens` is the
-- structured brand model; they are deliberately separate columns.
--
-- FORWARD-ONLY, IDEMPOTENT. 🔴 MIGRATION FILE ONLY — not applied to any DB by
-- this change. Apply via noctus.dev.migrate_product with explicit consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ── 1. mc_brand_kits: the rich model ───────────────────────────────────────
ALTER TABLE social_wiring.mc_brand_kits
    ADD COLUMN IF NOT EXISTS tokens      JSONB,
    ADD COLUMN IF NOT EXISTS brand_book  TEXT    NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS sections    JSONB   NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS is_template BOOLEAN NOT NULL DEFAULT false;

-- The marca link is `marca_id` (046). A branding that predates it may only
-- carry the legacy `brand_owner_id` (same UUIDs as the marca — 007 folded the
-- owner table into the marca table UUID-preserving): backfill, never overwrite.
UPDATE social_wiring.mc_brand_kits
   SET marca_id = brand_owner_id
 WHERE marca_id IS NULL
   AND brand_owner_id IS NOT NULL
   AND EXISTS (SELECT 1 FROM social_wiring.marcas m
                WHERE m.id = mc_brand_kits.brand_owner_id);

-- At most ONE Branding Template per org; the template belongs to no marca.
CREATE UNIQUE INDEX IF NOT EXISTS mc_brand_kits_one_template_per_org
    ON social_wiring.mc_brand_kits (org_id)
    WHERE is_template;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'mc_brand_kits_template_has_no_marca'
                    AND conrelid = 'social_wiring.mc_brand_kits'::regclass) THEN
    ALTER TABLE social_wiring.mc_brand_kits
        ADD CONSTRAINT mc_brand_kits_template_has_no_marca
        CHECK (NOT is_template OR marca_id IS NULL);
  END IF;
END
$$;

-- A branding is unique per (org, marca, slug) — 007 already indexes that for
-- marca-owned kits (NULLs are distinct there). Brandings with NO marca (the
-- template, an unassigned legacy kit) need their own uniqueness so an import
-- keyed on slug cannot duplicate them.
CREATE UNIQUE INDEX IF NOT EXISTS mc_brand_kits_unowned_slug_uniq
    ON social_wiring.mc_brand_kits (org_id, slug)
    WHERE marca_id IS NULL AND slug IS NOT NULL;

COMMENT ON COLUMN social_wiring.mc_brand_kits.tokens IS
    'The design system''s tokens.json (color themes + tokens, type families/'
    'groups, spacing/radius/other scales). Validated by the backend '
    '(branding/tokens_schema.py) — never trust a row not written through it.';
COMMENT ON COLUMN social_wiring.mc_brand_kits.design_tokens IS
    'FLAT override read ONLY by the SVG render mode (design/tokens.py). Not '
    'derived from `tokens`: a brand''s fonts are not necessarily bundled faces.';

-- ── 2. mc_brand_components ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.mc_brand_components (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    brand_kit_id  UUID NOT NULL
        REFERENCES social_wiring.mc_brand_kits(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    guideline_md  TEXT NOT NULL DEFAULT '',
    preview_html  TEXT NOT NULL DEFAULT '',
    position      INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (brand_kit_id, name)
);

ALTER TABLE social_wiring.mc_brand_components ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "mc_brand_components_select_own_org" ON social_wiring.mc_brand_components;
CREATE POLICY "mc_brand_components_select_own_org" ON social_wiring.mc_brand_components
    FOR SELECT TO authenticated
    USING (org_id = current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.mc_brand_components;
CREATE POLICY "service_role_bypass" ON social_wiring.mc_brand_components
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS ix_sw_mc_brand_components_kit
    ON social_wiring.mc_brand_components (brand_kit_id);
CREATE INDEX IF NOT EXISTS ix_sw_mc_brand_components_org
    ON social_wiring.mc_brand_components (org_id);

DROP TRIGGER IF EXISTS set_updated_at_mc_brand_components ON social_wiring.mc_brand_components;
CREATE TRIGGER set_updated_at_mc_brand_components
    BEFORE UPDATE ON social_wiring.mc_brand_components
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

COMMENT ON COLUMN social_wiring.mc_brand_components.preview_html IS
    'Untrusted markup (validated on write by branding/html_guard.py). The UI '
    'renders it ONLY inside a sandboxed iframe (srcdoc, no script permission) '
    '— never into the page DOM.';

-- ── 3. mc_brand_references: uploaded assets ────────────────────────────────
ALTER TABLE social_wiring.mc_brand_references
    ADD COLUMN IF NOT EXISTS storage_path TEXT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,
    ADD COLUMN IF NOT EXISTS size_bytes   BIGINT;

-- kind gains 'logo' and 'font' (001's inline CHECK carries the default name).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint
              WHERE conname = 'mc_brand_references_kind_check'
                AND conrelid = 'social_wiring.mc_brand_references'::regclass) THEN
    ALTER TABLE social_wiring.mc_brand_references
        DROP CONSTRAINT mc_brand_references_kind_check;
  END IF;
  ALTER TABLE social_wiring.mc_brand_references
      ADD CONSTRAINT mc_brand_references_kind_check
      CHECK (kind IN ('model','prompt','palette','typography','logo','font'));
END
$$;

-- A given uploaded file appears once per (branding, kind, label): the import
-- is keyed on it so re-importing a design system replaces, never duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS mc_brand_references_asset_uniq
    ON social_wiring.mc_brand_references (brand_kit_id, kind, label)
    WHERE storage_path IS NOT NULL;

-- ── 4. Private bucket for the uploaded assets (the 127 shape) ──────────────
INSERT INTO storage.buckets (id, name, public)
VALUES ('social-wiring-branding', 'social-wiring-branding', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "sw_branding_storage_select" ON storage.objects;
CREATE POLICY "sw_branding_storage_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'social-wiring-branding'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_branding_storage_insert" ON storage.objects;
CREATE POLICY "sw_branding_storage_insert" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'social-wiring-branding'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_branding_storage_update" ON storage.objects;
CREATE POLICY "sw_branding_storage_update" ON storage.objects
    FOR UPDATE TO authenticated
    USING (
        bucket_id = 'social-wiring-branding'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_branding_storage_delete" ON storage.objects;
CREATE POLICY "sw_branding_storage_delete" ON storage.objects
    FOR DELETE TO authenticated
    USING (
        bucket_id = 'social-wiring-branding'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "sw_branding_storage_service" ON storage.objects;
CREATE POLICY "sw_branding_storage_service" ON storage.objects
    FOR ALL TO service_role
    USING (bucket_id = 'social-wiring-branding')
    WITH CHECK (bucket_id = 'social-wiring-branding');
