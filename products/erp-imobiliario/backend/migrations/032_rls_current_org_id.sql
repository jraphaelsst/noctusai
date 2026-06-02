-- ============================================================================
-- Migration 032 — Codify the live RLS fix: current_org_id() for erp schema
--
-- WHY THIS EXISTS
-- ---------------
-- All authenticated RLS policies in the erp schema authored before 2026-06-02
-- used the TOP-LEVEL JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This claim is ALWAYS NULL in Supabase — org_id lives under user_metadata,
-- not at the top level. The result: all authenticated user reads returned
-- 0 rows while service_role writes succeeded.
--
-- The erp.current_org_id() function was redefined LIVE on 2026-06-02 to read
-- from the trusted noctus_users table. This migration codifies the live state
-- by rewriting every erp table policy to call current_org_id() directly.
--
-- NOTE: The 001_erp_imobiliario.sql and subsequent migrations that created
-- these policies used the broken jwt() form. This migration is the forward-
-- only correction — it does NOT rewrite those files (migrations are immutable
-- once applied to prod).
--
-- PREREQUISITE: public.current_org_id() and erp.current_org_id() must exist.
-- These are defined in:
--   - products/seed/backend/migrations/001_seed.sql (public schema)
--   - products/social-wiring/backend/migrations/011_rls_current_org_id.sql
--     Section 1 (both public + erp)
--
-- IDEMPOTENT: all policies use DROP POLICY IF EXISTS before CREATE POLICY.
-- Re-running is safe.
--
-- SCOPE: 170 erp authenticated policies across 43 tables.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02. Live state is fully fixed (0 advisor warnings).
--
-- POINTER: memory/feedback_rls_never_key_on_user_metadata.md
-- ============================================================================

-- Ensure erp.current_org_id() is current (idempotent re-definition).
-- This is the canonical erp-schema copy of the trusted-table resolver.
CREATE OR REPLACE FUNCTION erp.current_org_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public', 'erp'
AS $f$
  SELECT org_id FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;

