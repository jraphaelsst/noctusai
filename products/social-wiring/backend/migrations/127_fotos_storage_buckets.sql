-- 127_fotos_storage_buckets.sql -- social_wiring: edicao-fotos storage
-- buckets + object-level RLS
--
-- Two private buckets, mirroring the shape + object-RLS pattern of
-- `057_card_hub_documentos.sql` (`erp-imobiliario`'s `011_storage_
-- buckets.sql` / `035_rls_storage_current_org_id.sql` origin):
--
--   - `edicao-fotos` -- per-org uploaded + edited photos. Path shape
--     `{org_id}/{lote_id}/{foto_id}/...` (plan §4: "`{org_id}/{lote_id}/
--     {foto_id}/...`"). Object RLS scopes on the FIRST path segment via
--     `storage.foldername(name)`, same predicate `fotos_fotos.org_id`
--     etc. use at the table level.
--   - `edicao-fotos-referencias` -- the GLOBAL reference-pool images
--     (before/after pairs). No org segment in the path -- platform scope,
--     matching `fotos_referencias` / `fotos_guias_estilo` (124). Read
--     open to every authenticated user (same "readable platform-wide,
--     writes service_role only" shape as the two tables it backs);
--     write/delete restricted to service_role (curator/platform-admin
--     gate is enforced at the API layer, not by object RLS, since
--     `photo_curator` is a Core cross-org permission grant with no
--     org-scoped predicate to key a storage policy on).
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

-- ----------------------------------------------------------------------------
-- 1. edicao-fotos -- org-scoped photo storage
-- ----------------------------------------------------------------------------

INSERT INTO storage.buckets (id, name, public)
VALUES ('edicao-fotos', 'edicao-fotos', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "ef_fotos_storage_select" ON storage.objects;
CREATE POLICY "ef_fotos_storage_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'edicao-fotos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "ef_fotos_storage_insert" ON storage.objects;
CREATE POLICY "ef_fotos_storage_insert" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'edicao-fotos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "ef_fotos_storage_update" ON storage.objects;
CREATE POLICY "ef_fotos_storage_update" ON storage.objects
    FOR UPDATE TO authenticated
    USING (
        bucket_id = 'edicao-fotos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "ef_fotos_storage_delete" ON storage.objects;
CREATE POLICY "ef_fotos_storage_delete" ON storage.objects
    FOR DELETE TO authenticated
    USING (
        bucket_id = 'edicao-fotos'
        AND (storage.foldername(name))[1] = public.current_org_id()::text
    );

DROP POLICY IF EXISTS "ef_fotos_storage_service" ON storage.objects;
CREATE POLICY "ef_fotos_storage_service" ON storage.objects
    FOR ALL TO service_role
    USING (bucket_id = 'edicao-fotos')
    WITH CHECK (bucket_id = 'edicao-fotos');

-- ----------------------------------------------------------------------------
-- 2. edicao-fotos-referencias -- global reference-pool images
-- ----------------------------------------------------------------------------

INSERT INTO storage.buckets (id, name, public)
VALUES ('edicao-fotos-referencias', 'edicao-fotos-referencias', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "ef_referencias_storage_select" ON storage.objects;
CREATE POLICY "ef_referencias_storage_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'edicao-fotos-referencias');

DROP POLICY IF EXISTS "ef_referencias_storage_service" ON storage.objects;
CREATE POLICY "ef_referencias_storage_service" ON storage.objects
    FOR ALL TO service_role
    USING (bucket_id = 'edicao-fotos-referencias')
    WITH CHECK (bucket_id = 'edicao-fotos-referencias');
