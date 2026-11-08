-- ============================================================================
-- Migration 330 -- social_wiring: the Esteira card hub (cs_post_*) is service-only
-- (security triage 2026-11-07, fix-on-contact of the seed card_hub organ)
-- ============================================================================
-- WHY
-- ---
-- 241 generated the Esteira card hub with the old seed shape: own-org SELECT policies for `authenticated`
-- (keyed on current_org_id_for) on every cs_post_* table, FOR ALL TO authenticated on cs_equipe / cs_posts, and
-- four org-folder policies for `authenticated` on the private `sw-esteira` bucket. The SW frontend never reads these
-- through supabase-js (auth.getSession only; no .from/.schema/.storage/.channel); the backend uses the service-role
-- client with an explicit org_id. So the browser grant bought nothing but a direct path around the backend.
-- The seed organ (`card_hub_migration`) now emits the service-only shape by construction; this migration brings the
-- applied Esteira tables to it. Sibling of 328 (cliente_* card hub + sw_documentos bucket).
--
-- WHAT
--   1. DROP every authenticated policy on the cs_* hub tables and the 4 authenticated `sw-esteira` storage policies;
--      `sw-esteira_storage_service` and the service_role policies are KEPT.
--   2. REVOKE ALL on each table FROM PUBLIC, anon, authenticated; GRANT ALL TO service_role.
--   3. Tier declaration (`tier:org`) for every table touched.
-- 241 stays frozen. FORWARD-ONLY, IDEMPOTENT, no data change.
-- ============================================================================

SET search_path = social_wiring, public;

-- 1. policies naming a browser role
DROP POLICY IF EXISTS "cs_equipe_select_own_org" ON social_wiring.cs_equipe;
DROP POLICY IF EXISTS "cs_equipe_write_own_org" ON social_wiring.cs_equipe;
DROP POLICY IF EXISTS "cs_posts_select_own_org" ON social_wiring.cs_posts;
DROP POLICY IF EXISTS "cs_posts_write_own_org" ON social_wiring.cs_posts;
DROP POLICY IF EXISTS "cs_post_notas_select_own_org" ON social_wiring.cs_post_notas;
DROP POLICY IF EXISTS "cs_post_tags_select_own_org" ON social_wiring.cs_post_tags;
DROP POLICY IF EXISTS "cs_post_tag_links_select_own_org" ON social_wiring.cs_post_tag_links;
DROP POLICY IF EXISTS "cs_post_membros_select_own_org" ON social_wiring.cs_post_membros;
DROP POLICY IF EXISTS "cs_post_lembretes_select_own_org" ON social_wiring.cs_post_lembretes;
DROP POLICY IF EXISTS "cs_post_checklists_select_own_org" ON social_wiring.cs_post_checklists;
DROP POLICY IF EXISTS "cs_post_checklist_itens_select_own_org" ON social_wiring.cs_post_checklist_itens;
DROP POLICY IF EXISTS "cs_post_checklist_extras_select_own_org" ON social_wiring.cs_post_checklist_extras;
DROP POLICY IF EXISTS "cs_post_documentos_select_own_org" ON social_wiring.cs_post_documentos;
DROP POLICY IF EXISTS "cs_post_documento_acessos_select_own_org" ON social_wiring.cs_post_documento_acessos;
DROP POLICY IF EXISTS "cs_post_documento_tipos_select_authenticated" ON social_wiring.cs_post_documento_tipos;
DROP POLICY IF EXISTS "sw-esteira_storage_select" ON storage.objects;
DROP POLICY IF EXISTS "sw-esteira_storage_insert" ON storage.objects;
DROP POLICY IF EXISTS "sw-esteira_storage_update" ON storage.objects;
DROP POLICY IF EXISTS "sw-esteira_storage_delete" ON storage.objects;

-- 2. no table privilege for browser roles; the backend's service role keeps everything
REVOKE ALL ON TABLE social_wiring.cs_equipe FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_posts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_notas FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_tags FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_tag_links FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_membros FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_lembretes FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_checklists FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_checklist_itens FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_checklist_extras FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_documento_tipos FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_documentos FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_post_documento_acessos FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.cs_equipe TO service_role;
GRANT ALL ON TABLE social_wiring.cs_posts TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_notas TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_tags TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_tag_links TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_membros TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_lembretes TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_checklists TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_checklist_itens TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_checklist_extras TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_documento_tipos TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_documentos TO service_role;
GRANT ALL ON TABLE social_wiring.cs_post_documento_acessos TO service_role;

-- 3. access tier
COMMENT ON TABLE social_wiring.cs_equipe IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_posts IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_notas IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_tags IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_tag_links IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_membros IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_lembretes IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_checklists IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_checklist_itens IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_checklist_extras IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_documento_tipos IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_documentos IS 'tier:org';
COMMENT ON TABLE social_wiring.cs_post_documento_acessos IS 'tier:org';
