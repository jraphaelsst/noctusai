-- ============================================================================
-- IgIg — SQLite mirror of `018_igig_crm.sql` (018 ↔ 018). Parity-tested.
--
-- New tables only. The columns 018 adds to lead / orcamento / pauta / cliente
-- / contrato / integracao are declared in the 006 / 010 / 012 mirrors (SQLite
-- has no ADD COLUMN IF NOT EXISTS; the mirrors are applied as a set).
-- ============================================================================

CREATE TABLE IF NOT EXISTS produto_servico (
    id               TEXT PRIMARY KEY,
    org_id           TEXT NOT NULL,
    secao            TEXT NOT NULL CHECK (secao IN ('criacao_conteudo', 'gestao_conta')),
    nome             TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    descricao        TEXT,
    preco_base       REAL NOT NULL DEFAULT 0 CHECK (preco_base >= 0),
    unidade          TEXT NOT NULL DEFAULT 'unidade',
    horas_estimadas  REAL NOT NULL DEFAULT 0 CHECK (horas_estimadas >= 0),
    -- 020: the pauta format a criação product delivers.
    formato          TEXT CHECK (formato IS NULL OR formato IN ('feed', 'carrossel', 'reels', 'story', 'artigo', 'video')),
    ativo            INTEGER NOT NULL DEFAULT 1,
    ordem            INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_produto_servico_org
    ON produto_servico (org_id, secao, ordem);

CREATE TABLE IF NOT EXISTS negocio (
    id                   TEXT PRIMARY KEY,
    org_id               TEXT NOT NULL,
    lead_id              TEXT NOT NULL REFERENCES lead (id) ON DELETE CASCADE,
    titulo               TEXT NOT NULL CHECK (length(trim(titulo)) > 0),
    valor_estimado       REAL CHECK (valor_estimado IS NULL OR valor_estimado >= 0),
    etapa_id             TEXT NOT NULL REFERENCES pipeline_stages (id),
    kanban_pos           REAL NOT NULL DEFAULT 0,
    responsavel_id       TEXT REFERENCES profissional (id) ON DELETE SET NULL,
    status               TEXT NOT NULL DEFAULT 'aberto'
                         CHECK (status IN ('aberto', 'ganho', 'perdido')),
    stage_entered_at     TEXT NOT NULL,
    ganho_em             TEXT,
    perdido_em           TEXT,
    motivo_perda         TEXT,
    perdido_stage_id     TEXT REFERENCES pipeline_stages (id) ON DELETE SET NULL,
    orcamento_aceito_id  TEXT REFERENCES orcamento (id) ON DELETE SET NULL,
    cliente_id           TEXT REFERENCES cliente (id) ON DELETE SET NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT,
    CONSTRAINT negocio_perdido_com_motivo CHECK (
        status <> 'perdido' OR (motivo_perda IS NOT NULL AND perdido_em IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_igig_negocio_board ON negocio (org_id, etapa_id, kanban_pos);
CREATE INDEX IF NOT EXISTS idx_igig_negocio_lead ON negocio (org_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_igig_negocio_status ON negocio (org_id, status);

CREATE TABLE IF NOT EXISTS orcamento_item (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL,
    orcamento_id        TEXT NOT NULL REFERENCES orcamento (id) ON DELETE CASCADE,
    produto_servico_id  TEXT REFERENCES produto_servico (id) ON DELETE SET NULL,
    secao               TEXT NOT NULL CHECK (secao IN ('criacao_conteudo', 'gestao_conta')),
    descricao           TEXT NOT NULL,
    preco_unitario      REAL NOT NULL DEFAULT 0 CHECK (preco_unitario >= 0),
    recorrente          INTEGER NOT NULL DEFAULT 0,
    dias_semana         INTEGER NOT NULL DEFAULT 0 CHECK (dias_semana BETWEEN 0 AND 127),
    qtd_por_dia         INTEGER NOT NULL DEFAULT 0 CHECK (qtd_por_dia >= 0),
    quantidade_mensal   INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_mensal >= 0),
    subtotal            REAL NOT NULL DEFAULT 0,
    ordem               INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT,
    CONSTRAINT orcamento_item_recorrencia CHECK (
        NOT recorrente OR (dias_semana > 0 AND qtd_por_dia > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_igig_orcamento_item_orcamento
    ON orcamento_item (org_id, orcamento_id, ordem);

CREATE TABLE IF NOT EXISTS gmail_watch (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    email       TEXT NOT NULL,
    history_id  TEXT,
    expiration  TEXT,
    topic       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    UNIQUE (org_id, email)
);

CREATE TABLE IF NOT EXISTS orcamento_email (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    orcamento_id  TEXT NOT NULL REFERENCES orcamento (id) ON DELETE CASCADE,
    direction     TEXT NOT NULL CHECK (direction IN ('out', 'in')),
    message_id    TEXT NOT NULL,
    thread_id     TEXT,
    from_addr     TEXT,
    subject       TEXT,
    snippet       TEXT,
    occurred_at   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (org_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_igig_orcamento_email_orcamento
    ON orcamento_email (org_id, orcamento_id, occurred_at);

CREATE TABLE IF NOT EXISTS automacao (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    pipeline    TEXT NOT NULL CHECK (pipeline IN ('comercial', 'esteira')),
    etapa_id    TEXT NOT NULL REFERENCES pipeline_stages (id) ON DELETE CASCADE,
    gatilho     TEXT NOT NULL CHECK (gatilho IN ('entrada_etapa', 'sla')),
    sla_horas   INTEGER CHECK (sla_horas IS NULL OR sla_horas > 0),
    acao        TEXT NOT NULL DEFAULT '{}',
    ativo       INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    CONSTRAINT automacao_sla_com_horas CHECK (gatilho <> 'sla' OR sla_horas IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS automacao_execucao (
    id            TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    automacao_id  TEXT NOT NULL REFERENCES automacao (id) ON DELETE CASCADE,
    entidade_id   TEXT NOT NULL,
    -- 023: the pipeline_movimentos entry this execution belongs to + the
    -- `executando` claim state (declared here per the mirror convention).
    movimento_id  TEXT REFERENCES pipeline_movimentos (id) ON DELETE SET NULL,
    status        TEXT NOT NULL CHECK (status IN ('executando', 'sucesso', 'erro', 'ignorada')),
    detalhe       TEXT,
    executado_em  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_igig_automacao_execucao
    ON automacao_execucao (org_id, automacao_id, executado_em);
