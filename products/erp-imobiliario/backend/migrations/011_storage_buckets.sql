-- Migration 011: Supabase Storage Buckets
-- Creates initial buckets used by the ERP StorageService.
-- Additional buckets will be added as features require them.

-- 1. Create buckets
INSERT INTO storage.buckets (id, name, public)
VALUES
    ('erp-certidoes', 'erp-certidoes', true),
    ('erp-geral',     'erp-geral',     true)
ON CONFLICT (id) DO NOTHING;

-- 2. RLS policies for storage.objects
-- Files are stored under {org_id}/... so we scope access by checking
-- that the first path segment matches the user's org_id metadata.

-- Allow authenticated users to read files from their org
CREATE POLICY erp_storage_select ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = (auth.jwt() -> 'user_metadata' ->> 'org_id')
    );

-- Allow authenticated users to upload files to their org folder
CREATE POLICY erp_storage_insert ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = (auth.jwt() -> 'user_metadata' ->> 'org_id')
    );

-- Allow authenticated users to update their org's files
CREATE POLICY erp_storage_update ON storage.objects
    FOR UPDATE TO authenticated
    USING (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = (auth.jwt() -> 'user_metadata' ->> 'org_id')
    );

-- Allow authenticated users to delete their org's files
CREATE POLICY erp_storage_delete ON storage.objects
    FOR DELETE TO authenticated
    USING (
        bucket_id LIKE 'erp-%'
        AND (storage.foldername(name))[1] = (auth.jwt() -> 'user_metadata' ->> 'org_id')
    );

-- Service role bypass (for background processing like certidões)
CREATE POLICY erp_storage_service ON storage.objects
    FOR ALL
    USING (
        bucket_id LIKE 'erp-%'
        AND auth.role() = 'service_role'
    );
