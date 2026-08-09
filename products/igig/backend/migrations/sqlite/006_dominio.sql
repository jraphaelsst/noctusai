-- ============================================================================
-- IgIg domain schema — SQLite mirror of `006_igig_dominio.sql`
-- Numbered to MATCH its canonical counterpart (006 ↔ 006), so the pairing is
-- obvious and the cross-branch migration-number keeper sees one claim per
-- number rather than two competing files.
--
-- The Postgres file is CANONICAL; this is the development-time mirror.
-- `tests/test_schema_parity.py` fails if either file grows a table or column
-- the other lacks, so the two cannot drift silently.
--
-- Deliberate differences, and why each is safe:
--   * No schema qualifier — SQLite has no schemas; the file IS the namespace.
--   * TEXT ids instead of UUID — SQLite has no uuid type. Ids are generated
--     application-side by SqliteRecordStore (uuid4), so the values are
--     identical to what Postgres would store.
--   * JSONB → TEXT — the store encodes dict/list as JSON text and decodes on
--     read, so callers see the same Python objects on both backends.
--   * TIMESTAMPTZ → TEXT — ISO-8601 strings, which sort correctly as text.
--   * NUMERIC → REAL.
--   * No RLS — SQLite has none. Tenant isolation is the app-layer `org_id`
--     predicate that SqliteRecordStore injects into every statement. This is
--     the accepted divergence; the Postgres file carries the real policies.
--   * No updated_at triggers — the store stamps `updated_at` on update.
-- ============================================================================

CREATE TABLE IF NOT EXISTS cliente (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL,
    nome         TEXT NOT NULL,
    nicho        TEXT,
    email        TEXT,
    telefone     TEXT,
    status       TEXT NOT NULL DEFAULT 'prospect'
                 CHECK (status IN ('prospect', 'ativo', 'inativo', 'inadimplente')),
    origem       TEXT,
    observacoes  TEXT,
    encerrado_em TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_cliente_org ON cliente (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_cliente_status ON cliente (org_id, status);

CREATE TABLE IF NOT EXISTS marca (
    id                TEXT PRIMARY KEY,
    org_id            TEXT NOT NULL,
    cliente_id        TEXT NOT NULL REFERENCES cliente (id) ON DELETE CASCADE,
    nome              TEXT NOT NULL,
    logo_url          TEXT,
    paleta            TEXT NOT NULL DEFAULT '[]',
    tom_de_voz        TEXT,
    termos_proibidos  TEXT,
    nivel_formalidade TEXT,
    linhas_editoriais TEXT NOT NULL DEFAULT '[]',
    personas          TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_marca_org ON marca (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_marca_cliente ON marca (org_id, cliente_id);

CREATE TABLE IF NOT EXISTS contrato (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    cliente_id      TEXT NOT NULL REFERENCES cliente (id) ON DELETE CASCADE,
    numero          TEXT,
    valor_mensal    REAL,
    posts_por_mes   INTEGER,
    valor_excedente REAL,
    dia_vencimento  INTEGER CHECK (dia_vencimento BETWEEN 1 AND 31),
    data_inicio     TEXT,
    data_fim        TEXT,
    status          TEXT NOT NULL DEFAULT 'rascunho'
                    CHECK (status IN ('rascunho', 'aguardando_assinatura', 'ativo', 'encerrado')),
    assinado_em     TEXT,
    -- Added by 012 (comercial). Declared here because SQLite's ALTER TABLE has
    -- no IF NOT EXISTS and the mirrors are applied as a SET, never
    -- incrementally against an existing database.
    orcamento_id           TEXT,
    documento_key          TEXT,
    provedor_assinatura    TEXT,
    assinatura_external_id TEXT,
    link_assinatura        TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_contrato_org ON contrato (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_contrato_cliente ON contrato (org_id, cliente_id);

CREATE TABLE IF NOT EXISTS pauta (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    cliente_id      TEXT NOT NULL REFERENCES cliente (id) ON DELETE CASCADE,
    marca_id        TEXT REFERENCES marca (id) ON DELETE SET NULL,
    titulo          TEXT NOT NULL,
    formato         TEXT CHECK (formato IN ('feed', 'carrossel', 'reels', 'story', 'artigo', 'video')),
    funil           TEXT CHECK (funil IN ('topo', 'meio', 'fundo')),
    linha_editorial TEXT,
    copy_texto      TEXT,
    direcao_video   TEXT,
    canal           TEXT,
    data_publicacao TEXT,
    publicado_em    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_pauta_org ON pauta (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_pauta_calendario ON pauta (org_id, data_publicacao);

CREATE TABLE IF NOT EXISTS tarefa (
    id                 TEXT PRIMARY KEY,
    org_id             TEXT NOT NULL,
    pauta_id           TEXT NOT NULL REFERENCES pauta (id) ON DELETE CASCADE,
    titulo             TEXT NOT NULL,
    etapa              TEXT NOT NULL DEFAULT 'aguardando_roteiro'
                       CHECK (etapa IN (
                           'aguardando_roteiro', 'roteiro_em_producao',
                           'aguardando_design', 'design_em_producao',
                           'revisao_interna', 'aprovacao_cliente',
                           'pronto_para_agendamento', 'agendado')),
    responsavel_id     TEXT,
    prazo              TEXT,
    refacoes           INTEGER NOT NULL DEFAULT 0,
    observacao_cliente TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_tarefa_org ON tarefa (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_tarefa_etapa ON tarefa (org_id, etapa);

CREATE TABLE IF NOT EXISTS apontamento (
    id           TEXT PRIMARY KEY,
    org_id       TEXT NOT NULL,
    tarefa_id    TEXT NOT NULL REFERENCES tarefa (id) ON DELETE CASCADE,
    usuario_id   TEXT NOT NULL,
    iniciado_em  TEXT NOT NULL,
    encerrado_em TEXT,
    minutos      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_igig_apontamento_org ON apontamento (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_apontamento_tarefa ON apontamento (org_id, tarefa_id);
-- Partial unique index — SQLite supports these, so the "one open segment per
-- user" invariant is enforced identically on both backends.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_apontamento_aberto
    ON apontamento (org_id, usuario_id)
    WHERE encerrado_em IS NULL;
