-- Migration: 211_org_picker_policies
-- Schema(s): social_wiring
--
-- ORG PICKER (projects/org-picker/CONTRACT.md) -- pilot RLS conversion.
--
-- Every social_wiring RLS policy that resolved the caller's org through
-- public.current_org_id() / current_user_org_id() / an inline noctus_users
-- subquery now calls (SELECT public.current_org_id_for('social_wiring')):
-- the home org for everyone, and the platform-staff member's SELECTED org
-- while they act in this product (core migration 070). The schema literal is
-- in the policy, never a request header.
--
-- Same command, roles, USING / WITH CHECK shape as the live policy: this is
-- ALTER POLICY (no drop/create gap, name + command + roles untouched), the
-- expression body generated from the LIVE pg_policies of prod (the file-walk
-- of 001..210 cross-checked against it; see the sibling test).
--
-- NOT converted, on purpose:
--   * storage.objects policies (sw_branding_storage_*, sw_documentos_storage_*,
--     ef_fotos_storage_*, ef_referencias_storage_*) -- storage never acts;
--     they stay HOME-ONLY on current_org_id().
--   * policies that only test is_platform_admin() / current_org_role() / true
--     / status -- they carry no org identity.
--   * the 5 *_admin policies (api_tokens x2, portal_receiver_tokens x2,
--     portal_lead_forward_targets) keep their `nu.org_id = <t>.org_id` +
--     owner/admin EXISTS: the org predicate is converted, the role check stays
--     home-keyed (a JWT-direct write while acting does not satisfy it; the
--     backend writes these through the service role).
--
-- DEPENDS ON core migration 070 (public.current_org_id_for). Fails loudly if
-- absent. Does NOT flip products.org_picker_ready -- the tech-lead does that
-- after verification.
--
-- KB § PATTERNS/backend/database-rls.md

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION
      'migration 211 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

