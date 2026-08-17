-- ============================================================================
-- 003_integracao_bancaria.sql — P Studio
-- Schema: p_studio
--
-- Liga o módulo financeiro a um provedor de cobrança externo. Hoje o Asaas;
-- em produção, o Banco do Brasil. O desenho é o mesmo para os dois: o
-- lançamento ganha o espelho da cobrança no provedor, e todo evento recebido
-- é gravado antes de ser processado.
--
-- Três mudanças:
--
--   1. `clientes` ganha documento e endereço. Sem CPF/CNPJ é impossível criar
--      um pagador em qualquer provedor — o Asaas exige `cpfCnpj`, o BB exige
--      `pagador.numeroInscricao`. Este era o bloqueador de saída.
--
--   2. `lancamentos` ganha o espelho da cobrança (id no provedor, status,
--      linha digitável, pix copia-e-cola). Colunas e não tabela lateral: a
--      relação é 1:1 e todo caminho de leitura já faz `select("*")` aqui.
--
--   3. `provedor_eventos` — log do que o provedor mandou. Não é conveniência:
--      é a fila de retry. Ver o bloco de comentário sobre a tabela.
--
-- Idempotente: pode rodar duas vezes sem estragar nada.
-- ============================================================================

SET search_path = p_studio, public;


-- ============================================================================
-- 1. Clientes — documento e endereço do pagador
-- ============================================================================

-- `cpf_cnpj` fica NULLABLE de propósito: já existem clientes cadastrados sem
-- documento, e exigir o preenchimento retroativo travaria o cadastro inteiro.
-- A obrigatoriedade é do fluxo de cobrança, não do cadastro — quem tenta
-- emitir sem documento recebe erro de domínio no service, com mensagem que
-- diz qual campo falta.
ALTER TABLE p_studio.clientes
  ADD COLUMN IF NOT EXISTS cpf_cnpj            TEXT,
  ADD COLUMN IF NOT EXISTS cep                 TEXT,
  ADD COLUMN IF NOT EXISTS endereco            TEXT,
  ADD COLUMN IF NOT EXISTS bairro              TEXT,
  ADD COLUMN IF NOT EXISTS provedor            TEXT,
  ADD COLUMN IF NOT EXISTS provedor_cliente_id TEXT;

COMMENT ON COLUMN p_studio.clientes.cpf_cnpj IS
  'Somente dígitos, sem pontuação. Obrigatório para emitir cobrança.';
COMMENT ON COLUMN p_studio.clientes.provedor_cliente_id IS
  'Id do cliente no provedor. O BB não tem objeto cliente — lá fica NULL e o '
  'pagador vai inline no boleto.';


-- ============================================================================
-- 2. Lançamentos — espelho da cobrança no provedor
-- ============================================================================

ALTER TABLE p_studio.lancamentos
  ADD COLUMN IF NOT EXISTS provedor             TEXT,
  ADD COLUMN IF NOT EXISTS provedor_cobranca_id TEXT,
  ADD COLUMN IF NOT EXISTS provedor_status      TEXT,
  ADD COLUMN IF NOT EXISTS url_fatura           TEXT,
  ADD COLUMN IF NOT EXISTS linha_digitavel      TEXT,
  ADD COLUMN IF NOT EXISTS pix_copia_e_cola     TEXT,
  ADD COLUMN IF NOT EXISTS sincronizado_em      TIMESTAMPTZ;

COMMENT ON COLUMN p_studio.lancamentos.provedor_status IS
  'Status cru do provedor. O status do domínio continua em `status` — este '
  'existe para diagnóstico quando os dois divergirem.';
COMMENT ON COLUMN p_studio.lancamentos.sincronizado_em IS
  'Última vez que o provedor confirmou o estado desta cobrança.';

-- Guarda de idempotência de saída. O Asaas não tem `Idempotency-Key`, então
-- a proteção contra emitir a mesma cobrança duas vezes é esta: um pagamento
-- do provedor não pode se ligar a dois lançamentos.
--
-- Duas escolhas deliberadas:
--   • NULLs são distintos no Postgres, então os milhares de lançamentos sem
--     cobrança não disputam a constraint.
--   • O índice NÃO começa por `org_id`, contrariando a convenção do 001. Ele
--     serve à busca do webhook, que chega sem JWT e sem org — descobrir o org
--     é justamente o que ele está tentando fazer. Um índice
--     (org_id, provedor, provedor_cobranca_id) seria redundante aqui.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'lancamentos_provedor_cobranca_unico'
  ) THEN
    ALTER TABLE p_studio.lancamentos
      ADD CONSTRAINT lancamentos_provedor_cobranca_unico
      UNIQUE (provedor, provedor_cobranca_id);
  END IF;
END $$;


