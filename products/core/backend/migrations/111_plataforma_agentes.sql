-- ============================================================================
-- 111: public.plataforma_agentes -- the registry of the AI calls the PLATFORM itself makes to a vendor.
--
-- One row per call (chave): the whole prompt + the model, edited by a platform admin through
-- /api/studio/plataforma/agentes and read by code through noctusai_lib.integrations.prompt_registry (prompt_e_modelo / chamar_ia). A row exists only
-- for a call that actually reads it. Platform-wide (no org_id): SERVICE-ROLE ONLY -- RLS on, the single
-- service_role_bypass policy, no grant to authenticated / anon.
--
-- plataforma_agente_chamadas: one row per call made through the registry call helpers (tokens, USD cost, latency,
-- ok/error; never prompt or response text) so vendors and models can be compared. The central public.ai_usage ledger
-- (priced, attributed by feature 'plataforma.<chave>') has no latency column, hence this minimal table.
--
-- chave is a STABLE LOGICAL ID (dotted lowercase segments, e.g. agents.eval_improver, crm.lead_qualifier) -- never a
-- product slug or code path, so product renames/absorptions never fork rows. Per-market / per-org overrides, if ever
-- needed, are a later layer (market default, then org override) over these rows.
--
-- NOC-REMEDIATE[transition-log-primitive]: prompt/model edit history belongs to the seed transition-log primitive
-- (transition_log_migration(TransitionLogConfig(...))), not a hand-written versions table; this migration ships the
-- current-state row only (atualizado_em/atualizado_por) -- 2026-11-08
--
-- Seeded with exactly ONE row (agents.eval_improver); the prompt is a first draft the owner replaces.
-- Lives in core's public schema so EVERY product reads the same registry (service role only, via get_core_client).
-- ============================================================================

SET search_path = public;

CREATE TABLE IF NOT EXISTS public.plataforma_agentes (
    chave TEXT PRIMARY KEY CHECK (chave ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$' AND length(chave) <= 64),
    nome TEXT NOT NULL CHECK (length(nome) BETWEEN 1 AND 120),
    descricao TEXT NOT NULL DEFAULT '',
    vendor TEXT NOT NULL CHECK (vendor IN ('anthropic', 'openai')),
    modelo TEXT NOT NULL CHECK (length(modelo) BETWEEN 1 AND 80),
    capacidade TEXT NOT NULL DEFAULT 'chat' CHECK (capacidade IN ('chat', 'vision', 'transcription')),
    prompt TEXT NOT NULL CHECK (length(prompt) <= 100000),
    ativo BOOLEAN NOT NULL DEFAULT true,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_por UUID NULL
);

ALTER TABLE public.plataforma_agentes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.plataforma_agentes;
CREATE POLICY "service_role_bypass" ON public.plataforma_agentes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON public.plataforma_agentes FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.plataforma_agentes TO service_role;
COMMENT ON TABLE public.plataforma_agentes IS 'tier:platform';

CREATE TABLE IF NOT EXISTS public.plataforma_agente_chamadas (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chave TEXT NOT NULL REFERENCES public.plataforma_agentes (chave) ON DELETE CASCADE,
    vendor TEXT NOT NULL,
    modelo TEXT NOT NULL,
    tokens_entrada INTEGER NULL CHECK (tokens_entrada IS NULL OR tokens_entrada >= 0),
    tokens_saida INTEGER NULL CHECK (tokens_saida IS NULL OR tokens_saida >= 0),
    custo_usd NUMERIC(14, 8) NULL CHECK (custo_usd IS NULL OR custo_usd >= 0),
    latencia_ms INTEGER NOT NULL CHECK (latencia_ms >= 0),
    capacidade TEXT NOT NULL DEFAULT 'chat',
    ok BOOLEAN NOT NULL,
    erro TEXT NULL CHECK (erro IS NULL OR length(erro) <= 200),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS plataforma_agente_chamadas_chave_idx
    ON public.plataforma_agente_chamadas (chave, criado_em DESC);
ALTER TABLE public.plataforma_agente_chamadas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON public.plataforma_agente_chamadas;
CREATE POLICY "service_role_bypass" ON public.plataforma_agente_chamadas
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON public.plataforma_agente_chamadas FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.plataforma_agente_chamadas TO service_role;
COMMENT ON TABLE public.plataforma_agente_chamadas IS 'tier:platform';

INSERT INTO public.plataforma_agentes (chave, nome, descricao, vendor, modelo, prompt)
VALUES (
    'agents.eval_improver',
    'Avaliador e corretor de agentes',
    'Le as falhas de uma rodada de evals de um agente e decide as correcoes.',
    'anthropic',
    'claude-fable-5-1',
    $prompt$[PRIMEIRO RASCUNHO - SUBSTITUA ESTE TEXTO]

Voce avalia a rodada de evals de um agente e propoe as correcoes.

Voce recebe as falhas da rodada: para cada caso, a entrada, a saida esperada, a saida real e a nota do juiz.
Para cada falha, decida a causa provavel (instrucao ausente ou ambigua, conhecimento faltando, ferramenta mal
descrita, caso de eval mal escrito) e proponha a menor correcao que a resolve, dizendo qual parte do agente
muda (secao, texto, ferramenta, skill ou o proprio caso de eval).

Regras: nao invente fatos; cite o caso que motiva cada correcao; se as falhas nao permitem concluir, diga o que
falta saber em vez de adivinhar.$prompt$
)
ON CONFLICT (chave) DO NOTHING;