-- SECDEF helper used by fotos_lotes / fotos_lotes_openai select policies: it
-- embedded the home-only org lookup, so it converts with them.
-- secdef-execute-ok: rls-helper fotos_lotes/fotos_lotes_openai select policies call it as the caller (EXECUTE must stay)
CREATE OR REPLACE FUNCTION social_wiring.fotos_lote_visivel(p_lote_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'social_wiring', 'public'
AS $function$
    SELECT public.is_platform_admin() OR EXISTS (
        SELECT 1 FROM social_wiring.fotos_lotes l
        WHERE l.id = p_lote_id
          AND l.org_id = (SELECT public.current_org_id_for('social_wiring'))
          AND (
              l.criado_por = (SELECT auth.uid())
              OR public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager'])
          )
    );
$function$;

ALTER POLICY ads_accounts_select_own_org ON social_wiring.ads_accounts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ads_activity_events_select_own_org ON social_wiring.ads_activity_events
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ads_insight_snapshots_select_own_org ON social_wiring.ads_insight_snapshots
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ads_objects_select_own_org ON social_wiring.ads_objects
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY agentes_financeiros_select_own_org ON social_wiring.agentes_financeiros
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY agentes_financeiros_write_own_org ON social_wiring.agentes_financeiros
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY api_token_audit_select_own_org ON social_wiring.api_token_audit
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY api_tokens_insert_own_org_admin ON social_wiring.api_tokens
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = api_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY api_tokens_select_own_org ON social_wiring.api_tokens
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY api_tokens_update_own_org_admin ON social_wiring.api_tokens
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = api_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY atendimento_agendamentos_select_own_org ON social_wiring.atendimento_agendamentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_campo_conflitos_select_own_org ON social_wiring.atendimento_campo_conflitos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_aditivo_parcelas_select_own_org ON social_wiring.atendimento_contrato_aditivo_parcelas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_aditivo_versao_acessos_select_own_org ON social_wiring.atendimento_contrato_aditivo_versao_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_aditivo_versoes_select_own_org ON social_wiring.atendimento_contrato_aditivo_versoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_aditivos_select_own_org ON social_wiring.atendimento_contrato_aditivos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_assinaturas_select_own_org ON social_wiring.atendimento_contrato_assinaturas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_matricula_atos_select_own_org ON social_wiring.atendimento_contrato_matricula_atos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_versao_acessos_select_own_org ON social_wiring.atendimento_contrato_versao_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contrato_versoes_select_own_org ON social_wiring.atendimento_contrato_versoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_contratos_select_own_org ON social_wiring.atendimento_contratos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_documento_acessos_select_own_org ON social_wiring.atendimento_documento_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_documentos_select_own_org ON social_wiring.atendimento_documentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_favorecidos_select_own_org ON social_wiring.atendimento_favorecidos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_financiamento_select_own_org ON social_wiring.atendimento_financiamento
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_imoveis_select_own_org ON social_wiring.atendimento_imoveis
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_intermediarios_select_own_org ON social_wiring.atendimento_intermediarios
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_negociacao_select_own_org ON social_wiring.atendimento_negociacao
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_negociacao_parcelas_select_own_org ON social_wiring.atendimento_negociacao_parcelas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_negociacao_termos_select_own_org ON social_wiring.atendimento_negociacao_termos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_parcela_favorecidos_select_own_org ON social_wiring.atendimento_parcela_favorecidos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_parcela_permuta_ativos_select_own_org ON social_wiring.atendimento_parcela_permuta_ativos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimento_partes_select_own_org ON social_wiring.atendimento_partes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY atendimentos_own_org ON social_wiring.atendimentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_enrollments_select_via_automation ON social_wiring.automation_enrollments
  USING ((automation_id IN ( SELECT automations.id
   FROM social_wiring.automations
  WHERE (automations.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY em_steps_select_via_automation ON social_wiring.automation_steps
  USING ((automation_id IN ( SELECT automations.id
   FROM social_wiring.automations
  WHERE (automations.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY em_automations_select_own_org ON social_wiring.automations
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_campaigns_select_own_org ON social_wiring.campaigns
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY campanha_imoveis_select_own_org ON social_wiring.campanha_imoveis
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY campanha_solicitacoes_select_own_org ON social_wiring.campanha_solicitacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY campanha_veiculacoes_select_own_org ON social_wiring.campanha_veiculacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY campanhas_select_own_org ON social_wiring.campanhas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_consultas_select_own_org ON social_wiring.certidao_consultas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_emissao_aprendizados_select_own_org ON social_wiring.certidao_emissao_aprendizados
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_emissao_observacoes_select_own_org ON social_wiring.certidao_emissao_observacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_matriz_linhas_select_own_org ON social_wiring.certidao_matriz_linhas_customizadas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_matriz_linhas_write_own_org ON social_wiring.certidao_matriz_linhas_customizadas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_resultado_acessos_select_own_org ON social_wiring.certidao_resultado_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY certidao_resultados_select_own_org ON social_wiring.certidao_resultados
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_campo_conflitos_select_own_org ON social_wiring.cliente_campo_conflitos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_checklist_extras_select_own_org ON social_wiring.cliente_checklist_extras
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_checklist_itens_select_own_org ON social_wiring.cliente_checklist_itens
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_checklists_select_own_org ON social_wiring.cliente_checklists
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_documento_acessos_select_own_org ON social_wiring.cliente_documento_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_documento_checklist_select_own_org ON social_wiring.cliente_documento_checklist
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_documentos_select_own_org ON social_wiring.cliente_documentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_empresa_participacoes_select_own_org ON social_wiring.cliente_empresa_participacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_imovel_interesses_select_own_org ON social_wiring.cliente_imovel_interesses
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_lembretes_select_own_org ON social_wiring.cliente_lembretes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_membros_select_own_org ON social_wiring.cliente_membros
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_merges_select_own_org ON social_wiring.cliente_merges
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_notas_select_own_org ON social_wiring.cliente_notas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_revisao_rejeitadas_select_own_org ON social_wiring.cliente_revisao_rejeitadas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_tag_links_select_own_org ON social_wiring.cliente_tag_links
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_tags_select_own_org ON social_wiring.cliente_tags
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY cliente_touches_select_own_org ON social_wiring.cliente_touches
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY clientes_select_own_org ON social_wiring.clientes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_list_members_select_via_list ON social_wiring.contact_list_members
  USING ((list_id IN ( SELECT contact_lists.id
   FROM social_wiring.contact_lists
  WHERE (contact_lists.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY em_lists_select_own_org ON social_wiring.contact_lists
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_contacts_select_own_org ON social_wiring.contacts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY contrato_testemunhas_select_own_org ON social_wiring.contrato_testemunhas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY contrato_testemunhas_write_own_org ON social_wiring.contrato_testemunhas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY conversation_messages_select_own_org ON social_wiring.conversation_messages
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY credentials_select_own_org ON social_wiring.credentials
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY documento_retencao_politicas_select ON social_wiring.documento_retencao_politicas
  USING (((org_id IS NULL) OR (org_id = (SELECT public.current_org_id_for('social_wiring')))));

ALTER POLICY empresa_campo_conflitos_select_own_org ON social_wiring.empresa_campo_conflitos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY empresa_documento_acessos_select_own_org ON social_wiring.empresa_documento_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY empresa_documentos_select_own_org ON social_wiring.empresa_documentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY empresas_select_own_org ON social_wiring.empresas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY extracao_validacoes_select_own_org ON social_wiring.extracao_validacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY fotos_avaliacoes_select_admins ON social_wiring.fotos_avaliacoes
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (public.current_org_role() = ANY (ARRAY['owner'::text, 'admin'::text, 'manager'::text]))));

ALTER POLICY fotos_conjuntos_regras_select_own_org ON social_wiring.fotos_conjuntos_regras
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY fotos_dataset_select_admins ON social_wiring.fotos_dataset
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (public.current_org_role() = ANY (ARRAY['owner'::text, 'admin'::text, 'manager'::text]))));

ALTER POLICY fotos_decisoes_select_visivel ON social_wiring.fotos_decisoes
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND social_wiring.fotos_lote_visivel(lote_id)));

ALTER POLICY fotos_edicoes_select_visivel ON social_wiring.fotos_edicoes
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND social_wiring.fotos_lote_visivel(lote_id)));

ALTER POLICY fotos_eventos_select_visivel ON social_wiring.fotos_eventos
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND social_wiring.fotos_lote_visivel(lote_id)));

ALTER POLICY fotos_fotos_select_visivel ON social_wiring.fotos_fotos
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND social_wiring.fotos_lote_visivel(lote_id)));

ALTER POLICY fotos_guias_efetivos_select_own_org ON social_wiring.fotos_guias_efetivos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY fotos_lotes_select_visivel ON social_wiring.fotos_lotes
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND social_wiring.fotos_lote_visivel(id)));

