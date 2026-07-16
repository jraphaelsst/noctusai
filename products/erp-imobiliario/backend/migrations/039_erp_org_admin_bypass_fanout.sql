-- ============================================================================
-- Migration 039 -- Org source-of-truth hardening (Phase 2 fan-out)
--
-- WHY THIS EXISTS
-- ---------------
-- Migration 038 hardened ONE pilot table (erp.matricula_extracoes): DB-derived
-- org_id DEFAULT + a platform-admin cross-org RLS bypass. This migration fans
-- that same shape out to the 43 other org-scoped erp-schema tables covered by
-- migration 032's current_org_id() audit (2026-06-02) -- the proven, live-schema-
-- sourced baseline for 'org_id = current_org_id()' policies in this schema.
--
-- Two changes per table, same as 038:
--   1. `ALTER COLUMN org_id SET DEFAULT erp.current_org_id()` -- an INSERT that
--      omits org_id is stamped with the caller's DB-derived org; a stale JWT
--      can no longer produce a NULL org_id / NOT NULL 500 (the incident this
--      roadmap opened on).
--   2. Every existing policy gains `OR public.is_platform_admin()` in USING
--      (and WITH CHECK, where present) -- the platform operator
--      (noctus_users.role='admin') sees/manages every org, in addition to the
--      existing per-org isolation. Nothing else about each policy's shape
--      changes -- same name, same action, same role grant, same base predicate.
--
-- OUT OF SCOPE (see products/erp-imobiliario/backend/migrations/
-- 027_erp_org_scoping_completion.sql lines 42-47 + this dispatch's return note):
--   - erp.clientes / erp.ativos / erp.metas -- NO org_id column today (scoped
--     via owner_id/usuario_id + role RLS instead); adding org_id is design work
--     for a follow-up (erp-rls-org-scope-redesign), not a mechanical fan-out.
--   - Any erp-schema table added/changed after the 032 audit (2026-06-02) that
--     this migration doesn't enumerate below (e.g. the metas/equipe_membros/
--     ai_feedback/ai_outputs/llm_usage/profiles/certidao_consultas family added
--     by migrations 014-030) -- NOT verified against a live pg_policies read in
--     this pass (no live-DB tool available to this dispatch). A follow-up pass
--     should re-run the same live-schema audit 032 used, confirm which of those
--     tables carry a genuine org_id-keyed policy, and fan the bypass to them too
--     before declaring the erp-schema fan-out complete.
--   - imobi_scheduling.* / storage.objects (migrations 033/035) -- different
--     schemas than `erp`; the roadmap's '74 tables' count is scoped to the erp
--     schema specifically (see roadmap Scope section).
--
-- PREREQUISITE: public.is_platform_admin() (migration 038) and erp.current_org_id()
-- (migration 032) must already exist.
--
-- IDEMPOTENT: DROP POLICY IF EXISTS before CREATE POLICY; ALTER ... SET DEFAULT.
-- ============================================================================

