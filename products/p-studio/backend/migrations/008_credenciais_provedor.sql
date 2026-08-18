-- ============================================================================
-- 008_credenciais_provedor.sql — P Studio
-- Schema: p_studio
--
-- Tira a credencial do provedor de cobrança do `.env` e põe no banco,
-- cifrada em repouso, gerenciável pela UI.
--
-- POR QUE. Até aqui `ASAAS_API_KEY` / `ASAAS_WEBHOOK_TOKEN` viviam no `.env`
-- da raiz. Três consequências, todas observadas em 2026-08-18 contra o deploy
-- vivo:
--   1. Ninguém as configurou, e NADA reclamou — `BASELINE_REQUIRED_PROD_ENV`
--      (seed `deploy_config.py`) lista só `REDIS_SESSION_ENCRYPTION_KEY`, então
--      `predeploy_check` devolveu 7/7 verde com a integração inteira desligada.
--      O sintoma era o webhook em produção respondendo 503.
--   2. Trocar de chave (sandbox ↔ produção, ou rotação após vazamento) exigia
--      editar o `.env` do VPS e recriar o container.
--   3. O dono do estúdio não tem como fazer nada disso — e a chave é DELE.
--
-- A forma canônica da casa para "segredo de terceiro que precisa persistir" é
-- `noctusai_lib.security.token_store` (Protocol+Fake+Real+factory, Fernet
-- sobre uma coluna TEXT). Esta migration cria a tabela no formato que aquele
-- store espera; o lado Python é `app/services/credenciais.py`, mesmo commit.
-- Nenhum código de cripto ou de persistência é escrito aqui — é consumo de
-- seed, não fork. → `KB § PATTERNS/backend/seed-fake-real-adapter.md`
--
-- Forward-only e idempotente. Não edita nenhuma migration já aplicada.
-- ============================================================================

SET search_path = p_studio, public;


-- ============================================================================
-- 1. Credenciais cifradas — uma linha por (org, provedor+ambiente)
-- ============================================================================
--
-- Formato ditado pelo store do seed (`SupabaseCredentialStore`), que espera
-- exatamente: org_id, provider, encrypted_tokens, metadata, created_at,
-- updated_at, PK(org_id, provider). Divergir da forma esperada obrigaria a
-- passar `metadata_columns=` e a inventar mapeamento — custo sem ganho numa
-- tabela nova. Tabela nova ⇒ forma canônica.
--
-- `provider` carrega o AMBIENTE no nome (`asaas_sandbox` / `asaas_producao`)
-- em vez de uma coluna própria. Motivo: a chave natural do store é
-- (org_id, provider), e as duas credenciais coexistem — o usuário cadastra as
-- duas e alterna qual está ativa (tabela 2). Um `ambiente` como coluna
-- separada exigiria PK(org_id, provider, ambiente), que é justamente a forma
-- que o store NÃO tem. Este é o encaixe barato; o caro seria bifurcar o store.
--
-- `encrypted_tokens` é TEXT e não BYTEA de propósito — Fernet já devolve
-- base64 url-safe, e BYTEA volta como `\x…` hex pelo PostgREST, uma armadilha
-- de leitura que o `004_whatsapp_connections.sql` do social-wiring documenta.
-- O bundle cifrado é `{"api_key": "...", "webhook_token": "..."}`.
CREATE TABLE IF NOT EXISTS p_studio.provedor_credenciais (
    org_id           UUID        NOT NULL,
    provider         TEXT        NOT NULL,
    encrypted_tokens TEXT        NOT NULL,
    metadata         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, provider)
);

COMMENT ON TABLE p_studio.provedor_credenciais IS
  'Credenciais do provedor de cobrança, cifradas com Fernet em repouso. '
  'Escrita/leitura só pelo backend via noctusai_lib.security.token_store.';
COMMENT ON COLUMN p_studio.provedor_credenciais.provider IS
  'Provedor + ambiente: asaas_sandbox | asaas_producao. O ambiente ATIVO '
  'está em p_studio.integracao_config.ambiente.';
