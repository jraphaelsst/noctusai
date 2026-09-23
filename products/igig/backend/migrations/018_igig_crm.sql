-- ============================================================================
-- IgIg — cliente-first CRM foundation (roadmap cardhub-igig-crm-2026-09, wave B)
--
--   lead (enriched)   — contact + specs + the source it came from, with
--                       per-org external ids for dedupe (Meta Lead Ads, WAHA).
--   negocio           — the SALES CARD on the Comercial funnel. A lead has N
--                       negócios over time; closing one requires an orçamento
--                       (R4) and creates the Cliente.
--   produto_servico   — the catalogue orçamento items are priced from (R6).
--   orcamento (ext.)  — versions, validity (NULL = never expires), totals,
--                       margin, scope limits, e-mail tracking; at most ONE
--                       `aceito` per negócio.
--   orcamento_item    — line items; recurrence = weekday bitmask + qty/day.
--   pauta/cliente/contrato — origin links + contract signing modality (R12).
--   integracao        — canal set gains smtp/gmail/whatsapp/meta_leads + a
--                       non-secret `config` (host/port/from…); secrets stay in
--                       the Fernet-encrypted `token_cifrado`.
--   gmail_watch / orcamento_email — the reply watcher's state + the thread log
--                       (decision: Gmail API push, roadmap decision log).
--   automacao / automacao_execucao — stage-entry + SLA automations (R11).
--
-- Card positions use the seed's column names (`etapa_id`, `kanban_pos`) — the
-- seed `move_card` writes exactly those.
--
-- SQLite mirror: migrations/sqlite/018_crm.sql (parity-tested). Columns added
-- here to tables CREATEd by earlier migrations are declared in THOSE mirrors
-- (SQLite has no ADD COLUMN IF NOT EXISTS; mirrors apply as a set).
-- ============================================================================
SET search_path = igig, public;

-- ----------------------------------------------------------------------------
-- 1. lead — enrichment
-- ----------------------------------------------------------------------------
-- `origem` becomes the CHANNEL the lead arrived through (closed set). Until
-- now it held the public form's free-text "como nos conheceu" — that meaning
-- moves to `como_conheceu`, preserved verbatim, and every existing row is a
-- form lead (the form was the only way a lead could be created).
ALTER TABLE igig.lead ADD COLUMN IF NOT EXISTS como_conheceu TEXT;
ALTER TABLE igig.lead ADD COLUMN IF NOT EXISTS instagram TEXT;
ALTER TABLE igig.lead ADD COLUMN IF NOT EXISTS especificacoes JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE igig.lead ADD COLUMN IF NOT EXISTS observacoes TEXT;
ALTER TABLE igig.lead ADD COLUMN IF NOT EXISTS meta_lead_id TEXT;
ALTER TABLE igig.lead ADD COLUMN IF NOT EXISTS waha_chat_id TEXT;

UPDATE igig.lead
   SET como_conheceu = origem
 WHERE como_conheceu IS NULL
   AND origem IS NOT NULL
   AND origem NOT IN ('formulario', 'manual', 'whatsapp', 'meta_ads');
UPDATE igig.lead
   SET origem = 'formulario'
 WHERE origem IS NULL
    OR origem NOT IN ('formulario', 'manual', 'whatsapp', 'meta_ads');

ALTER TABLE igig.lead ALTER COLUMN origem SET DEFAULT 'manual';
ALTER TABLE igig.lead ALTER COLUMN origem SET NOT NULL;
ALTER TABLE igig.lead DROP CONSTRAINT IF EXISTS lead_origem_check;
ALTER TABLE igig.lead ADD CONSTRAINT lead_origem_check
    CHECK (origem IN ('formulario', 'manual', 'whatsapp', 'meta_ads'));