-- ----- erp.analises_credito -----
DROP POLICY IF EXISTS "analises_credito_delete_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_delete_policy" ON erp.analises_credito
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "analises_credito_insert_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_insert_policy" ON erp.analises_credito
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "analises_credito_select_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_select_policy" ON erp.analises_credito
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "analises_credito_update_policy" ON erp.analises_credito;
CREATE POLICY "analises_credito_update_policy" ON erp.analises_credito
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.assinaturas -----
DROP POLICY IF EXISTS "assinaturas_delete_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_delete_policy" ON erp.assinaturas
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "assinaturas_insert_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_insert_policy" ON erp.assinaturas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "assinaturas_select_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_select_policy" ON erp.assinaturas
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "assinaturas_update_policy" ON erp.assinaturas;
CREATE POLICY "assinaturas_update_policy" ON erp.assinaturas
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.campanhas -----
DROP POLICY IF EXISTS "campanhas_delete_policy" ON erp.campanhas;
CREATE POLICY "campanhas_delete_policy" ON erp.campanhas
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "campanhas_insert_policy" ON erp.campanhas;
CREATE POLICY "campanhas_insert_policy" ON erp.campanhas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "campanhas_select_policy" ON erp.campanhas;
CREATE POLICY "campanhas_select_policy" ON erp.campanhas
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "campanhas_update_policy" ON erp.campanhas;
CREATE POLICY "campanhas_update_policy" ON erp.campanhas
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.chamados_portal -----
DROP POLICY IF EXISTS "chamados_portal_delete_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_delete_policy" ON erp.chamados_portal
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chamados_portal_insert_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_insert_policy" ON erp.chamados_portal
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chamados_portal_select_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_select_policy" ON erp.chamados_portal
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chamados_portal_update_policy" ON erp.chamados_portal;
CREATE POLICY "chamados_portal_update_policy" ON erp.chamados_portal
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.chaves -----
DROP POLICY IF EXISTS "chaves_delete_policy" ON erp.chaves;
CREATE POLICY "chaves_delete_policy" ON erp.chaves
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chaves_insert_policy" ON erp.chaves;
CREATE POLICY "chaves_insert_policy" ON erp.chaves
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chaves_select_policy" ON erp.chaves;
CREATE POLICY "chaves_select_policy" ON erp.chaves
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chaves_update_policy" ON erp.chaves;
CREATE POLICY "chaves_update_policy" ON erp.chaves
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.chaves_historico -----
DROP POLICY IF EXISTS "chaves_historico_delete_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_delete_policy" ON erp.chaves_historico
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chaves_historico_insert_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_insert_policy" ON erp.chaves_historico
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chaves_historico_select_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_select_policy" ON erp.chaves_historico
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "chaves_historico_update_policy" ON erp.chaves_historico;
CREATE POLICY "chaves_historico_update_policy" ON erp.chaves_historico
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.checkins -----
DROP POLICY IF EXISTS "checkins_delete_policy" ON erp.checkins;
CREATE POLICY "checkins_delete_policy" ON erp.checkins
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "checkins_insert_policy" ON erp.checkins;
CREATE POLICY "checkins_insert_policy" ON erp.checkins
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "checkins_select_policy" ON erp.checkins;
CREATE POLICY "checkins_select_policy" ON erp.checkins
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "checkins_update_policy" ON erp.checkins;
CREATE POLICY "checkins_update_policy" ON erp.checkins
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.comissoes -----
DROP POLICY IF EXISTS "comissoes_delete_policy" ON erp.comissoes;
CREATE POLICY "comissoes_delete_policy" ON erp.comissoes
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "comissoes_insert_policy" ON erp.comissoes;
CREATE POLICY "comissoes_insert_policy" ON erp.comissoes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "comissoes_select_policy" ON erp.comissoes;
CREATE POLICY "comissoes_select_policy" ON erp.comissoes
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "comissoes_update_policy" ON erp.comissoes;
CREATE POLICY "comissoes_update_policy" ON erp.comissoes
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.comissoes_splits -----
DROP POLICY IF EXISTS "comissoes_splits_delete_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_delete_policy" ON erp.comissoes_splits
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "comissoes_splits_insert_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_insert_policy" ON erp.comissoes_splits
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "comissoes_splits_select_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_select_policy" ON erp.comissoes_splits
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "comissoes_splits_update_policy" ON erp.comissoes_splits;
CREATE POLICY "comissoes_splits_update_policy" ON erp.comissoes_splits
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.conquistas -----
DROP POLICY IF EXISTS "conquistas_delete_policy" ON erp.conquistas;
CREATE POLICY "conquistas_delete_policy" ON erp.conquistas
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "conquistas_insert_policy" ON erp.conquistas;
CREATE POLICY "conquistas_insert_policy" ON erp.conquistas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "conquistas_select_policy" ON erp.conquistas;
CREATE POLICY "conquistas_select_policy" ON erp.conquistas
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "conquistas_update_policy" ON erp.conquistas;
CREATE POLICY "conquistas_update_policy" ON erp.conquistas
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.contratos -----
DROP POLICY IF EXISTS "contratos_delete_policy" ON erp.contratos;
CREATE POLICY "contratos_delete_policy" ON erp.contratos
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "contratos_insert_policy" ON erp.contratos;
CREATE POLICY "contratos_insert_policy" ON erp.contratos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "contratos_select_policy" ON erp.contratos;
CREATE POLICY "contratos_select_policy" ON erp.contratos
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "contratos_update_policy" ON erp.contratos;
CREATE POLICY "contratos_update_policy" ON erp.contratos
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.contratos_locacao -----
DROP POLICY IF EXISTS "contratos_locacao_delete_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_delete_policy" ON erp.contratos_locacao
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "contratos_locacao_insert_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_insert_policy" ON erp.contratos_locacao
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "contratos_locacao_select_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_select_policy" ON erp.contratos_locacao
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "contratos_locacao_update_policy" ON erp.contratos_locacao;
CREATE POLICY "contratos_locacao_update_policy" ON erp.contratos_locacao
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.distribuicao_config -----
DROP POLICY IF EXISTS "distribuicao_config_delete_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_delete_policy" ON erp.distribuicao_config
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "distribuicao_config_insert_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_insert_policy" ON erp.distribuicao_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "distribuicao_config_select_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_select_policy" ON erp.distribuicao_config
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "distribuicao_config_update_policy" ON erp.distribuicao_config;
CREATE POLICY "distribuicao_config_update_policy" ON erp.distribuicao_config
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.document_templates -----
DROP POLICY IF EXISTS "document_templates_delete_policy" ON erp.document_templates;
CREATE POLICY "document_templates_delete_policy" ON erp.document_templates
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "document_templates_insert_policy" ON erp.document_templates;
CREATE POLICY "document_templates_insert_policy" ON erp.document_templates
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "document_templates_select_policy" ON erp.document_templates;
CREATE POLICY "document_templates_select_policy" ON erp.document_templates
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "document_templates_update_policy" ON erp.document_templates;
CREATE POLICY "document_templates_update_policy" ON erp.document_templates
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.documentos -----
DROP POLICY IF EXISTS "documentos_delete_policy" ON erp.documentos;
CREATE POLICY "documentos_delete_policy" ON erp.documentos
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "documentos_insert_policy" ON erp.documentos;
CREATE POLICY "documentos_insert_policy" ON erp.documentos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "documentos_select_policy" ON erp.documentos;
CREATE POLICY "documentos_select_policy" ON erp.documentos
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "documentos_update_policy" ON erp.documentos;
CREATE POLICY "documentos_update_policy" ON erp.documentos
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.email_templates -----
DROP POLICY IF EXISTS "email_templates_delete_policy" ON erp.email_templates;
CREATE POLICY "email_templates_delete_policy" ON erp.email_templates
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "email_templates_insert_policy" ON erp.email_templates;
CREATE POLICY "email_templates_insert_policy" ON erp.email_templates
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "email_templates_select_policy" ON erp.email_templates;
CREATE POLICY "email_templates_select_policy" ON erp.email_templates
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "email_templates_update_policy" ON erp.email_templates;
CREATE POLICY "email_templates_update_policy" ON erp.email_templates
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.emails -----
DROP POLICY IF EXISTS "emails_delete_policy" ON erp.emails;
CREATE POLICY "emails_delete_policy" ON erp.emails
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "emails_insert_policy" ON erp.emails;
CREATE POLICY "emails_insert_policy" ON erp.emails
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "emails_select_policy" ON erp.emails;
CREATE POLICY "emails_select_policy" ON erp.emails
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "emails_update_policy" ON erp.emails;
CREATE POLICY "emails_update_policy" ON erp.emails
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.envios_email -----
DROP POLICY IF EXISTS "envios_email_delete_policy" ON erp.envios_email;
CREATE POLICY "envios_email_delete_policy" ON erp.envios_email
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "envios_email_insert_policy" ON erp.envios_email;
CREATE POLICY "envios_email_insert_policy" ON erp.envios_email
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "envios_email_select_policy" ON erp.envios_email;
CREATE POLICY "envios_email_select_policy" ON erp.envios_email
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "envios_email_update_policy" ON erp.envios_email;
CREATE POLICY "envios_email_update_policy" ON erp.envios_email
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.eventos -----
-- NOTE: UPDATE policy is TO public (matches live pg_policies.polroles).
DROP POLICY IF EXISTS "eventos_delete_policy" ON erp.eventos;
CREATE POLICY "eventos_delete_policy" ON erp.eventos
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "eventos_insert_policy" ON erp.eventos;
CREATE POLICY "eventos_insert_policy" ON erp.eventos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "eventos_select_policy" ON erp.eventos;
CREATE POLICY "eventos_select_policy" ON erp.eventos
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "eventos_update_policy" ON erp.eventos;
CREATE POLICY "eventos_update_policy" ON erp.eventos
  FOR UPDATE TO public
  USING ((org_id = current_org_id()))
  WITH CHECK ((org_id = current_org_id()));