COMMENT ON COLUMN p_studio.provedor_credenciais.metadata IS
  'Extras NÃO-SECRETOS em texto claro (ex.: prefixo mascarado da chave para '
  'a UI). Nunca colocar segredo aqui — esta coluna não é cifrada.';

ALTER TABLE p_studio.provedor_credenciais ENABLE ROW LEVEL SECURITY;

-- 🔴 DIVERGÊNCIA DELIBERADA do precedente (`social_wiring.mailchimp_connections`
-- dá SELECT ao papel `authenticated`). Aqui NÃO existe policy de leitura para
-- `authenticated`: só `service_role`.
--
-- Rationale [A — aceito com justificativa]: uma policy de SELECT para
-- `authenticated` expõe a coluna `encrypted_tokens` a qualquer membro da org
-- via PostgREST direto, sem passar pelo backend. O ciphertext não é
-- plaintext, mas é material para ataque offline contra a chave Fernet, e o
-- frontend NÃO precisa dele: toda leitura da UI passa pelo backend, que
-- devolve status mascarado (`_mascarar`) e jamais o segredo. Conceder leitura
-- seria alargar a superfície sem nenhum consumidor. O precedente do
-- social-wiring é mais permissivo do que o necessário; não replicamos.
DROP POLICY IF EXISTS "provedor_credenciais_service_role" ON p_studio.provedor_credenciais;
CREATE POLICY "provedor_credenciais_service_role" ON p_studio.provedor_credenciais
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 2. Configuração da integração — qual ambiente está ativo
-- ============================================================================
--
-- Tabela separada, e não uma flag no `metadata` da linha de credencial, por
-- dois motivos: (a) alternar ambiente não deveria exigir decifrar e recifrar
-- o bundle só para virar um booleano; (b) "qual ambiente está ativo" é uma
-- configuração da org, não um atributo de uma credencial — se um dia houver
-- três ambientes ou dois provedores, a flag distribuída vira estado
-- inconsistente (duas linhas dizendo `ativo`) e esta coluna não.
--
-- Nada aqui é secreto, então `authenticated` LÊ (a UI mostra o ambiente
-- corrente) e só `service_role` escreve.
CREATE TABLE IF NOT EXISTS p_studio.integracao_config (
    org_id        UUID        PRIMARY KEY,
    provedor      TEXT        NOT NULL DEFAULT 'asaas',
    ambiente      TEXT        NOT NULL DEFAULT 'sandbox'
                              CHECK (ambiente IN ('sandbox', 'producao')),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE p_studio.integracao_config IS
  'Configuração não-secreta da integração de cobrança, uma linha por org. '
  'O default `sandbox` é deliberado: um deploy que ainda não escolheu não '
  'pode acabar emitindo boleto real por omissão.';

ALTER TABLE p_studio.integracao_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "integracao_config_select_own_org" ON p_studio.integracao_config;
CREATE POLICY "integracao_config_select_own_org" ON p_studio.integracao_config
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "integracao_config_service_role" ON p_studio.integracao_config;
CREATE POLICY "integracao_config_service_role" ON p_studio.integracao_config
    FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================================
-- 3. Nav — registra a página de integrações
-- ============================================================================
-- O nav do produto é filtrado por `status_pagina` (rota não listada ⇒ oculta).
-- Sem esta linha a página existe na rota e não aparece no menu — exatamente o
-- "route-exists ≠ wired" que o produto já pagou uma vez.
INSERT INTO p_studio.status_pagina (nome_pagina, status, descricao) VALUES
    ('integracoes', 'producao', 'Credenciais do provedor de cobrança e fila de eventos')
ON CONFLICT (nome_pagina) DO NOTHING;


DO $$
BEGIN
  RAISE NOTICE 'P Studio: 008 aplicada — credenciais cifradas do provedor prontas.';
END $$;