-- Dedupe keys: the same Meta lead / WhatsApp chat must land once per org.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_lead_meta
    ON igig.lead (org_id, meta_lead_id) WHERE meta_lead_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_lead_waha
    ON igig.lead (org_id, waha_chat_id) WHERE waha_chat_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. produto_servico — the catalogue
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS igig.produto_servico (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    secao            TEXT NOT NULL CHECK (secao IN ('criacao_conteudo', 'gestao_conta')),
    nome             TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    descricao        TEXT,
    preco_base       NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (preco_base >= 0),
    unidade          TEXT NOT NULL DEFAULT 'unidade',
    -- Feeds the orçamento's estimated cost → live margin (roadmap decision
    -- 2026-09-22: "live estimated margin").
    horas_estimadas  NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (horas_estimadas >= 0),
    ativo            BOOLEAN NOT NULL DEFAULT TRUE,
    ordem            INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_produto_servico_org
    ON igig.produto_servico (org_id, secao, ordem);

-- ----------------------------------------------------------------------------
-- 3. negocio — the funnel card
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS igig.negocio (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    lead_id              UUID NOT NULL REFERENCES igig.lead (id) ON DELETE CASCADE,
    titulo               TEXT NOT NULL CHECK (length(trim(titulo)) > 0),
    valor_estimado       NUMERIC(12, 2) CHECK (valor_estimado IS NULL OR valor_estimado >= 0),
    etapa_id             UUID NOT NULL REFERENCES igig.pipeline_stages (id),
    kanban_pos           NUMERIC NOT NULL DEFAULT 0,
    responsavel_id       UUID REFERENCES igig.profissional (id) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'aberto'
                         CHECK (status IN ('aberto', 'ganho', 'perdido')),
    -- Dwell time per stage (loss statistics — roadmap decision 2026-09-22).
    stage_entered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ganho_em             TIMESTAMPTZ,
    perdido_em           TIMESTAMPTZ,
    motivo_perda         TEXT,
    perdido_stage_id     UUID REFERENCES igig.pipeline_stages (id) ON DELETE SET NULL,
    orcamento_aceito_id  UUID REFERENCES igig.orcamento (id) ON DELETE SET NULL,
    cliente_id           UUID REFERENCES igig.cliente (id) ON DELETE SET NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ,
    -- A lost deal without its reason is exactly the statistic the owner asked
    -- for, silently missing.
    CONSTRAINT negocio_perdido_com_motivo CHECK (
        status <> 'perdido' OR (motivo_perda IS NOT NULL AND perdido_em IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_igig_negocio_board
    ON igig.negocio (org_id, etapa_id, kanban_pos);
CREATE INDEX IF NOT EXISTS idx_igig_negocio_lead ON igig.negocio (org_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_igig_negocio_status ON igig.negocio (org_id, status);

-- ----------------------------------------------------------------------------
-- 4. orcamento — versions, validity, totals, e-mail tracking
-- ----------------------------------------------------------------------------
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS negocio_id UUID
    REFERENCES igig.negocio (id) ON DELETE CASCADE;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;
-- NULL = never expires (owner decision 2026-09-22).
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS validade DATE;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS subtotal_criacao NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS subtotal_gestao NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS desconto NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS total_mensal NUMERIC(12, 2) NOT NULL DEFAULT 0;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS margem_estimada NUMERIC(12, 2);
-- {revisoes_incluidas, valor_excedente, ...} — authored per proposal.
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS limites_escopo JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS observacoes TEXT;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS pdf_key TEXT;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS enviado_em TIMESTAMPTZ;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS email_message_id TEXT;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS email_thread_id TEXT;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS respondido_em TIMESTAMPTZ;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS aceito_em TIMESTAMPTZ;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS recusado_em TIMESTAMPTZ;
ALTER TABLE igig.orcamento ADD COLUMN IF NOT EXISTS motivo_recusa TEXT;

ALTER TABLE igig.orcamento DROP CONSTRAINT IF EXISTS orcamento_status_check;
ALTER TABLE igig.orcamento ADD CONSTRAINT orcamento_status_check
    CHECK (status IN ('rascunho', 'enviado', 'aceito', 'recusado', 'expirado', 'substituido'));

-- Only one acceptable version per negócio (owner decision 2026-09-22).
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_orcamento_um_aceito
    ON igig.orcamento (negocio_id) WHERE status = 'aceito' AND negocio_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_orcamento_versao
    ON igig.orcamento (negocio_id, versao) WHERE negocio_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_igig_orcamento_negocio ON igig.orcamento (org_id, negocio_id);

-- ----------------------------------------------------------------------------
-- 5. orcamento_item
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS igig.orcamento_item (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    orcamento_id        UUID NOT NULL REFERENCES igig.orcamento (id) ON DELETE CASCADE,
    produto_servico_id  UUID REFERENCES igig.produto_servico (id) ON DELETE SET NULL,
    secao               TEXT NOT NULL CHECK (secao IN ('criacao_conteudo', 'gestao_conta')),
    descricao           TEXT NOT NULL,
    preco_unitario      NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (preco_unitario >= 0),
    recorrente          BOOLEAN NOT NULL DEFAULT FALSE,
    -- seg=1, ter=2, qua=4, qui=8, sex=16, sab=32, dom=64.
    dias_semana         SMALLINT NOT NULL DEFAULT 0 CHECK (dias_semana BETWEEN 0 AND 127),
    qtd_por_dia         INTEGER NOT NULL DEFAULT 0 CHECK (qtd_por_dia >= 0),
    quantidade_mensal   INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_mensal >= 0),
    subtotal            NUMERIC(12, 2) NOT NULL DEFAULT 0,
    ordem               INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ,
    -- A recurring item without a weekday never happens; say so at write time.
    CONSTRAINT orcamento_item_recorrencia CHECK (
        NOT recorrente OR (dias_semana > 0 AND qtd_por_dia > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_igig_orcamento_item_orcamento
    ON igig.orcamento_item (org_id, orcamento_id, ordem);

-- ----------------------------------------------------------------------------
-- 6. pauta / cliente / contrato — origin links + signing modality
-- ----------------------------------------------------------------------------
-- Calendar pautas generated from an accepted orçamento's recurring items
-- (roadmap R9: pautas only; esteira tasks on demand).
ALTER TABLE igig.pauta ADD COLUMN IF NOT EXISTS orcamento_item_id UUID
    REFERENCES igig.orcamento_item (id) ON DELETE SET NULL;
ALTER TABLE igig.pauta ADD COLUMN IF NOT EXISTS gerada_automaticamente BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE igig.cliente ADD COLUMN IF NOT EXISTS lead_id UUID
    REFERENCES igig.lead (id) ON DELETE SET NULL;
ALTER TABLE igig.cliente ADD COLUMN IF NOT EXISTS negocio_id UUID
    REFERENCES igig.negocio (id) ON DELETE SET NULL;
-- One cliente per lead: closing a second negócio of the same lead reuses the
-- existing cliente — the idempotency of R4's "creates the Cliente" is here,
-- not only in application code.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_cliente_lead
    ON igig.cliente (org_id, lead_id) WHERE lead_id IS NOT NULL;

ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS modalidade_assinatura TEXT NOT NULL DEFAULT 'digital';
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS assinado_manual_em TIMESTAMPTZ;
ALTER TABLE igig.contrato ADD COLUMN IF NOT EXISTS documento_assinado_key TEXT;
ALTER TABLE igig.contrato DROP CONSTRAINT IF EXISTS contrato_modalidade_assinatura_check;
ALTER TABLE igig.contrato ADD CONSTRAINT contrato_modalidade_assinatura_check
    CHECK (modalidade_assinatura IN ('digital', 'fisica'));

-- ----------------------------------------------------------------------------
-- 7. integracao — more channels + non-secret config
-- ----------------------------------------------------------------------------
ALTER TABLE igig.integracao ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE igig.integracao DROP CONSTRAINT IF EXISTS integracao_canal_check;
ALTER TABLE igig.integracao ADD CONSTRAINT integracao_canal_check
    CHECK (canal IN (
        'instagram', 'facebook', 'tiktok', 'linkedin',
        'smtp', 'gmail', 'whatsapp', 'meta_leads'));

-- ----------------------------------------------------------------------------
-- 8. Reply watcher — Gmail watch state + the orçamento e-mail thread log
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS igig.gmail_watch (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    email       TEXT NOT NULL,
    history_id  TEXT,
    -- users.watch expires (≤7 days); the renewal job keys on this.
    expiration  TIMESTAMPTZ,
    topic       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    UNIQUE (org_id, email)
);

CREATE TABLE IF NOT EXISTS igig.orcamento_email (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    orcamento_id  UUID NOT NULL REFERENCES igig.orcamento (id) ON DELETE CASCADE,
    direction     TEXT NOT NULL CHECK (direction IN ('out', 'in')),
    message_id    TEXT NOT NULL,
    thread_id     TEXT,
    from_addr     TEXT,
    subject       TEXT,
    snippet       TEXT,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A push notification can be delivered twice; the log must not double.
    UNIQUE (org_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_igig_orcamento_email_orcamento
    ON igig.orcamento_email (org_id, orcamento_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_igig_orcamento_email_thread
    ON igig.orcamento_email (org_id, thread_id);

-- ----------------------------------------------------------------------------
-- 9. Automations v1 (R11)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS igig.automacao (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    pipeline    TEXT NOT NULL CHECK (pipeline IN ('comercial', 'esteira')),
    etapa_id    UUID NOT NULL REFERENCES igig.pipeline_stages (id) ON DELETE CASCADE,
    gatilho     TEXT NOT NULL CHECK (gatilho IN ('entrada_etapa', 'sla')),
    sla_horas   INTEGER CHECK (sla_horas IS NULL OR sla_horas > 0),
    -- {tipo: 'tarefa'|'checklist'|'responsavel'|'email'|'whatsapp'|'alerta'|'ia', ...}
    acao        JSONB NOT NULL DEFAULT '{}'::jsonb,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    CONSTRAINT automacao_sla_com_horas CHECK (gatilho <> 'sla' OR sla_horas IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_igig_automacao_etapa
    ON igig.automacao (org_id, pipeline, etapa_id) WHERE ativo;

CREATE TABLE IF NOT EXISTS igig.automacao_execucao (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    automacao_id  UUID NOT NULL REFERENCES igig.automacao (id) ON DELETE CASCADE,
    entidade_id   UUID NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('sucesso', 'erro', 'ignorada')),
    detalhe       TEXT,
    executado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_igig_automacao_execucao
    ON igig.automacao_execucao (org_id, automacao_id, executado_em DESC);

-- ----------------------------------------------------------------------------
-- 10. RLS + updated_at
-- ----------------------------------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'produto_servico', 'negocio', 'orcamento_item', 'gmail_watch',
        'orcamento_email', 'automacao', 'automacao_execucao']
    LOOP
        EXECUTE format('ALTER TABLE igig.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', t || '_org_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON igig.%I FOR ALL TO authenticated '
            'USING (org_id = (SELECT public.current_org_id())) '
            'WITH CHECK (org_id = (SELECT public.current_org_id()))',
            t || '_org_isolation', t
        );
    END LOOP;
    FOREACH t IN ARRAY ARRAY[
        'produto_servico', 'negocio', 'orcamento_item', 'gmail_watch', 'automacao']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON igig.%I', 'trg_' || t || '_updated_at', t);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON igig.%I '
            'FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at()',
            'trg_' || t || '_updated_at', t
        );
    END LOOP;
END $$;

NOTIFY pgrst, 'reload schema';
