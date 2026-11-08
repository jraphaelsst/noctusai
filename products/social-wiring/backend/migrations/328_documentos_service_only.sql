-- ============================================================================
-- Migration 328 -- social_wiring: card-hub documents are service-only (security triage 2026-11-07, P1)
-- ============================================================================
-- WHY
-- ---
-- Private bucket `social-wiring-documentos` (ID documents, certidoes, ...) carried storage.objects policies
-- `sw_documentos_storage_{select,insert,update,delete}` (migration 057, frozen) granting `authenticated`
-- SELECT/INSERT/UPDATE/DELETE on the caller's org folder, keyed on `current_org_id()` -- NOT the product-scoped
-- `current_org_id_for('social_wiring')`. A browser could therefore skip the access audit (cliente_documento_acessos),
-- the soft-delete-with-reason and the retention sweep, and a product-blocked user kept file access.
-- The SW frontend uses supabase for auth.getSession() only (no .from/.schema/.storage); every file op goes through the
-- backend with the service-role client, and prod edge logs show only service_role on this bucket.
--
-- WHAT
--   1. DROP the 4 authenticated storage policies; `sw_documentos_storage_service` (057) is KEPT -> bucket service-only.
--   2. REVOKE ALL on every social_wiring.cliente_* card-hub table FROM anon, authenticated (the existing org SELECT
--      policies stay as a second layer). The backend reads/writes through the service-role admin client.
--   3. DROP the authenticated write policy on cliente_origens_excluidas (216): a browser write path to the exclusion list.
--   4. Default privileges: a FUTURE social_wiring table/sequence is not auto-granted to browser roles.
--   5. Tier declaration for every table touched.
-- FORWARD-ONLY, IDEMPOTENT, no data change. Migrations 056/057/083 stay frozen.
-- ============================================================================

SET search_path = social_wiring, public;

-- 1. bucket -> service-only
DROP POLICY IF EXISTS "sw_documentos_storage_select" ON storage.objects;
DROP POLICY IF EXISTS "sw_documentos_storage_insert" ON storage.objects;
DROP POLICY IF EXISTS "sw_documentos_storage_update" ON storage.objects;
DROP POLICY IF EXISTS "sw_documentos_storage_delete" ON storage.objects;

-- 3. browser write path on the exclusion list
DROP POLICY IF EXISTS "cliente_origens_excluidas_write_own_org" ON social_wiring.cliente_origens_excluidas;

-- 2. no table privilege for browser roles on the card-hub tables
REVOKE ALL ON TABLE social_wiring.cliente_campo_conflitos FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_checklist_extras FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_checklist_itens FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_checklists FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_documento_acessos FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_documento_checklist FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_documento_tipos FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_documentos FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_empresa_participacoes FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_imovel_interesses FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_lembretes FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_membros FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_merges FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_notas FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_origens_excluidas FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_revisao_rejeitadas FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_tag_links FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_tags FROM anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cliente_touches FROM anon, authenticated;

-- 4. future tables/sequences are not re-granted to browser roles
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA social_wiring REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA social_wiring REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- 5. access tier
COMMENT ON TABLE social_wiring.cliente_campo_conflitos IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_checklist_extras IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_checklist_itens IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_checklists IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_documento_acessos IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_documento_checklist IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_documento_tipos IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_documentos IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_empresa_participacoes IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_imovel_interesses IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_lembretes IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_membros IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_merges IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_notas IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_origens_excluidas IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_revisao_rejeitadas IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_tag_links IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_tags IS 'tier:org';
COMMENT ON TABLE social_wiring.cliente_touches IS 'tier:org';