ALTER POLICY fotos_lotes_openai_select_visivel ON social_wiring.fotos_lotes_openai
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND social_wiring.fotos_lote_visivel(lote_id)));

ALTER POLICY fotos_notificacoes_preferencias_self ON social_wiring.fotos_notificacoes_preferencias
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (user_id = auth.uid())))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (user_id = auth.uid())));

ALTER POLICY fotos_org_settings_admin_write ON social_wiring.fotos_org_settings
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND ((public.current_org_role() = ANY (ARRAY['owner'::text, 'admin'::text, 'manager'::text])) OR public.is_platform_admin())))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND ((public.current_org_role() = ANY (ARRAY['owner'::text, 'admin'::text, 'manager'::text])) OR public.is_platform_admin())));

ALTER POLICY fotos_org_settings_select_own_org ON social_wiring.fotos_org_settings
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY fotos_regras_org_select_admins ON social_wiring.fotos_regras_org
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (public.current_org_role() = ANY (ARRAY['owner'::text, 'admin'::text, 'manager'::text]))));

ALTER POLICY identificador_canonizacoes_select_own_org ON social_wiring.identificador_canonizacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ig_media_select_own_org ON social_wiring.ig_media
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ig_media_snapshots_select_own_org ON social_wiring.ig_media_snapshots
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ig_metric_snapshots_select_own_org ON social_wiring.ig_metric_snapshots
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY ig_profile_snapshots_select_own_org ON social_wiring.ig_profile_snapshots
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imoveis_select_own_org ON social_wiring.imoveis
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_campo_conflitos_select_own_org ON social_wiring.imovel_campo_conflitos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_dados_select_own_org ON social_wiring.imovel_dados
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_documento_acessos_select_own_org ON social_wiring.imovel_documento_acessos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_documentos_select_own_org ON social_wiring.imovel_documentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_endereco_historico_select_own_org ON social_wiring.imovel_endereco_historico
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_endereco_historico_write_own_org ON social_wiring.imovel_endereco_historico
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_proprietarios_select_own_org ON social_wiring.imovel_proprietarios
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovel_registry_select_own_org ON social_wiring.imovel_registry
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovelweb_agencies_select_own_org ON social_wiring.imovelweb_agencies
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovelweb_lead_events_select_own_org ON social_wiring.imovelweb_lead_events
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY imovelweb_leads_select_own_org ON social_wiring.imovelweb_leads
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY integration_accounts_delete_own_org ON social_wiring.integration_accounts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY integration_accounts_insert_own_org ON social_wiring.integration_accounts
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY integration_accounts_select_own_org ON social_wiring.integration_accounts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY integration_accounts_update_own_org ON social_wiring.integration_accounts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY invitations_select_own_org ON social_wiring.invitations
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_campanhas_select_own_org ON social_wiring.lead_campanhas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_corretor_aliases_select_own_org ON social_wiring.lead_corretor_aliases
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_corretores_select_own_org ON social_wiring.lead_corretores
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_import_batches_select_own_org ON social_wiring.lead_import_batches
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_source_aliases_select_own_org ON social_wiring.lead_source_aliases
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_sources_select_own_org ON social_wiring.lead_sources
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY lead_vendas_select_own_org ON social_wiring.lead_vendas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY leads_select_own_org ON social_wiring.leads
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_clicks_select_via_send_log ON social_wiring.link_clicks
  USING ((send_log_id IN ( SELECT send_logs.id
   FROM social_wiring.send_logs
  WHERE (send_logs.org_id = (SELECT public.current_org_id_for('social_wiring'))))));