-- ----- erp.extratos_bancarios -----
DROP POLICY IF EXISTS "extratos_bancarios_delete_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_delete_policy" ON erp.extratos_bancarios
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "extratos_bancarios_insert_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_insert_policy" ON erp.extratos_bancarios
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "extratos_bancarios_select_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_select_policy" ON erp.extratos_bancarios
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "extratos_bancarios_update_policy" ON erp.extratos_bancarios;
CREATE POLICY "extratos_bancarios_update_policy" ON erp.extratos_bancarios
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.filiais -----
DROP POLICY IF EXISTS "filiais_delete_policy" ON erp.filiais;
CREATE POLICY "filiais_delete_policy" ON erp.filiais
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "filiais_insert_policy" ON erp.filiais;
CREATE POLICY "filiais_insert_policy" ON erp.filiais
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "filiais_select_policy" ON erp.filiais;
CREATE POLICY "filiais_select_policy" ON erp.filiais
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "filiais_update_policy" ON erp.filiais;
CREATE POLICY "filiais_update_policy" ON erp.filiais
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.impostos -----
DROP POLICY IF EXISTS "impostos_delete_policy" ON erp.impostos;
CREATE POLICY "impostos_delete_policy" ON erp.impostos
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "impostos_insert_policy" ON erp.impostos;
CREATE POLICY "impostos_insert_policy" ON erp.impostos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "impostos_select_policy" ON erp.impostos;
CREATE POLICY "impostos_select_policy" ON erp.impostos
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "impostos_update_policy" ON erp.impostos;
CREATE POLICY "impostos_update_policy" ON erp.impostos
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON erp.invitations;
CREATE POLICY "invitations_select_own_org" ON erp.invitations
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.lancamentos -----
-- NOTE: UPDATE policy is TO public (matches live pg_policies.polroles).
DROP POLICY IF EXISTS "lancamentos_delete_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_delete_policy" ON erp.lancamentos
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "lancamentos_insert_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_insert_policy" ON erp.lancamentos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "lancamentos_select_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_select_policy" ON erp.lancamentos
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "lancamentos_update_policy" ON erp.lancamentos;
CREATE POLICY "lancamentos_update_policy" ON erp.lancamentos
  FOR UPDATE TO public
  USING ((org_id = current_org_id()))
  WITH CHECK ((org_id = current_org_id()));

