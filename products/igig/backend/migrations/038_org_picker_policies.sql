-- Migration: 038_org_picker_policies
-- Schema(s): igig
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- rollout to igig, same shape as
-- social-wiring 211.
--
-- Every igig RLS policy that resolved the caller's org through public.current_org_id()
-- now calls (SELECT public.current_org_id_for('igig')): the home org for everyone, and
-- the platform-staff member's SELECTED org while they act in this product (core migration
-- 070). The schema literal is in the policy, never a request header.
--
-- Same command, roles, USING / WITH CHECK shape as the live policy: ALTER POLICY (no
-- drop/create gap, name + command + roles untouched); expression bodies generated from the
-- LIVE pg_policies of prod on 2026-10-09 (51 policies), cross-checked against the file walk
-- by the sibling test.
--
-- NOT converted, on purpose:
--   * storage.objects policies -- storage never acts; they stay HOME-ONLY on current_org_id().
--   * policies that carry no org identity (service-role `true` bypasses, status_pagina
--     producao/desenvolvimento, customer-only policies keyed on current_customer_org_id()
--     -- a customer never acts).
--   * the role checks (current_org_role()) read the CALLER's own noctus_users
--     row: the platform staff member's home role (owner/admin, platform org), which already
--     satisfies them while acting. They are role checks, not org identity.
--
-- DEPENDS ON core migration 070 (public.current_org_id_for). Fails loudly if absent.
-- Does NOT flip products.org_picker_ready (see 040).
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 038 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

ALTER POLICY acesso_org_isolation ON igig.acesso
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY apontamento_org_isolation ON igig.apontamento
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY aprovacao_org_isolation ON igig.aprovacao
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY automacao_org_isolation ON igig.automacao
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY automacao_execucao_org_isolation ON igig.automacao_execucao
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_org_isolation ON igig.cliente
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_checklist_extras_select_own_org ON igig.cliente_checklist_extras
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_checklist_itens_select_own_org ON igig.cliente_checklist_itens
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_checklists_select_own_org ON igig.cliente_checklists
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_documento_acessos_select_own_org ON igig.cliente_documento_acessos
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_documentos_select_own_org ON igig.cliente_documentos
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_lembretes_select_own_org ON igig.cliente_lembretes
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_membros_select_own_org ON igig.cliente_membros
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_notas_select_own_org ON igig.cliente_notas
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_tag_links_select_own_org ON igig.cliente_tag_links
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cliente_tags_select_own_org ON igig.cliente_tags
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY cofre_revelacoes_org_isolation ON igig.cofre_revelacoes
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY contrato_org_isolation ON igig.contrato
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY credentials_select_own_org ON igig.credentials
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY fatura_org_isolation ON igig.fatura
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY fatura_item_org_isolation ON igig.fatura_item
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY funcao_org_isolation ON igig.funcao
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY gmail_watch_org_isolation ON igig.gmail_watch
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY integracao_org_isolation ON igig.integracao
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY invitations_select_own_org ON igig.invitations
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY lead_org_isolation ON igig.lead
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY marca_org_isolation ON igig.marca
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY metrica_org_isolation ON igig.metrica
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_org_isolation ON igig.negocio
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_checklist_extras_select_own_org ON igig.negocio_checklist_extras
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_checklist_itens_select_own_org ON igig.negocio_checklist_itens
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_checklists_select_own_org ON igig.negocio_checklists
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_documento_acessos_select_own_org ON igig.negocio_documento_acessos
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_documentos_select_own_org ON igig.negocio_documentos
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_lembretes_select_own_org ON igig.negocio_lembretes
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_membros_select_own_org ON igig.negocio_membros
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_notas_select_own_org ON igig.negocio_notas
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_tag_links_select_own_org ON igig.negocio_tag_links
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY negocio_tags_select_own_org ON igig.negocio_tags
  USING ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY orcamento_org_isolation ON igig.orcamento
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY orcamento_email_org_isolation ON igig.orcamento_email
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY orcamento_item_org_isolation ON igig.orcamento_item
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY pauta_org_isolation ON igig.pauta
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY pauta_slot_gerado_org_isolation ON igig.pauta_slot_gerado
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY peca_org_isolation ON igig.peca
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY pipeline_movimentos_org_isolation ON igig.pipeline_movimentos
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY pipeline_stages_org_isolation ON igig.pipeline_stages
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY produto_servico_org_isolation ON igig.produto_servico
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY profissional_org_isolation ON igig.profissional
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY publicacao_org_isolation ON igig.publicacao
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));

ALTER POLICY tarefa_org_isolation ON igig.tarefa
  USING ((org_id = (SELECT public.current_org_id_for('igig'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('igig'))));