ALTER POLICY llm_usage_select_own_org ON social_wiring.llm_usage
  USING (((org_id IS NOT NULL) AND (org_id = (SELECT public.current_org_id_for('social_wiring')))));

ALTER POLICY mailchimp_connections_select_own_org ON social_wiring.mailchimp_connections
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY marcas_delete_own_org ON social_wiring.marcas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY marcas_insert_own_org ON social_wiring.marcas
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY marcas_select_own_org ON social_wiring.marcas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY marcas_update_own_org ON social_wiring.marcas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_abertura_blocos_select_own_org ON social_wiring.matricula_abertura_blocos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_ato_detalhes_select_own_org ON social_wiring.matricula_ato_detalhes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_atos_select_own_org ON social_wiring.matricula_atos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_extracao_arquivos_select_own_org ON social_wiring.matricula_extracao_arquivos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_extracoes_select_own_org ON social_wiring.matricula_extracoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_extracoes_write_own_org ON social_wiring.matricula_extracoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY matricula_qualificacoes_select_own_org ON social_wiring.matricula_qualificacoes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY mc_brand_components_select_own_org ON social_wiring.mc_brand_components
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY mc_brand_kits_select_own_org ON social_wiring.mc_brand_kits
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY mc_brand_owners_select_own_org ON social_wiring.mc_brand_owners_legacy
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY mc_brand_references_select_own_org ON social_wiring.mc_brand_references
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY mc_post_slides_select_own_org ON social_wiring.mc_post_slides
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY mc_posts_select_own_org ON social_wiring.mc_posts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY meta_ads_lead_forms_select_own_org ON social_wiring.meta_ads_lead_forms
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY meta_ads_leads_select_own_org ON social_wiring.meta_ads_leads
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY meta_webhook_events_select_own_org ON social_wiring.meta_webhook_events
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY n8n_folders_select_own_org ON social_wiring.n8n_folders
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY n8n_workflow_placement_select_own_org ON social_wiring.n8n_workflow_placement
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY negociacao_defaults_select_own_org ON social_wiring.negociacao_defaults
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY notification_log_select_own_org ON social_wiring.notification_log
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY notification_recipients_select_own_org ON social_wiring.notification_recipients
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY notification_recipients_write_own_org ON social_wiring.notification_recipients
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY olx_lead_events_select_own_org ON social_wiring.olx_lead_events
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY olx_leads_select_own_org ON social_wiring.olx_leads
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY org_dados_cadastrais_select_own_org ON social_wiring.org_dados_cadastrais
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY org_dados_cadastrais_write_own_org ON social_wiring.org_dados_cadastrais
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY org_testemunhas_select_own_org ON social_wiring.org_testemunhas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY org_testemunhas_write_own_org ON social_wiring.org_testemunhas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY permuta_ativos_select_own_org ON social_wiring.permuta_ativos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY permuta_ativos_write_own_org ON social_wiring.permuta_ativos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY permuta_interesses_select_own_org ON social_wiring.permuta_interesses
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY permuta_interesses_write_own_org ON social_wiring.permuta_interesses
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY permuta_matches_select_own_org ON social_wiring.permuta_matches
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY permuta_matches_write_own_org ON social_wiring.permuta_matches
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY pipeline_movimentos_own_org ON social_wiring.pipeline_movimentos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY pipeline_stages_own_org ON social_wiring.pipeline_stages
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY portal_lead_forward_targets_select_own_org ON social_wiring.portal_lead_forward_targets
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY portal_lead_forward_targets_write_own_org_admin ON social_wiring.portal_lead_forward_targets
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = portal_lead_forward_targets.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))))
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = portal_lead_forward_targets.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY portal_lead_forwards_select_own_org ON social_wiring.portal_lead_forwards
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY portal_receiver_tokens_insert_own_org_admin ON social_wiring.portal_receiver_tokens
  WITH CHECK (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = portal_receiver_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY portal_receiver_tokens_select_own_org ON social_wiring.portal_receiver_tokens
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY portal_receiver_tokens_update_own_org_admin ON social_wiring.portal_receiver_tokens
  USING (((org_id = (SELECT public.current_org_id_for('social_wiring'))) AND (EXISTS ( SELECT 1
   FROM public.noctus_users nu
  WHERE ((nu.id = ( SELECT auth.uid() AS uid)) AND (nu.org_id = portal_receiver_tokens.org_id) AND (nu.org_role = ANY (ARRAY['owner'::text, 'admin'::text])))))));

ALTER POLICY processos_venda_own_org ON social_wiring.processos_venda
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY roteiros_select_own_org ON social_wiring.roteiros
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_appt_req_svc_select_own_org ON social_wiring.sched_appointment_request_services
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_appt_requests_select_own_org ON social_wiring.sched_appointment_requests
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_appointments_select_own_org ON social_wiring.sched_appointments
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_condominiums_select_own_org ON social_wiring.sched_condominiums
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_crew_skills_select_own_org ON social_wiring.sched_crew_skills
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_pending_chat_select_own_org ON social_wiring.sched_pending_chat_identities
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_properties_select_own_org ON social_wiring.sched_properties
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_route_groups_select_own_org ON social_wiring.sched_route_groups
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_services_select_own_org ON social_wiring.sched_services
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_tool_call_audits_select_own_org ON social_wiring.sched_tool_call_audits
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY sched_users_select_own_org ON social_wiring.sched_users
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_send_logs_select_own_org ON social_wiring.send_logs
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_domains_select_own_org ON social_wiring.sender_domains
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_templates_select_own_org ON social_wiring.templates
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY em_unsubscribes_select_own_org ON social_wiring.unsubscribes
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY upload_jobs_insert_own_org ON social_wiring.upload_jobs
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY upload_jobs_select_own_org ON social_wiring.upload_jobs
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY upload_jobs_update_own_org ON social_wiring.upload_jobs
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))))
  WITH CHECK ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY video_cache_select_own_org ON social_wiring.video_cache
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY visitas_select_own_org ON social_wiring.visitas
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY whatsapp_chats_select_own_org ON social_wiring.whatsapp_chats
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY whatsapp_connections_select_own_org ON social_wiring.whatsapp_connections
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY youtube_channel_snapshots_select_own_org ON social_wiring.youtube_channel_snapshots
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY youtube_shorts_select_own_org ON social_wiring.youtube_shorts
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY youtube_video_snapshots_select_own_org ON social_wiring.youtube_video_snapshots
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));

ALTER POLICY youtube_videos_select_own_org ON social_wiring.youtube_videos
  USING ((org_id = (SELECT public.current_org_id_for('social_wiring'))));