-- ----- erp.matricula_extracoes -----
-- NOTE: This policy had the broken jwt() form in the QUAL itself (not just the
-- role array). The live fix changed it to current_org_id() and TO authenticated.
-- The original migration used TO public — set to authenticated per the live fix.
DROP POLICY IF EXISTS "org_isolation" ON erp.matricula_extracoes;
CREATE POLICY "org_isolation" ON erp.matricula_extracoes
  FOR ALL TO authenticated
  USING ((org_id = current_org_id()))
  WITH CHECK ((org_id = current_org_id()));

-- ----- erp.meta_campanhas_sync -----
DROP POLICY IF EXISTS "meta_campanhas_sync_delete_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_delete_policy" ON erp.meta_campanhas_sync
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_campanhas_sync_insert_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_insert_policy" ON erp.meta_campanhas_sync
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_campanhas_sync_select_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_select_policy" ON erp.meta_campanhas_sync
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_campanhas_sync_update_policy" ON erp.meta_campanhas_sync;
CREATE POLICY "meta_campanhas_sync_update_policy" ON erp.meta_campanhas_sync
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.meta_config -----
DROP POLICY IF EXISTS "meta_config_delete_policy" ON erp.meta_config;
CREATE POLICY "meta_config_delete_policy" ON erp.meta_config
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_config_insert_policy" ON erp.meta_config;
CREATE POLICY "meta_config_insert_policy" ON erp.meta_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_config_select_policy" ON erp.meta_config;
CREATE POLICY "meta_config_select_policy" ON erp.meta_config
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_config_update_policy" ON erp.meta_config;
CREATE POLICY "meta_config_update_policy" ON erp.meta_config
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.meta_leads -----
DROP POLICY IF EXISTS "meta_leads_delete_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_delete_policy" ON erp.meta_leads
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_leads_insert_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_insert_policy" ON erp.meta_leads
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_leads_select_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_select_policy" ON erp.meta_leads
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "meta_leads_update_policy" ON erp.meta_leads;
CREATE POLICY "meta_leads_update_policy" ON erp.meta_leads
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.movimentacoes_bancarias -----
DROP POLICY IF EXISTS "movimentacoes_bancarias_delete_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_delete_policy" ON erp.movimentacoes_bancarias
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "movimentacoes_bancarias_insert_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_insert_policy" ON erp.movimentacoes_bancarias
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "movimentacoes_bancarias_select_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_select_policy" ON erp.movimentacoes_bancarias
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "movimentacoes_bancarias_update_policy" ON erp.movimentacoes_bancarias;
CREATE POLICY "movimentacoes_bancarias_update_policy" ON erp.movimentacoes_bancarias
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.notificacao_preferencias -----
DROP POLICY IF EXISTS "notificacao_preferencias_delete_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_delete_policy" ON erp.notificacao_preferencias
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "notificacao_preferencias_insert_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_insert_policy" ON erp.notificacao_preferencias
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "notificacao_preferencias_select_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_select_policy" ON erp.notificacao_preferencias
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "notificacao_preferencias_update_policy" ON erp.notificacao_preferencias;
CREATE POLICY "notificacao_preferencias_update_policy" ON erp.notificacao_preferencias
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.notificacoes -----
DROP POLICY IF EXISTS "notificacoes_delete_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_delete_policy" ON erp.notificacoes
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "notificacoes_insert_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_insert_policy" ON erp.notificacoes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "notificacoes_select_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_select_policy" ON erp.notificacoes
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "notificacoes_update_policy" ON erp.notificacoes;
CREATE POLICY "notificacoes_update_policy" ON erp.notificacoes
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.ordens_servico -----
DROP POLICY IF EXISTS "ordens_servico_delete_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_delete_policy" ON erp.ordens_servico
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "ordens_servico_insert_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_insert_policy" ON erp.ordens_servico
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "ordens_servico_select_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_select_policy" ON erp.ordens_servico
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "ordens_servico_update_policy" ON erp.ordens_servico;
CREATE POLICY "ordens_servico_update_policy" ON erp.ordens_servico
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.parcelas_contrato -----
DROP POLICY IF EXISTS "parcelas_contrato_delete_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_delete_policy" ON erp.parcelas_contrato
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "parcelas_contrato_insert_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_insert_policy" ON erp.parcelas_contrato
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "parcelas_contrato_select_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_select_policy" ON erp.parcelas_contrato
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "parcelas_contrato_update_policy" ON erp.parcelas_contrato;
CREATE POLICY "parcelas_contrato_update_policy" ON erp.parcelas_contrato
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.pontuacoes -----
DROP POLICY IF EXISTS "pontuacoes_delete_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_delete_policy" ON erp.pontuacoes
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "pontuacoes_insert_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_insert_policy" ON erp.pontuacoes
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "pontuacoes_select_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_select_policy" ON erp.pontuacoes
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "pontuacoes_update_policy" ON erp.pontuacoes;
CREATE POLICY "pontuacoes_update_policy" ON erp.pontuacoes
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.portal_acessos -----
DROP POLICY IF EXISTS "portal_acessos_delete_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_delete_policy" ON erp.portal_acessos
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "portal_acessos_insert_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_insert_policy" ON erp.portal_acessos
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "portal_acessos_select_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_select_policy" ON erp.portal_acessos
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "portal_acessos_update_policy" ON erp.portal_acessos;
CREATE POLICY "portal_acessos_update_policy" ON erp.portal_acessos
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.portal_tokens -----
DROP POLICY IF EXISTS "portal_tokens_delete_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_delete_policy" ON erp.portal_tokens
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "portal_tokens_insert_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_insert_policy" ON erp.portal_tokens
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "portal_tokens_select_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_select_policy" ON erp.portal_tokens
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "portal_tokens_update_policy" ON erp.portal_tokens;
CREATE POLICY "portal_tokens_update_policy" ON erp.portal_tokens
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.propostas -----
DROP POLICY IF EXISTS "propostas_delete_policy" ON erp.propostas;
CREATE POLICY "propostas_delete_policy" ON erp.propostas
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "propostas_insert_policy" ON erp.propostas;
CREATE POLICY "propostas_insert_policy" ON erp.propostas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "propostas_select_policy" ON erp.propostas;
CREATE POLICY "propostas_select_policy" ON erp.propostas
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "propostas_update_policy" ON erp.propostas;
CREATE POLICY "propostas_update_policy" ON erp.propostas
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.remessas -----
DROP POLICY IF EXISTS "remessas_delete_policy" ON erp.remessas;
CREATE POLICY "remessas_delete_policy" ON erp.remessas
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "remessas_insert_policy" ON erp.remessas;
CREATE POLICY "remessas_insert_policy" ON erp.remessas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "remessas_select_policy" ON erp.remessas;
CREATE POLICY "remessas_select_policy" ON erp.remessas
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "remessas_update_policy" ON erp.remessas;
CREATE POLICY "remessas_update_policy" ON erp.remessas
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.seguros -----
DROP POLICY IF EXISTS "seguros_delete_policy" ON erp.seguros;
CREATE POLICY "seguros_delete_policy" ON erp.seguros
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "seguros_insert_policy" ON erp.seguros;
CREATE POLICY "seguros_insert_policy" ON erp.seguros
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "seguros_select_policy" ON erp.seguros;
CREATE POLICY "seguros_select_policy" ON erp.seguros
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "seguros_update_policy" ON erp.seguros;
CREATE POLICY "seguros_update_policy" ON erp.seguros
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.site_config -----
-- NOTE: UPDATE policy is TO public (matches live pg_policies.polroles).
DROP POLICY IF EXISTS "site_config_delete_policy" ON erp.site_config;
CREATE POLICY "site_config_delete_policy" ON erp.site_config
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "site_config_insert_policy" ON erp.site_config;
CREATE POLICY "site_config_insert_policy" ON erp.site_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "site_config_select_policy" ON erp.site_config;
CREATE POLICY "site_config_select_policy" ON erp.site_config
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "site_config_update_policy" ON erp.site_config;
CREATE POLICY "site_config_update_policy" ON erp.site_config
  FOR UPDATE TO public
  USING ((org_id = current_org_id()))
  WITH CHECK ((org_id = current_org_id()));

