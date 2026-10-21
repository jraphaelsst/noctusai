-- ============================================================================
-- 044_julia_v2_guardrails.sql -- Julia on a public WhatsApp line: output filters
-- and abuse escalation (docs: products/agents/projects/julia-v2/GUARDRAILS.md B3, B4).
--
-- 1. agents.conformidade_regras gets two CHECKs: `parametros` is a JSON object, and the
--    `escala_seguranca` thresholds (limiar_suspeito < limiar_handoff, integers 1..20) are
--    well formed when present. A malformed pair must be refused at the write, not
--    discovered at the lead's third attempt.
-- 2. The public-line rules are seeded ACTIVE and `bloquear` for every Julia INSTANCE
--    (agents.definition_scope = 'instancia'): link_nao_permitido, contato_nao_permitido,
--    pii_na_resposta, formato_suspeito, padroes_proibidos. Rule PARAMETERS are DATA, not
--    content shipped by code: padroes_proibidos / alegacao_identidade carry their regexes in
--    `parametros.padroes`; escala_seguranca carries the thresholds (2 / 3). The owner edits
--    them through the rule API; ON CONFLICT DO NOTHING keeps anything already tuned.
--    No wording ships here: correction texts are `agent_version_textos` rows (registry keys).
-- 3. Violations still hold codes and counts only (037); the new rules write the same shape.
--
-- Idempotent. NOT applied to any database by this slice -- the tech-lead applies it.
-- ============================================================================

SET search_path = agents, public;

-- ── 1. CHECKs ───────────────────────────────────────────────────────────────

ALTER TABLE agents.conformidade_regras DROP CONSTRAINT IF EXISTS conformidade_regras_parametros_objeto_check;
ALTER TABLE agents.conformidade_regras ADD CONSTRAINT conformidade_regras_parametros_objeto_check
    CHECK (jsonb_typeof(parametros) = 'object');

ALTER TABLE agents.conformidade_regras DROP CONSTRAINT IF EXISTS conformidade_regras_escala_limiares_check;
ALTER TABLE agents.conformidade_regras ADD CONSTRAINT conformidade_regras_escala_limiares_check
    CHECK (
        regra <> 'escala_seguranca'
        OR (
            CASE WHEN parametros ? 'limiar_suspeito'
                 THEN (parametros ->> 'limiar_suspeito') ~ '^([1-9]|1[0-9]|20)$' ELSE true END
            AND CASE WHEN parametros ? 'limiar_handoff'
                     THEN (parametros ->> 'limiar_handoff') ~ '^([1-9]|1[0-9]|20)$' ELSE true END
            AND CASE WHEN (parametros ->> 'limiar_suspeito') ~ '^([1-9]|1[0-9]|20)$'
                          AND (parametros ->> 'limiar_handoff') ~ '^([1-9]|1[0-9]|20)$'
                     THEN (parametros ->> 'limiar_suspeito')::int < (parametros ->> 'limiar_handoff')::int
                     ELSE true END
        )
    );

-- ── 2. rule defaults for the Julia instances (data, editable; never overwritten) ──

INSERT INTO agents.conformidade_regras (org_id, agent_id, regra, ativo, politica, parametros)
SELECT a.org_id, a.id, r.regra, true, r.politica, r.parametros
FROM agents.agents a
CROSS JOIN (VALUES
    ('link_nao_permitido',   'bloquear',  '{}'::jsonb),
    ('contato_nao_permitido','bloquear',  '{}'::jsonb),
    ('pii_na_resposta',      'bloquear',  '{}'::jsonb),
    ('formato_suspeito',     'bloquear',  '{"max_chars": 1200, "max_bullets": 6}'::jsonb),
    ('padroes_proibidos',    'bloquear',  jsonb_build_object('padroes', jsonb_build_array(
        'financiamento\s+(j[aá]\s+)?aprovad',
        'aprova(c[aã]o|do)?\s+garantid',
        'sem\s+consulta\s+(ao\s+)?(spc|serasa|cr[eé]dito)',
        '\bpix\b',
        '\bboleto\b',
        'taxa\s+de\s+reserva',
        'sinal\s+de\s+r\$',
        'transfer[eê]ncia\s+(banc[aá]ria|para|pra)',
        'c[oó]digo\s+de\s+(verifica|confirma|seguran)',
        'c[oó]digo\s+(que\s+(chegou|recebeu)|de\s+6)'
    ))),
    ('alegacao_identidade',  'registrar', jsonb_build_object('padroes', jsonb_build_array(
        '\b(sou|aqui\s+[eé])\b.{0,30}\b(o\s+|a\s+)?(dono|dona|propriet[aá]ri[oa]|diretor|diretora|gerente)\b.{0,30}\b(da|do|de)\b',
        '\b(sou|aqui\s+[eé])\b.{0,20}\b(corretor|corretora|atendente|funcion[aá]ri[oa])\b',
        '\b(suporte|equipe|time)\s+(da\s+)?noctus',
        '\b(sou|aqui\s+[eé])\b.{0,20}\b(policial|delegad[oa]|pol[ií]cia|promotor|juiz|ju[ií]za)\b',
        '\b(sou|aqui\s+[eé])\b.{0,20}\b(advogad[oa]|oficial\s+de\s+justi[cç]a)\b',
        '\bsou\s+da\s+imobili[aá]ria\b'
    ))),
    ('escala_seguranca',     'registrar', '{"limiar_suspeito": 2, "limiar_handoff": 3}'::jsonb)
) AS r(regra, politica, parametros)
WHERE a.definition_scope = 'instancia'
ON CONFLICT (agent_id, regra) DO NOTHING;