-- ============================================================================
-- 3. Eventos recebidos do provedor
--
-- Por que uma tabela, e não processar direto:
--
-- O Asaas entrega webhook por fila sequencial e **interrompe a fila após 15
-- respostas não-2xx consecutivas**. Novas notificações continuam sendo
-- geradas, mas param de ser entregues até alguém reativar na mão no painel.
-- Ou seja: um evento que a gente não consegue processar, se devolver erro,
-- derruba a conciliação de todos os outros pagamentos.
--
-- Por isso o webhook grava primeiro, processa depois e responde 200 quase
-- sempre. Evento problemático fica estacionado aqui com `processado_em` nulo
-- e `erro` preenchido, e é reprocessado por rota autenticada. Esta tabela É a
-- fila de retry.
--
-- Três desvios conscientes das convenções do 001:
--
--   • Primeiro JSONB do schema. O payload é modelo de dados de terceiro, com
--     ~28 tipos de evento que mudam sem nos consultar. Normalizar seria
--     inventar schema para contrato que não é nosso. JSONB e não TEXT porque
--     o reprocessamento consulta campos de dentro.
--   • `tipo` guardado CRU (`PAYMENT_RECEIVED`), não traduzido. O log é
--     forense: guardar só o valor normalizado destrói a capacidade de
--     responder "o que eles mandaram, afinal?".
--   • Não é append-only como `producao_eventos`: `efeito`, `erro` e
--     `processado_em` são escritos depois do insert. A identidade da linha é
--     *o evento recebido*; como tratamos é metadado dela, não evento novo.
--
-- E o mais importante, dito sem rodeio: as policies abaixo protegem LEITURA.
-- O webhook escreve com o client service-role e passa por cima da RLS, porque
-- chega sem JWT. Fingir o contrário seria pior que o desvio.
-- ============================================================================

CREATE TABLE IF NOT EXISTS p_studio.provedor_eventos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,

    provedor       TEXT NOT NULL,
    evento_id      TEXT NOT NULL,   -- evt_… do provedor, ou sha256:<hex>
    tipo           TEXT NOT NULL,   -- cru: PAYMENT_RECEIVED, PAYMENT_OVERDUE…

    cobranca_id    TEXT,
    lancamento_id  UUID REFERENCES p_studio.lancamentos(id) ON DELETE SET NULL,

    payload        JSONB NOT NULL,

    -- recebido | ignorado_ja_recebido | sem_lancamento | ignorado | erro
    efeito         TEXT,
    erro           TEXT,
    processado_em  TIMESTAMPTZ,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT provedor_eventos_unico UNIQUE (provedor, evento_id)
);

COMMENT ON COLUMN p_studio.provedor_eventos.evento_id IS
  'Id do evento no provedor. Quando o tipo de evento não traz id, o adapter '
  'calcula sha256:<hex> sobre o corpo canônico — determinístico, e honesto '
  'quanto a ser fallback.';
COMMENT ON COLUMN p_studio.provedor_eventos.processado_em IS
  'NULL = ainda não aplicado. É este predicado que a rota de reprocessamento '
  'consulta.';

DROP TRIGGER IF EXISTS set_updated_at_provedor_eventos ON p_studio.provedor_eventos;
CREATE TRIGGER set_updated_at_provedor_eventos
  BEFORE UPDATE ON p_studio.provedor_eventos
  FOR EACH ROW EXECUTE FUNCTION p_studio.set_updated_at();

-- Convenção do 001: todo índice começa por org_id.
CREATE INDEX IF NOT EXISTS idx_ps_provedor_eventos_org
  ON p_studio.provedor_eventos(org_id, created_at DESC);

-- Parcial: a fila de retry é pequena mesmo quando a tabela não é.
CREATE INDEX IF NOT EXISTS idx_ps_provedor_eventos_pendentes
  ON p_studio.provedor_eventos(org_id, created_at)
  WHERE processado_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_ps_provedor_eventos_lancamento
  ON p_studio.provedor_eventos(org_id, lancamento_id);


-- ============================================================================
-- RLS
-- ============================================================================

ALTER TABLE p_studio.provedor_eventos ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT := 'provedor_eventos';
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'p_studio' AND tablename = t
      AND policyname = t || '_select_own_org'
  ) THEN
    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR SELECT TO authenticated
        USING (org_id = public.current_org_id());
    $p$, t || '_select_own_org', t);

    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR INSERT TO authenticated
        WITH CHECK (org_id = public.current_org_id());
    $p$, t || '_insert_own_org', t);

    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR UPDATE TO authenticated
        USING (org_id = public.current_org_id())
        WITH CHECK (org_id = public.current_org_id());
    $p$, t || '_update_own_org', t);

    EXECUTE format($p$
      CREATE POLICY %1$I ON p_studio.%2$I
        FOR DELETE TO authenticated
        USING (org_id = public.current_org_id());
    $p$, t || '_delete_own_org', t);
  END IF;
END $$;


DO $$
BEGIN
  RAISE NOTICE 'P Studio: 003 aplicada — integração bancária pronta.';
END $$;
