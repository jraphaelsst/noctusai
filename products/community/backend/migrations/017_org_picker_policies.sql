-- Migration: 017_org_picker_policies
-- Schema(s): community
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- rollout to community, same shape as
-- social-wiring 211.
--
-- Every community RLS policy that resolved the caller's org through public.current_org_id()
-- now calls (SELECT public.current_org_id_for('community')): the home org for everyone, and
-- the platform-staff member's SELECTED org while they act in this product (core migration
-- 070). The schema literal is in the policy, never a request header.
--
-- Same command, roles, USING / WITH CHECK shape as the live policy: ALTER POLICY (no
-- drop/create gap, name + command + roles untouched); expression bodies generated from the
-- LIVE pg_policies of prod on 2026-10-09 (74 policies), cross-checked against the file walk
-- by the sibling test.
--
-- NOT converted, on purpose:
--   * storage.objects policies -- storage never acts; they stay HOME-ONLY on current_org_id().
--   * policies that carry no org identity (service-role `true` bypasses, status_pagina
--     producao/desenvolvimento, customer-only policies keyed on current_customer_org_id()
--     -- a customer never acts).
--   * the role checks (current_org_role(), community.eh_equipe()) read the CALLER's own noctus_users
--     row: the platform staff member's home role (owner/admin, platform org), which already
--     satisfies them while acting. They are role checks, not org identity.
--
-- DEPENDS ON core migration 070 (public.current_org_id_for). Fails loudly if absent.
-- Does NOT flip products.org_picker_ready (see 019).
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 017 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

ALTER POLICY aplicacao_perguntas_delete_own_org ON community.aplicacao_perguntas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacao_perguntas_insert_own_org ON community.aplicacao_perguntas
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacao_perguntas_select_own_org ON community.aplicacao_perguntas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacao_perguntas_update_own_org ON community.aplicacao_perguntas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacoes_delete_own_org ON community.aplicacoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacoes_insert_own_org ON community.aplicacoes
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacoes_select_own_org ON community.aplicacoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY aplicacoes_update_own_org ON community.aplicacoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY assinaturas_delete_own_org ON community.assinaturas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY assinaturas_insert_own_org ON community.assinaturas
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY assinaturas_select_own_org ON community.assinaturas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY assinaturas_update_own_org ON community.assinaturas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY configuracoes_cobranca_select_equipe ON community.configuracoes_cobranca
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY configuracoes_cobranca_write_equipe ON community.configuracoes_cobranca
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY credentials_select_own_org ON community.credentials
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY examples_delete_own_org ON community.examples
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY examples_insert_own_org ON community.examples
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY examples_select_own_org ON community.examples
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY examples_update_own_org ON community.examples
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_membros_delete_own_org ON community.grupo_membros
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_membros_insert_own_org ON community.grupo_membros
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_membros_select_own_org ON community.grupo_membros
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_membros_update_own_org ON community.grupo_membros
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_mensagens_delete_own_org ON community.grupo_mensagens
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_mensagens_insert_own_org ON community.grupo_mensagens
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_mensagens_select_own_org ON community.grupo_mensagens
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupo_mensagens_update_own_org ON community.grupo_mensagens
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupos_delete_own_org ON community.grupos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupos_insert_own_org ON community.grupos
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupos_select_own_org ON community.grupos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY grupos_update_own_org ON community.grupos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY gt_reservas_equipe ON community.grupoterapia_reservas
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY gt_sessoes_equipe ON community.grupoterapia_sessoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY invitations_select_own_org ON community.invitations
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lancamentos_equipe ON community.lancamentos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lote_itens_delete_own_org ON community.lote_itens
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lote_itens_insert_own_org ON community.lote_itens
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lote_itens_select_own_org ON community.lote_itens
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lote_itens_update_own_org ON community.lote_itens
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lotes_sincronizacao_delete_own_org ON community.lotes_sincronizacao
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lotes_sincronizacao_insert_own_org ON community.lotes_sincronizacao
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lotes_sincronizacao_select_own_org ON community.lotes_sincronizacao
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY lotes_sincronizacao_update_own_org ON community.lotes_sincronizacao
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY membro_eventos_insert_equipe ON community.membro_eventos
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY membro_eventos_select_equipe ON community.membro_eventos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY membros_delete_own_org ON community.membros
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY membros_insert_own_org ON community.membros
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY membros_select_own_org ON community.membros
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY membros_update_own_org ON community.membros
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY mensagem_flags_delete_own_org ON community.mensagem_flags
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY mensagem_flags_insert_own_org ON community.mensagem_flags
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY mensagem_flags_select_own_org ON community.mensagem_flags
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY mensagem_flags_update_own_org ON community.mensagem_flags
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY pagamentos_delete_own_org ON community.pagamentos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY pagamentos_insert_own_org ON community.pagamentos
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY pagamentos_select_own_org ON community.pagamentos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY pagamentos_update_own_org ON community.pagamentos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY plano_gateway_refs_delete_own_org ON community.plano_gateway_refs
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY plano_gateway_refs_insert_own_org ON community.plano_gateway_refs
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY plano_gateway_refs_select_own_org ON community.plano_gateway_refs
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY plano_gateway_refs_update_own_org ON community.plano_gateway_refs
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY planos_delete_own_org ON community.planos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY planos_insert_own_org ON community.planos
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY planos_select_own_org ON community.planos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY planos_update_own_org ON community.planos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissao_destinos_delete_own_org ON community.transmissao_destinos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissao_destinos_insert_own_org ON community.transmissao_destinos
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissao_destinos_select_own_org ON community.transmissao_destinos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissao_destinos_update_own_org ON community.transmissao_destinos
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissoes_delete_own_org ON community.transmissoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissoes_insert_own_org ON community.transmissoes
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissoes_select_own_org ON community.transmissoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY transmissoes_update_own_org ON community.transmissoes
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));

ALTER POLICY whatsapp_connections_select_own_org ON community.whatsapp_connections
  USING (((org_id = (SELECT public.current_org_id_for('community'))) AND community.eh_equipe()));
