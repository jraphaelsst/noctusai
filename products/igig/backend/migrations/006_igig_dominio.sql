-- ============================================================================
-- IgIg domain schema — Cliente · Marca · Contrato · Pauta · Tarefa
--
-- This is the CANONICAL schema. It targets Postgres/Supabase and ships the
-- real RLS policies, even though the product develops against SQLite today:
-- the moment IgIg lands on Postgres, tenant isolation becomes db-enforced
-- with no schema work. On the SQLite path there is no RLS, so isolation is
-- app-layer `org_id` scoping inside
-- `noctusai_lib.integrations.persistence.SqliteRecordStore` — the accepted
-- divergence recorded in KB § PATTERNS/common/accept-with-rationale.md.
--
-- The SQLite mirror lives at `migrations/sqlite/001_dominio.sql`. The two are
-- kept honest by `tests/test_schema_parity.py`, which fails if either file
-- grows a table or column the other lacks. Two hand-maintained schemas would
-- otherwise drift silently — the failure mode the parity test exists to make
-- loud.
--
-- `apontamento` is a SUPPORT table, not a core entity: the play/pause
-- timesheet in Módulo 4 produces N time segments per tarefa, so the hours
-- cannot live as a single column on tarefa. Módulo 5's "custo real do job"
-- and Módulo 6's DRE both aggregate over it.
-- ============================================================================
SET search_path = igig, public;