-- ----- erp.analises_credito -----
ALTER TABLE erp.analises_credito
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "analises_credito_delete_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_delete_policy" ON erp.analises_credito
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "analises_credito_insert_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_insert_policy" ON erp.analises_credito
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "analises_credito_select_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_select_policy" ON erp.analises_credito
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "analises_credito_update_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_update_policy" ON erp.analises_credito
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.assinaturas -----
ALTER TABLE erp.assinaturas
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "assinaturas_delete_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_delete_policy" ON erp.assinaturas
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "assinaturas_insert_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_insert_policy" ON erp.assinaturas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "assinaturas_select_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_select_policy" ON erp.assinaturas
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "assinaturas_update_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_update_policy" ON erp.assinaturas
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.campanhas -----
ALTER TABLE erp.campanhas
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "campanhas_delete_policy" ON erp.campanhas;
CREATE POLICY "campanhas_delete_policy" ON erp.campanhas
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "campanhas_insert_policy" ON erp.campanhas;
CREATE POLICY "campanhas_insert_policy" ON erp.campanhas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "campanhas_select_policy" ON erp.campanhas;
CREATE POLICY "campanhas_select_policy" ON erp.campanhas
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "campanhas_update_policy" ON erp.campanhas;
CREATE POLICY "campanhas_update_policy" ON erp.campanhas
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.chamados_portal -----
ALTER TABLE erp.chamados_portal
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "chamados_portal_delete_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_delete_policy" ON erp.chamados_portal
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chamados_portal_insert_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_insert_policy" ON erp.chamados_portal
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chamados_portal_select_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_select_policy" ON erp.chamados_portal
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chamados_portal_update_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_update_policy" ON erp.chamados_portal
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.chaves -----
ALTER TABLE erp.chaves
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "chaves_delete_policy" ON erp.chaves;
CREATE POLICY "chaves_delete_policy" ON erp.chaves
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chaves_insert_policy" ON erp.chaves;
CREATE POLICY "chaves_insert_policy" ON erp.chaves
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chaves_select_policy" ON erp.chaves;
CREATE POLICY "chaves_select_policy" ON erp.chaves
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chaves_update_policy" ON erp.chaves;
CREATE POLICY "chaves_update_policy" ON erp.chaves
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.chaves_historico -----
ALTER TABLE erp.chaves_historico
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "chaves_historico_delete_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_delete_policy" ON erp.chaves_historico
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chaves_historico_insert_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_insert_policy" ON erp.chaves_historico
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chaves_historico_select_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_select_policy" ON erp.chaves_historico
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "chaves_historico_update_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_update_policy" ON erp.chaves_historico
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.checkins -----
ALTER TABLE erp.checkins
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "checkins_delete_policy" ON erp.checkins;
CREATE POLICY "checkins_delete_policy" ON erp.checkins
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "checkins_insert_policy" ON erp.checkins;
CREATE POLICY "checkins_insert_policy" ON erp.checkins
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "checkins_select_policy" ON erp.checkins;
CREATE POLICY "checkins_select_policy" ON erp.checkins
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "checkins_update_policy" ON erp.checkins;
CREATE POLICY "checkins_update_policy" ON erp.checkins
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.comissoes -----
ALTER TABLE erp.comissoes
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "comissoes_delete_policy" ON erp.comissoes;
CREATE POLICY "comissoes_delete_policy" ON erp.comissoes
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "comissoes_insert_policy" ON erp.comissoes;
CREATE POLICY "comissoes_insert_policy" ON erp.comissoes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "comissoes_select_policy" ON erp.comissoes;
CREATE POLICY "comissoes_select_policy" ON erp.comissoes
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "comissoes_update_policy" ON erp.comissoes;
CREATE POLICY "comissoes_update_policy" ON erp.comissoes
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.comissoes_splits -----
ALTER TABLE erp.comissoes_splits
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "comissoes_splits_delete_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_delete_policy" ON erp.comissoes_splits
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "comissoes_splits_insert_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_insert_policy" ON erp.comissoes_splits
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "comissoes_splits_select_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_select_policy" ON erp.comissoes_splits
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "comissoes_splits_update_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_update_policy" ON erp.comissoes_splits
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.conquistas -----
ALTER TABLE erp.conquistas
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "conquistas_delete_policy" ON erp.conquistas;
CREATE POLICY "conquistas_delete_policy" ON erp.conquistas
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "conquistas_insert_policy" ON erp.conquistas;
CREATE POLICY "conquistas_insert_policy" ON erp.conquistas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "conquistas_select_policy" ON erp.conquistas;
CREATE POLICY "conquistas_select_policy" ON erp.conquistas
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "conquistas_update_policy" ON erp.conquistas;
CREATE POLICY "conquistas_update_policy" ON erp.conquistas
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.contratos -----
ALTER TABLE erp.contratos
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "contratos_delete_policy" ON erp.contratos;
CREATE POLICY "contratos_delete_policy" ON erp.contratos
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "contratos_insert_policy" ON erp.contratos;
CREATE POLICY "contratos_insert_policy" ON erp.contratos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "contratos_select_policy" ON erp.contratos;
CREATE POLICY "contratos_select_policy" ON erp.contratos
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "contratos_update_policy" ON erp.contratos;
CREATE POLICY "contratos_update_policy" ON erp.contratos
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.contratos_locacao -----
ALTER TABLE erp.contratos_locacao
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "contratos_locacao_delete_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_delete_policy" ON erp.contratos_locacao
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "contratos_locacao_insert_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_insert_policy" ON erp.contratos_locacao
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "contratos_locacao_select_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_select_policy" ON erp.contratos_locacao
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "contratos_locacao_update_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_update_policy" ON erp.contratos_locacao
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.distribuicao_config -----
ALTER TABLE erp.distribuicao_config
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "distribuicao_config_delete_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_delete_policy" ON erp.distribuicao_config
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "distribuicao_config_insert_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_insert_policy" ON erp.distribuicao_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "distribuicao_config_select_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_select_policy" ON erp.distribuicao_config
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "distribuicao_config_update_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_update_policy" ON erp.distribuicao_config
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.document_templates -----
ALTER TABLE erp.document_templates
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "document_templates_delete_policy" ON erp.document_templates;
CREATE POLICY "document_templates_delete_policy" ON erp.document_templates
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "document_templates_insert_policy" ON erp.document_templates;
CREATE POLICY "document_templates_insert_policy" ON erp.document_templates
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "document_templates_select_policy" ON erp.document_templates;
CREATE POLICY "document_templates_select_policy" ON erp.document_templates
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "document_templates_update_policy" ON erp.document_templates;
CREATE POLICY "document_templates_update_policy" ON erp.document_templates
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.documentos -----
ALTER TABLE erp.documentos
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "documentos_delete_policy" ON erp.documentos;
CREATE POLICY "documentos_delete_policy" ON erp.documentos
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "documentos_insert_policy" ON erp.documentos;
CREATE POLICY "documentos_insert_policy" ON erp.documentos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "documentos_select_policy" ON erp.documentos;
CREATE POLICY "documentos_select_policy" ON erp.documentos
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "documentos_update_policy" ON erp.documentos;
CREATE POLICY "documentos_update_policy" ON erp.documentos
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.email_templates -----
ALTER TABLE erp.email_templates
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "email_templates_delete_policy" ON erp.email_templates;
CREATE POLICY "email_templates_delete_policy" ON erp.email_templates
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "email_templates_insert_policy" ON erp.email_templates;
CREATE POLICY "email_templates_insert_policy" ON erp.email_templates
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "email_templates_select_policy" ON erp.email_templates;
CREATE POLICY "email_templates_select_policy" ON erp.email_templates
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "email_templates_update_policy" ON erp.email_templates;
CREATE POLICY "email_templates_update_policy" ON erp.email_templates
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.emails -----
ALTER TABLE erp.emails
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "emails_delete_policy" ON erp.emails;
CREATE POLICY "emails_delete_policy" ON erp.emails
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "emails_insert_policy" ON erp.emails;
CREATE POLICY "emails_insert_policy" ON erp.emails
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "emails_select_policy" ON erp.emails;
CREATE POLICY "emails_select_policy" ON erp.emails
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "emails_update_policy" ON erp.emails;
CREATE POLICY "emails_update_policy" ON erp.emails
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.envios_email -----
ALTER TABLE erp.envios_email
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "envios_email_delete_policy" ON erp.envios_email;
CREATE POLICY "envios_email_delete_policy" ON erp.envios_email
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "envios_email_insert_policy" ON erp.envios_email;
CREATE POLICY "envios_email_insert_policy" ON erp.envios_email
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "envios_email_select_policy" ON erp.envios_email;
CREATE POLICY "envios_email_select_policy" ON erp.envios_email
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "envios_email_update_policy" ON erp.envios_email;
CREATE POLICY "envios_email_update_policy" ON erp.envios_email
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.eventos -----
ALTER TABLE erp.eventos
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "eventos_delete_policy" ON erp.eventos;
CREATE POLICY "eventos_delete_policy" ON erp.eventos
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "eventos_insert_policy" ON erp.eventos;
CREATE POLICY "eventos_insert_policy" ON erp.eventos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "eventos_select_policy" ON erp.eventos;
CREATE POLICY "eventos_select_policy" ON erp.eventos
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "eventos_update_policy" ON erp.eventos;
CREATE POLICY "eventos_update_policy" ON erp.eventos
  FOR UPDATE TO public
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin())
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.extratos_bancarios -----
ALTER TABLE erp.extratos_bancarios
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "extratos_bancarios_delete_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_delete_policy" ON erp.extratos_bancarios
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "extratos_bancarios_insert_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_insert_policy" ON erp.extratos_bancarios
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "extratos_bancarios_select_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_select_policy" ON erp.extratos_bancarios
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "extratos_bancarios_update_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_update_policy" ON erp.extratos_bancarios
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.filiais -----
ALTER TABLE erp.filiais
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "filiais_delete_policy" ON erp.filiais;
CREATE POLICY "filiais_delete_policy" ON erp.filiais
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "filiais_insert_policy" ON erp.filiais;
CREATE POLICY "filiais_insert_policy" ON erp.filiais
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "filiais_select_policy" ON erp.filiais;
CREATE POLICY "filiais_select_policy" ON erp.filiais
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "filiais_update_policy" ON erp.filiais;
CREATE POLICY "filiais_update_policy" ON erp.filiais
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.impostos -----
ALTER TABLE erp.impostos
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "impostos_delete_policy" ON erp.impostos;
CREATE POLICY "impostos_delete_policy" ON erp.impostos
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "impostos_insert_policy" ON erp.impostos;
CREATE POLICY "impostos_insert_policy" ON erp.impostos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "impostos_select_policy" ON erp.impostos;
CREATE POLICY "impostos_select_policy" ON erp.impostos
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "impostos_update_policy" ON erp.impostos;
CREATE POLICY "impostos_update_policy" ON erp.impostos
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.invitations -----
ALTER TABLE erp.invitations
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "invitations_select_own_org" ON erp.invitations;
CREATE POLICY "invitations_select_own_org" ON erp.invitations
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.lancamentos -----
ALTER TABLE erp.lancamentos
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "lancamentos_delete_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_delete_policy" ON erp.lancamentos
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "lancamentos_insert_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_insert_policy" ON erp.lancamentos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "lancamentos_select_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_select_policy" ON erp.lancamentos
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "lancamentos_update_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_update_policy" ON erp.lancamentos
  FOR UPDATE TO public
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin())
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.meta_campanhas_sync -----
ALTER TABLE erp.meta_campanhas_sync
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "meta_campanhas_sync_delete_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_delete_policy" ON erp.meta_campanhas_sync
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_campanhas_sync_insert_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_insert_policy" ON erp.meta_campanhas_sync
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_campanhas_sync_select_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_select_policy" ON erp.meta_campanhas_sync
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_campanhas_sync_update_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_update_policy" ON erp.meta_campanhas_sync
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.meta_config -----
ALTER TABLE erp.meta_config
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "meta_config_delete_policy" ON erp.meta_config;
CREATE POLICY "meta_config_delete_policy" ON erp.meta_config
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_config_insert_policy" ON erp.meta_config;
CREATE POLICY "meta_config_insert_policy" ON erp.meta_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_config_select_policy" ON erp.meta_config;
CREATE POLICY "meta_config_select_policy" ON erp.meta_config
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_config_update_policy" ON erp.meta_config;
CREATE POLICY "meta_config_update_policy" ON erp.meta_config
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.meta_leads -----
ALTER TABLE erp.meta_leads
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "meta_leads_delete_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_delete_policy" ON erp.meta_leads
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_leads_insert_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_insert_policy" ON erp.meta_leads
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_leads_select_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_select_policy" ON erp.meta_leads
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "meta_leads_update_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_update_policy" ON erp.meta_leads
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.movimentacoes_bancarias -----
ALTER TABLE erp.movimentacoes_bancarias
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "movimentacoes_bancarias_delete_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_delete_policy" ON erp.movimentacoes_bancarias
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "movimentacoes_bancarias_insert_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_insert_policy" ON erp.movimentacoes_bancarias
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "movimentacoes_bancarias_select_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_select_policy" ON erp.movimentacoes_bancarias
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "movimentacoes_bancarias_update_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_update_policy" ON erp.movimentacoes_bancarias
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.notificacao_preferencias -----
ALTER TABLE erp.notificacao_preferencias
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "notificacao_preferencias_delete_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_delete_policy" ON erp.notificacao_preferencias
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "notificacao_preferencias_insert_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_insert_policy" ON erp.notificacao_preferencias
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "notificacao_preferencias_select_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_select_policy" ON erp.notificacao_preferencias
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "notificacao_preferencias_update_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_update_policy" ON erp.notificacao_preferencias
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.notificacoes -----
ALTER TABLE erp.notificacoes
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "notificacoes_delete_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_delete_policy" ON erp.notificacoes
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "notificacoes_insert_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_insert_policy" ON erp.notificacoes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "notificacoes_select_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_select_policy" ON erp.notificacoes
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "notificacoes_update_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_update_policy" ON erp.notificacoes
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.ordens_servico -----
ALTER TABLE erp.ordens_servico
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "ordens_servico_delete_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_delete_policy" ON erp.ordens_servico
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "ordens_servico_insert_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_insert_policy" ON erp.ordens_servico
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "ordens_servico_select_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_select_policy" ON erp.ordens_servico
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "ordens_servico_update_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_update_policy" ON erp.ordens_servico
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.parcelas_contrato -----
ALTER TABLE erp.parcelas_contrato
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "parcelas_contrato_delete_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_delete_policy" ON erp.parcelas_contrato
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "parcelas_contrato_insert_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_insert_policy" ON erp.parcelas_contrato
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "parcelas_contrato_select_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_select_policy" ON erp.parcelas_contrato
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "parcelas_contrato_update_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_update_policy" ON erp.parcelas_contrato
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.pontuacoes -----
ALTER TABLE erp.pontuacoes
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "pontuacoes_delete_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_delete_policy" ON erp.pontuacoes
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "pontuacoes_insert_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_insert_policy" ON erp.pontuacoes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "pontuacoes_select_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_select_policy" ON erp.pontuacoes
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "pontuacoes_update_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_update_policy" ON erp.pontuacoes
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.portal_acessos -----
ALTER TABLE erp.portal_acessos
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "portal_acessos_delete_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_delete_policy" ON erp.portal_acessos
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "portal_acessos_insert_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_insert_policy" ON erp.portal_acessos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "portal_acessos_select_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_select_policy" ON erp.portal_acessos
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "portal_acessos_update_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_update_policy" ON erp.portal_acessos
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.portal_tokens -----
ALTER TABLE erp.portal_tokens
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "portal_tokens_delete_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_delete_policy" ON erp.portal_tokens
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "portal_tokens_insert_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_insert_policy" ON erp.portal_tokens
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "portal_tokens_select_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_select_policy" ON erp.portal_tokens
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "portal_tokens_update_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_update_policy" ON erp.portal_tokens
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.propostas -----
ALTER TABLE erp.propostas
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "propostas_delete_policy" ON erp.propostas;
CREATE POLICY "propostas_delete_policy" ON erp.propostas
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "propostas_insert_policy" ON erp.propostas;
CREATE POLICY "propostas_insert_policy" ON erp.propostas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "propostas_select_policy" ON erp.propostas;
CREATE POLICY "propostas_select_policy" ON erp.propostas
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "propostas_update_policy" ON erp.propostas;
CREATE POLICY "propostas_update_policy" ON erp.propostas
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.remessas -----
ALTER TABLE erp.remessas
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "remessas_delete_policy" ON erp.remessas;
CREATE POLICY "remessas_delete_policy" ON erp.remessas
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "remessas_insert_policy" ON erp.remessas;
CREATE POLICY "remessas_insert_policy" ON erp.remessas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "remessas_select_policy" ON erp.remessas;
CREATE POLICY "remessas_select_policy" ON erp.remessas
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "remessas_update_policy" ON erp.remessas;
CREATE POLICY "remessas_update_policy" ON erp.remessas
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.seguros -----
ALTER TABLE erp.seguros
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "seguros_delete_policy" ON erp.seguros;
CREATE POLICY "seguros_delete_policy" ON erp.seguros
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "seguros_insert_policy" ON erp.seguros;
CREATE POLICY "seguros_insert_policy" ON erp.seguros
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "seguros_select_policy" ON erp.seguros;
CREATE POLICY "seguros_select_policy" ON erp.seguros
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "seguros_update_policy" ON erp.seguros;
CREATE POLICY "seguros_update_policy" ON erp.seguros
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.site_config -----
ALTER TABLE erp.site_config
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "site_config_delete_policy" ON erp.site_config;
CREATE POLICY "site_config_delete_policy" ON erp.site_config
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "site_config_insert_policy" ON erp.site_config;
CREATE POLICY "site_config_insert_policy" ON erp.site_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "site_config_select_policy" ON erp.site_config;
CREATE POLICY "site_config_select_policy" ON erp.site_config
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "site_config_update_policy" ON erp.site_config;
CREATE POLICY "site_config_update_policy" ON erp.site_config
  FOR UPDATE TO public
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin())
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.vistorias -----
ALTER TABLE erp.vistorias
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "vistorias_delete_policy" ON erp.vistorias;
CREATE POLICY "vistorias_delete_policy" ON erp.vistorias
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "vistorias_insert_policy" ON erp.vistorias;
CREATE POLICY "vistorias_insert_policy" ON erp.vistorias
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "vistorias_select_policy" ON erp.vistorias;
CREATE POLICY "vistorias_select_policy" ON erp.vistorias
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "vistorias_update_policy" ON erp.vistorias;
CREATE POLICY "vistorias_update_policy" ON erp.vistorias
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.vistorias_rapidas -----
ALTER TABLE erp.vistorias_rapidas
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "vistorias_rapidas_delete_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_delete_policy" ON erp.vistorias_rapidas
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "vistorias_rapidas_insert_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_insert_policy" ON erp.vistorias_rapidas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "vistorias_rapidas_select_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_select_policy" ON erp.vistorias_rapidas
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "vistorias_rapidas_update_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_update_policy" ON erp.vistorias_rapidas
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.whatsapp_config -----
ALTER TABLE erp.whatsapp_config
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "whatsapp_config_delete_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_delete_policy" ON erp.whatsapp_config
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "whatsapp_config_insert_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_insert_policy" ON erp.whatsapp_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "whatsapp_config_select_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_select_policy" ON erp.whatsapp_config
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "whatsapp_config_update_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_update_policy" ON erp.whatsapp_config
  FOR UPDATE TO public
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin())
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());


-- ----- erp.whatsapp_messages -----
ALTER TABLE erp.whatsapp_messages
  ALTER COLUMN org_id SET DEFAULT erp.current_org_id();

DROP POLICY IF EXISTS "whatsapp_messages_delete_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_delete_policy" ON erp.whatsapp_messages
  FOR DELETE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "whatsapp_messages_insert_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_insert_policy" ON erp.whatsapp_messages
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "whatsapp_messages_select_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_select_policy" ON erp.whatsapp_messages
  FOR SELECT TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

DROP POLICY IF EXISTS "whatsapp_messages_update_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_update_policy" ON erp.whatsapp_messages
  FOR UPDATE TO authenticated
  USING ((org_id = erp.current_org_id()) OR public.is_platform_admin());

