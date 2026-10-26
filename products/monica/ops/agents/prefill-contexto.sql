-- ============================================================================
-- Contexto de Mônica Tangerino -- pré-preenchimento (PREPARED, NOT APPLIED).
--
-- Preenche SOMENTE `quem_sou` e `instagram` do agente `monica-leads` na organização "Mônica Tangerino"
-- (fa80a1e0-1bcd-4c65-8a37-2162e8ffa688). O restante ela escreve na página Contexto do monica.
--
-- Pré-requisito: a definição `monica-leads` existir e declarar essas chaves (ops/agents/README.md, passo 1-3).
-- Nunca sobrescreve: se a Mônica já escreveu um valor, ON CONFLICT DO NOTHING o preserva. Idempotente.
-- Aplicar no Supabase (schema agents) depois do go-live -- o tech-lead aplica.
-- ============================================================================

INSERT INTO agents.agent_org_specs (org_id, agent_key, chave, valor)
VALUES
  ('fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'monica-leads', 'quem_sou',
   'Psicanalista. Fala sobre os assuntos importantes da vida pelas lentes da psicanálise.'),
  ('fa80a1e0-1bcd-4c65-8a37-2162e8ffa688', 'monica-leads', 'instagram',
   '@psimonicatangerino (profissional) · @monicatangerino (pessoal)')
ON CONFLICT (org_id, agent_key, chave) DO NOTHING;