-- ============================================================================
-- cliente — the agency's customer account
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.cliente (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    nome         TEXT NOT NULL,
    nicho        TEXT,
    email        TEXT,
    telefone     TEXT,
    -- Módulo 1: contract signature flips prospect → ativo. Módulo 6 flips
    -- ativo → inadimplente, which gates the approval portal.
    status       TEXT NOT NULL DEFAULT 'prospect'
                 CHECK (status IN ('prospect', 'ativo', 'inativo', 'inadimplente')),
    origem       TEXT,
    observacoes  TEXT,
    encerrado_em TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_cliente_org ON igig.cliente (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_cliente_status ON igig.cliente (org_id, status);

-- ============================================================================
-- marca — Módulo 2, the Central da Marca spine that M3/M4/M5 all read from
--
-- paleta / linhas_editoriais / personas are JSONB: their shape is authored
-- per brand and queried whole (the persistent sidebar renders all of it at
-- once), so normalising them would buy joins we never filter on.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.marca (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    cliente_id        UUID NOT NULL REFERENCES igig.cliente (id) ON DELETE CASCADE,
    nome              TEXT NOT NULL,
    logo_url          TEXT,
    paleta            JSONB NOT NULL DEFAULT '[]'::jsonb,
    tom_de_voz        TEXT,
    termos_proibidos  TEXT,
    nivel_formalidade TEXT,
    linhas_editoriais JSONB NOT NULL DEFAULT '[]'::jsonb,
    personas          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_marca_org ON igig.marca (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_marca_cliente ON igig.marca (org_id, cliente_id);

-- ============================================================================
-- contrato — Módulo 6 retainers
--
-- posts_por_mes is the pacote contratado; Módulo 6 compares it against the
-- month's delivered pautas to bill itens excedentes.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.contrato (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    cliente_id     UUID NOT NULL REFERENCES igig.cliente (id) ON DELETE CASCADE,
    numero         TEXT,
    valor_mensal   NUMERIC(12, 2),
    posts_por_mes  INTEGER,
    valor_excedente NUMERIC(12, 2),
    dia_vencimento INTEGER CHECK (dia_vencimento BETWEEN 1 AND 31),
    data_inicio    DATE,
    data_fim       DATE,
    status         TEXT NOT NULL DEFAULT 'rascunho'
                   CHECK (status IN ('rascunho', 'aguardando_assinatura', 'ativo', 'encerrado')),
    assinado_em    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_contrato_org ON igig.contrato (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_contrato_cliente ON igig.contrato (org_id, cliente_id);

-- ============================================================================
-- pauta — Módulo 3, one planned piece of content on the calendário editorial
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.pauta (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    cliente_id       UUID NOT NULL REFERENCES igig.cliente (id) ON DELETE CASCADE,
    marca_id         UUID REFERENCES igig.marca (id) ON DELETE SET NULL,
    titulo           TEXT NOT NULL,
    formato          TEXT CHECK (formato IN ('feed', 'carrossel', 'reels', 'story', 'artigo', 'video')),
    -- Módulo 3: nível de consciência (topo/meio/fundo de funil)
    funil            TEXT CHECK (funil IN ('topo', 'meio', 'fundo')),
    linha_editorial  TEXT,
    copy_texto       TEXT,
    direcao_video    TEXT,
    canal            TEXT,
    data_publicacao  TIMESTAMPTZ,
    publicado_em     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_pauta_org ON igig.pauta (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_pauta_calendario ON igig.pauta (org_id, data_publicacao);

-- ============================================================================
-- tarefa — Módulo 4, one item on the esteira de produção
--
-- `etapa` is the rigid 8-step kanban from the spec. `refacoes` is the
-- Contador de Refações the client's [Solicitar Ajuste] increments; Módulo 5's
-- BI de eficiência reports taxa de refação per cliente off it.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.tarefa (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    pauta_id       UUID NOT NULL REFERENCES igig.pauta (id) ON DELETE CASCADE,
    titulo         TEXT NOT NULL,
    etapa          TEXT NOT NULL DEFAULT 'aguardando_roteiro'
                   CHECK (etapa IN (
                       'aguardando_roteiro', 'roteiro_em_producao',
                       'aguardando_design', 'design_em_producao',
                       'revisao_interna', 'aprovacao_cliente',
                       'pronto_para_agendamento', 'agendado')),
    responsavel_id UUID,
    prazo          TIMESTAMPTZ,
    refacoes       INTEGER NOT NULL DEFAULT 0,
    observacao_cliente TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_tarefa_org ON igig.tarefa (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_tarefa_etapa ON igig.tarefa (org_id, etapa);

-- ============================================================================
-- apontamento — support table under tarefa (timesheet play/pause segments)
--
-- `minutos` is denormalised from iniciado_em/encerrado_em so the DRE can sum
-- without recomputing intervals per row; an open segment has encerrado_em
-- NULL and minutos 0.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.apontamento (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    tarefa_id    UUID NOT NULL REFERENCES igig.tarefa (id) ON DELETE CASCADE,
    usuario_id   UUID NOT NULL,
    iniciado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    encerrado_em TIMESTAMPTZ,
    minutos      INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_apontamento_org ON igig.apontamento (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_apontamento_tarefa ON igig.apontamento (org_id, tarefa_id);
-- One open segment per user at a time — the spec requires the timer to pause
-- when another tarefa starts, so a second open row is a bug, not a state.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_apontamento_aberto
    ON igig.apontamento (org_id, usuario_id)
    WHERE encerrado_em IS NULL;

-- ============================================================================
-- RLS — every table, org-scoped through the trusted resolver
--
-- public.current_org_id() reads public.noctus_users (declared in 001) rather
-- than auth.jwt()->user_metadata, which is user-editable and therefore a
-- privilege-escalation hole.
-- ============================================================================
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['cliente', 'marca', 'contrato', 'pauta', 'tarefa', 'apontamento']
    LOOP
        EXECUTE format('ALTER TABLE igig.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', t || '_org_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON igig.%I FOR ALL TO authenticated '
            'USING (org_id = public.current_org_id()) '
            'WITH CHECK (org_id = public.current_org_id())',
            t || '_org_isolation', t
        );
    END LOOP;
END $$;

-- ============================================================================
-- updated_at triggers
-- ============================================================================
CREATE OR REPLACE FUNCTION igig.set_updated_at()
  RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END $$;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['cliente', 'marca', 'contrato', 'pauta', 'tarefa', 'apontamento']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON igig.%I', 'trg_' || t || '_updated_at', t);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON igig.%I '
            'FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at()',
            'trg_' || t || '_updated_at', t
        );
    END LOOP;
END $$;