-- ----- erp.vistorias -----
DROP POLICY IF EXISTS "vistorias_delete_policy" ON erp.vistorias;
CREATE POLICY "vistorias_delete_policy" ON erp.vistorias
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "vistorias_insert_policy" ON erp.vistorias;
CREATE POLICY "vistorias_insert_policy" ON erp.vistorias
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "vistorias_select_policy" ON erp.vistorias;
CREATE POLICY "vistorias_select_policy" ON erp.vistorias
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "vistorias_update_policy" ON erp.vistorias;
CREATE POLICY "vistorias_update_policy" ON erp.vistorias
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.vistorias_rapidas -----
DROP POLICY IF EXISTS "vistorias_rapidas_delete_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_delete_policy" ON erp.vistorias_rapidas
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "vistorias_rapidas_insert_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_insert_policy" ON erp.vistorias_rapidas
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "vistorias_rapidas_select_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_select_policy" ON erp.vistorias_rapidas
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "vistorias_rapidas_update_policy" ON erp.vistorias_rapidas;
CREATE POLICY "vistorias_rapidas_update_policy" ON erp.vistorias_rapidas
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));

-- ----- erp.whatsapp_config -----
-- NOTE: UPDATE policy is TO public (matches live pg_policies.polroles).
DROP POLICY IF EXISTS "whatsapp_config_delete_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_delete_policy" ON erp.whatsapp_config
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "whatsapp_config_insert_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_insert_policy" ON erp.whatsapp_config
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "whatsapp_config_select_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_select_policy" ON erp.whatsapp_config
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "whatsapp_config_update_policy" ON erp.whatsapp_config;
CREATE POLICY "whatsapp_config_update_policy" ON erp.whatsapp_config
  FOR UPDATE TO public
  USING ((org_id = current_org_id()))
  WITH CHECK ((org_id = current_org_id()));

-- ----- erp.whatsapp_messages -----
DROP POLICY IF EXISTS "whatsapp_messages_delete_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_delete_policy" ON erp.whatsapp_messages
  FOR DELETE TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "whatsapp_messages_insert_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_insert_policy" ON erp.whatsapp_messages
  FOR INSERT TO authenticated
  WITH CHECK ((org_id = current_org_id()));

DROP POLICY IF EXISTS "whatsapp_messages_select_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_select_policy" ON erp.whatsapp_messages
  FOR SELECT TO authenticated
  USING ((org_id = current_org_id()));

DROP POLICY IF EXISTS "whatsapp_messages_update_policy" ON erp.whatsapp_messages;
CREATE POLICY "whatsapp_messages_update_policy" ON erp.whatsapp_messages
  FOR UPDATE TO authenticated
  USING ((org_id = current_org_id()));
