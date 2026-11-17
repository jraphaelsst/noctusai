-- ============================================================================
-- Migration 350 · social_wiring: Estruturas (platform library of script structures) + block-type catalog (M1)
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/core-studio-build/specs/estruturas-contract.md section 3.1 (EST-1, owner
-- decisions of 2026-11-15). An Estrutura is a headline formula + an ordered list of typed blocks, owned by ONE
-- monitored third-party profile and optionally derived from one video. The library is PLATFORM-WIDE (no org_id):
-- only platform admins write (through the RPCs below), org members only read through the API (service-role only;
-- no browser grant, no browser policy). It replaces the per-viral blueprint as the structure source.
--
--   * cs_estrutura_tipos_bloco  -- the catalog of canonical block types (21 + the protected system row `Outro`),
--                                  seeded from app/modules/media_creation/estruturas_tipos_bloco.py :: seed_sql()
--                                  (a test pins the text below to that function). An admin owns it afterwards.
--   * cs_estruturas             -- the Estrutura: formula, formato, objetivos, status, origem, per-field provenance.
--   * cs_estrutura_blocos       -- the ordered blocks (ordem unique per Estrutura, DEFERRED so a reorder is one statement).
--   * cs_estrutura_eventos      -- append-only history of every change (NO content: opt-out purges leave nothing).
--   * cs_estrutura_tipo_eventos -- append-only history of the catalog.
--   * cs_estrutura_importacoes  -- one row per load run (state; the per-row trail is cs_estrutura_eventos.importacao_id).
--   * cs_estrutura_usos         -- append-only fact: which Estrutura (and blocks) served which headline/roteiro.
--   * cs_estruturas_resumo      -- derived view (blocos_total, campos_pendentes, busca); never stored.
--
-- EVERY state change + its event row is ONE call to a SECURITY DEFINER function (one PostgREST call = one
-- transaction): cs_estrutura_criar / _atualizar / _substituir_blocos / _confirmar / _publicar / _arquivar /
-- _restaurar / _excluir and cs_estrutura_tipo_salvar / _tipo_excluir. The service role can only SELECT the
-- library tables; it cannot write them except through those functions. A refusal is a coded exception
-- (RAISE EXCEPTION '<code>'), mapped to an HTTP status by the API (versao_desatualizada -> 409, ...).
--
-- Deliberate refinements of the contract text (each recorded in the slice return as drift-found):
--   * cs_estrutura_usos.estrutura_id is ON DELETE CASCADE (the contract says RESTRICT). RESTRICT would make the LGPD
--     opt-out purge (profile delete -> Estruturas cascade) fail for any USED Estrutura and the usos are append-only,
--     so the purge could not clear them first. The admin hard delete still refuses a used Estrutura
--     (cs_estrutura_excluir raises estrutura_em_uso); only a DB-driven cascade removes usos.
--   * cs_estrutura_restaurar returns an archived Estrutura to `ativa` only when it was ever published
--     (publicada_em IS NOT NULL), else to `rascunho`: restoring a never-published draft straight to `ativa` would
--     bypass the publish completeness check.
--   * cs_estruturas_resumo.campos_pendentes also counts blocks' nome_origem (an AI draft's block names are
--     `ia_sugerido`; imports write `fonte`, so the import numbers are unchanged).
--
-- Backward compatible with the previous image (new objects only). FORWARD-ONLY, IDEMPOTENT.
-- GuardProbes: _SW_350_PROBES in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
-- Requires 229 (cs_perfis_monitorados, cs_virais, cs_headlines, cs_roteiros) and the marcas table.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_perfis_monitorados') IS NULL
     OR to_regclass('social_wiring.cs_virais') IS NULL
     OR to_regclass('social_wiring.cs_headlines') IS NULL
     OR to_regclass('social_wiring.cs_roteiros') IS NULL THEN
    RAISE EXCEPTION 'Migration 350 requires the cs_* library tables of migration 229 -- apply 229 first';
  END IF;
  IF to_regclass('social_wiring.marcas') IS NULL THEN
    RAISE EXCEPTION 'Migration 350 requires social_wiring.marcas -- apply the marcas migration first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Block-type catalog (platform) + its events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_estrutura_tipos_bloco (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome                 TEXT NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 80),
    ordem                INTEGER NOT NULL,
    tempo_tipico         TEXT CHECK (tempo_tipico IS NULL OR char_length(tempo_tipico) BETWEEN 1 AND 40),
    instrucao_referencia TEXT NOT NULL CHECK (char_length(instrucao_referencia) BETWEEN 1 AND 600),
    ativo                BOOLEAN NOT NULL DEFAULT true,
    sistema              BOOLEAN NOT NULL DEFAULT false,
    versao               INTEGER NOT NULL DEFAULT 1 CHECK (versao >= 1),
    created_by           UUID,
    updated_by           UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_estrutura_tipos_bloco_nome_uq UNIQUE (nome),
    -- DEFERRED: moving a type shifts its neighbours in the same statement/transaction.
    CONSTRAINT cs_estrutura_tipos_bloco_ordem_uq UNIQUE (ordem) DEFERRABLE INITIALLY DEFERRED
);

-- ``Outro`` (sistema) is write-protected in the table itself, not only in the RPC: it cannot be renamed,
-- deactivated, un-flagged or deleted by any path.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_tipos_bloco_protegido()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF OLD.sistema THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'cs_estrutura_tipos_bloco_protegido: the system block type cannot be deleted' USING ERRCODE = 'P0001';
        END IF;
        IF NEW.nome IS DISTINCT FROM OLD.nome OR NEW.ativo IS DISTINCT FROM OLD.ativo
           OR NEW.sistema IS DISTINCT FROM OLD.sistema THEN
            RAISE EXCEPTION 'cs_estrutura_tipos_bloco_protegido: the system block type cannot be renamed, deactivated or un-flagged' USING ERRCODE = 'P0001';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$fn$;
DROP TRIGGER IF EXISTS cs_estrutura_tipos_bloco_protegido ON social_wiring.cs_estrutura_tipos_bloco;
CREATE TRIGGER cs_estrutura_tipos_bloco_protegido
    BEFORE UPDATE OR DELETE ON social_wiring.cs_estrutura_tipos_bloco
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_estrutura_tipos_bloco_protegido();

-- transition-log-ok: cs_estrutura_tipo_eventos a catalog-edit ledger (create/edit/activate/delete of rows), no single state column to transition
CREATE TABLE IF NOT EXISTS social_wiring.cs_estrutura_tipo_eventos (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo_id    UUID NOT NULL,
    tipo       TEXT NOT NULL CHECK (tipo IN ('criado', 'editado', 'ativado', 'desativado', 'excluido')),
    campo      TEXT,
    ator_id    UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cs_estrutura_tipo_eventos_tipo_idx
    ON social_wiring.cs_estrutura_tipo_eventos (tipo_id, created_at);

-- ----------------------------------------------------------------------------
-- 2. cs_estruturas
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_estruturas (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- the human id shown as "estrutura #codigo" (chat citation, deep link)
    codigo              BIGINT GENERATED ALWAYS AS IDENTITY,
    -- CASCADE: an opt-out purge must remove derived data (ordinary profile delete is guarded in the service)
    perfil_id           UUID NOT NULL REFERENCES social_wiring.cs_perfis_monitorados (id) ON DELETE CASCADE,
    viral_id            UUID REFERENCES social_wiring.cs_virais (id) ON DELETE SET NULL,
    formula_headline    TEXT NOT NULL,
    formato             TEXT,
    objetivos           TEXT[] NOT NULL DEFAULT '{}'::text[],
    status              TEXT NOT NULL DEFAULT 'rascunho',
    origem              TEXT NOT NULL,
    -- the load's idempotency key (CoreStudio id / Maquina molde id), never our PK
    fonte_externa       TEXT,
    ref_externa         TEXT,
    fonte_hash          TEXT,
    formula_herdada_de  TEXT,
    referencia_rotulo   TEXT,
    formula_origem      TEXT NOT NULL DEFAULT 'admin',
    formato_origem      TEXT NOT NULL DEFAULT 'admin',
    objetivos_origem    TEXT NOT NULL DEFAULT 'admin',
    versao              INTEGER NOT NULL DEFAULT 1,
    created_by          UUID,
    updated_by          UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    arquivada_em        TIMESTAMPTZ,
    publicada_em        TIMESTAMPTZ,
    CONSTRAINT cs_estruturas_codigo_uq UNIQUE (codigo),
    CONSTRAINT cs_estruturas_formula_valida CHECK (char_length(formula_headline) BETWEEN 1 AND 1000
                                                   AND formula_headline = btrim(formula_headline)),
    CONSTRAINT cs_estruturas_formato_valido CHECK (formato IS NULL OR formato IN ('reels', 'carrossel', 'stories', 'post')),
    CONSTRAINT cs_estruturas_objetivos_validos CHECK (
        objetivos <@ ARRAY['alcance', 'autoridade', 'conexao', 'venda']::text[]
        AND cardinality(objetivos) <= 4
        -- no duplicates: every element is one of the 4, so the count of distinct members == cardinality
        AND cardinality(objetivos) = (('alcance' = ANY (objetivos))::int + ('autoridade' = ANY (objetivos))::int
                                      + ('conexao' = ANY (objetivos))::int + ('venda' = ANY (objetivos))::int)),
    CONSTRAINT cs_estruturas_status_valido CHECK (status IN ('rascunho', 'ativa', 'arquivada')),
    CONSTRAINT cs_estruturas_ativa_completa CHECK (status <> 'ativa' OR (formato IS NOT NULL AND cardinality(objetivos) >= 1)),
    CHECK (origem IN ('manual', 'import_corestudio', 'import_maquina', 'viral_auto')),
    CONSTRAINT cs_estruturas_fonte_externa_par CHECK ((fonte_externa IS NULL) = (ref_externa IS NULL)),
    CHECK (formula_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    CHECK (formato_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    CHECK (objetivos_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    CHECK (versao >= 1)
);
CREATE UNIQUE INDEX IF NOT EXISTS cs_estruturas_fonte_ref_uq
    ON social_wiring.cs_estruturas (fonte_externa, ref_externa) WHERE ref_externa IS NOT NULL;
-- one auto-draft per video
CREATE UNIQUE INDEX IF NOT EXISTS cs_estruturas_viral_auto_uq
    ON social_wiring.cs_estruturas (viral_id) WHERE origem = 'viral_auto';
CREATE INDEX IF NOT EXISTS cs_estruturas_perfil_status_idx ON social_wiring.cs_estruturas (perfil_id, status);
CREATE INDEX IF NOT EXISTS cs_estruturas_status_formato_idx ON social_wiring.cs_estruturas (status, formato);
CREATE INDEX IF NOT EXISTS cs_estruturas_viral_idx ON social_wiring.cs_estruturas (viral_id) WHERE viral_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_estruturas_formula_fts ON social_wiring.cs_estruturas
    USING GIN (to_tsvector('portuguese', formula_headline));

-- ----------------------------------------------------------------------------
-- 3. cs_estrutura_blocos
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_estrutura_blocos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    estrutura_id    UUID NOT NULL REFERENCES social_wiring.cs_estruturas (id) ON DELETE CASCADE,
    ordem           INTEGER NOT NULL CHECK (ordem >= 1),
    -- a type in use cannot be deleted (RESTRICT); `Outro` for anything outside the catalog
    tipo_id         UUID NOT NULL REFERENCES social_wiring.cs_estrutura_tipos_bloco (id) ON UPDATE CASCADE ON DELETE RESTRICT,
    -- the block's own display name (the source's "nome_original"); the TYPE is the canonical class
    nome            TEXT NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 120),
    -- time OR slide/frame label ("3-7s", "slide 2", "legenda 1", "imagem")
    tempo           TEXT CHECK (tempo IS NULL OR char_length(tempo) BETWEEN 1 AND 40),
    instrucao       TEXT CHECK (instrucao IS NULL OR char_length(instrucao) BETWEEN 1 AND 2000),
    -- the source's parenthetical: describes the ORIGINAL video's content; shown, never templated
    nota            TEXT CHECK (nota IS NULL OR char_length(nota) BETWEEN 1 AND 600),
    repeticoes      INTEGER NOT NULL DEFAULT 1 CHECK (repeticoes BETWEEN 1 AND 20),
    nome_origem      TEXT NOT NULL DEFAULT 'admin' CHECK (nome_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    tipo_origem      TEXT NOT NULL DEFAULT 'admin' CHECK (tipo_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    tempo_origem     TEXT NOT NULL DEFAULT 'admin' CHECK (tempo_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    instrucao_origem TEXT NOT NULL DEFAULT 'admin' CHECK (instrucao_origem IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- DEFERRED: a reorder / insert-in-the-middle is one RPC, the check runs at commit
    CONSTRAINT cs_estrutura_blocos_ordem_uq UNIQUE (estrutura_id, ordem) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS cs_estrutura_blocos_tipo_idx ON social_wiring.cs_estrutura_blocos (tipo_id);

-- ----------------------------------------------------------------------------
-- 4. cs_estrutura_eventos (append-only, NO content, NO FK: history outlives a hard delete)
-- ----------------------------------------------------------------------------
-- transition-log-ok: cs_estrutura_eventos a field-level provenance + lifecycle ledger of a multi-field entity (no single state column), contract 3.1
CREATE TABLE IF NOT EXISTS social_wiring.cs_estrutura_eventos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    estrutura_id    UUID NOT NULL,
    perfil_id       UUID,
    tipo            TEXT NOT NULL CHECK (tipo IN (
        'criada', 'criada_automatica', 'importada', 'atualizada_import', 'ia_preenchida', 'campo_editado',
        'campo_confirmado', 'bloco_adicionado', 'bloco_removido', 'blocos_reordenados', 'publicada', 'arquivada',
        'restaurada', 'excluida')),
    -- formula_headline | formato | objetivos | viral_id | bloco.<bloco_id>[.nome|tipo|tempo|instrucao|nota|repeticoes]
    campo           TEXT,
    origem_anterior TEXT CHECK (origem_anterior IS NULL OR origem_anterior IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    origem_nova     TEXT CHECK (origem_nova IS NULL OR origem_nova IN ('fonte', 'referencia', 'ia_sugerido', 'admin')),
    ator_id         UUID,
    ator_tipo       TEXT NOT NULL CHECK (ator_tipo IN ('admin', 'sistema_import', 'sistema_ia')),
    importacao_id   UUID,
    -- cs_estruturas.versao AFTER the change
    versao          INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cs_estrutura_eventos_estrutura_idx ON social_wiring.cs_estrutura_eventos (estrutura_id, created_at);
CREATE INDEX IF NOT EXISTS cs_estrutura_eventos_tipo_idx ON social_wiring.cs_estrutura_eventos (tipo, created_at);
CREATE INDEX IF NOT EXISTS cs_estrutura_eventos_importacao_idx
    ON social_wiring.cs_estrutura_eventos (importacao_id) WHERE importacao_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 5. cs_estrutura_importacoes (one row per load run)
-- ----------------------------------------------------------------------------
-- measurable[cs_estrutura_importacoes]: the row IS the dated record of ONE load run (created_at -> finished_at, terminal status, counters); the per-row trail is cs_estrutura_eventos.importacao_id, so a second events table would duplicate it
CREATE TABLE IF NOT EXISTS social_wiring.cs_estrutura_importacoes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fonte                   TEXT NOT NULL CHECK (fonte IN ('referencia', 'maquina_de_roteiros')),
    arquivo_sha256          TEXT NOT NULL CHECK (char_length(arquivo_sha256) = 64),
    arquivo_nome            TEXT CHECK (arquivo_nome IS NULL OR char_length(arquivo_nome) <= 300),
    status                  TEXT NOT NULL CHECK (status IN ('simulada', 'em_andamento', 'concluida', 'falhou')),
    dry_run                 BOOLEAN NOT NULL DEFAULT true,
    linhas_total            INTEGER NOT NULL DEFAULT 0 CHECK (linhas_total >= 0),
    perfis_criados          INTEGER NOT NULL DEFAULT 0 CHECK (perfis_criados >= 0),
    perfis_mesclados        INTEGER NOT NULL DEFAULT 0 CHECK (perfis_mesclados >= 0),
    estruturas_criadas      INTEGER NOT NULL DEFAULT 0 CHECK (estruturas_criadas >= 0),
    estruturas_atualizadas  INTEGER NOT NULL DEFAULT 0 CHECK (estruturas_atualizadas >= 0),
    estruturas_inalteradas  INTEGER NOT NULL DEFAULT 0 CHECK (estruturas_inalteradas >= 0),
    estruturas_ignoradas    INTEGER NOT NULL DEFAULT 0 CHECK (estruturas_ignoradas >= 0),
    blocos_criados          INTEGER NOT NULL DEFAULT 0 CHECK (blocos_criados >= 0),
    -- a histogram {motivo: n}, not a business list
    ignoradas_motivos       JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(ignoradas_motivos) = 'object'),
    erro                    TEXT CHECK (erro IS NULL OR char_length(erro) <= 1000),
    iniciada_por            UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at             TIMESTAMPTZ
);
-- one load at a time (the importacao_em_andamento lock, enforced where two admins cannot both pass)
CREATE UNIQUE INDEX IF NOT EXISTS cs_estrutura_importacoes_uma_em_andamento_uq
    ON social_wiring.cs_estrutura_importacoes (status) WHERE status = 'em_andamento';
CREATE INDEX IF NOT EXISTS cs_estrutura_importacoes_sha_idx
    ON social_wiring.cs_estrutura_importacoes (arquivo_sha256, created_at DESC);

-- ----------------------------------------------------------------------------
-- 6. cs_estrutura_usos (append-only fact: which Estrutura served which headline / roteiro)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_estrutura_usos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id     UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    -- CASCADE (not the contract's RESTRICT): see the header. The admin hard delete refuses a used Estrutura in the RPC.
    estrutura_id UUID NOT NULL REFERENCES social_wiring.cs_estruturas (id) ON DELETE CASCADE,
    contexto     TEXT NOT NULL CHECK (contexto IN ('chat', 'lote_headlines', 'roteiro_avancado')),
    papel        TEXT NOT NULL CHECK (papel IN ('principal', 'mistura')),
    ordem        SMALLINT NOT NULL CHECK (ordem >= 1),
    bloco_ids    UUID[] NOT NULL DEFAULT '{}'::uuid[],
    headline_id  UUID REFERENCES social_wiring.cs_headlines (id) ON DELETE SET NULL,
    roteiro_id   UUID REFERENCES social_wiring.cs_roteiros (id) ON DELETE SET NULL,
    -- cs_chat_propostas arrives with M3: no FK here
    proposta_id  UUID,
    created_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    -- No CHECK "at least one link": the ON DELETE SET NULL actions would trip it. The service guarantees at least
    -- one of headline_id | roteiro_id | proposta_id at insert.
);
CREATE UNIQUE INDEX IF NOT EXISTS cs_estrutura_usos_roteiro_uq
    ON social_wiring.cs_estrutura_usos (estrutura_id, roteiro_id) WHERE roteiro_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS cs_estrutura_usos_headline_uq
    ON social_wiring.cs_estrutura_usos (estrutura_id, headline_id) WHERE headline_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_estrutura_usos_marca_idx ON social_wiring.cs_estrutura_usos (marca_id, created_at);
CREATE INDEX IF NOT EXISTS cs_estrutura_usos_estrutura_idx ON social_wiring.cs_estrutura_usos (estrutura_id, created_at);
CREATE INDEX IF NOT EXISTS cs_estrutura_usos_org_idx ON social_wiring.cs_estrutura_usos (org_id);
CREATE INDEX IF NOT EXISTS cs_estrutura_usos_headline_idx ON social_wiring.cs_estrutura_usos (headline_id) WHERE headline_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS cs_estrutura_usos_roteiro_idx ON social_wiring.cs_estrutura_usos (roteiro_id) WHERE roteiro_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 7. Append-only guards (UPDATE/DELETE refused; the FK actions of usos are the ONLY carve-out) + TRUNCATE refusal
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'cs_estrutura_eventos_imutavel: cs_estrutura_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_estrutura_eventos_imutavel ON social_wiring.cs_estrutura_eventos;
CREATE TRIGGER cs_estrutura_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_estrutura_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_estrutura_eventos_imutavel();

CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_tipo_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'cs_estrutura_tipo_eventos_imutavel: cs_estrutura_tipo_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_estrutura_tipo_eventos_imutavel ON social_wiring.cs_estrutura_tipo_eventos;
CREATE TRIGGER cs_estrutura_tipo_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_estrutura_tipo_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_estrutura_tipo_eventos_imutavel();

-- usos: append-only with the FK-ACTION carve-outs. A DB-driven FK action runs its statement from inside the RI
-- trigger (pg_trigger_depth() > 1 here): ON DELETE CASCADE (estrutura / marca / org) is a DELETE, ON DELETE SET NULL
-- (headline / roteiro) is an UPDATE of exactly that column from non-NULL to NULL with everything else unchanged.
-- Every other UPDATE/DELETE -- including any a service-role call makes (depth 1 inside a function, 0 direct) -- is refused.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_usos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF pg_trigger_depth() > 1 THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        IF TG_OP = 'UPDATE'
           AND (NEW.id, NEW.org_id, NEW.marca_id, NEW.estrutura_id, NEW.contexto, NEW.papel, NEW.ordem,
                NEW.bloco_ids, NEW.proposta_id, NEW.created_by, NEW.created_at)
               IS NOT DISTINCT FROM
               (OLD.id, OLD.org_id, OLD.marca_id, OLD.estrutura_id, OLD.contexto, OLD.papel, OLD.ordem,
                OLD.bloco_ids, OLD.proposta_id, OLD.created_by, OLD.created_at)
           AND (NEW.headline_id IS NULL OR NEW.headline_id IS NOT DISTINCT FROM OLD.headline_id)
           AND (NEW.roteiro_id IS NULL OR NEW.roteiro_id IS NOT DISTINCT FROM OLD.roteiro_id) THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION 'cs_estrutura_usos_imutavel: cs_estrutura_usos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_estrutura_usos_imutavel ON social_wiring.cs_estrutura_usos;
CREATE TRIGGER cs_estrutura_usos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_estrutura_usos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_estrutura_usos_imutavel();

-- Row triggers never fire on TRUNCATE: one statement-level refusal shared by the three append-only tables.
CREATE OR REPLACE FUNCTION social_wiring.cs_estruturas_recusa_truncate()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'cs_estruturas_recusa_truncate: % is append-only (TRUNCATE refused)', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_estrutura_eventos_no_truncate ON social_wiring.cs_estrutura_eventos;
CREATE TRIGGER cs_estrutura_eventos_no_truncate BEFORE TRUNCATE ON social_wiring.cs_estrutura_eventos
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.cs_estruturas_recusa_truncate();
DROP TRIGGER IF EXISTS cs_estrutura_tipo_eventos_no_truncate ON social_wiring.cs_estrutura_tipo_eventos;
CREATE TRIGGER cs_estrutura_tipo_eventos_no_truncate BEFORE TRUNCATE ON social_wiring.cs_estrutura_tipo_eventos
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.cs_estruturas_recusa_truncate();
DROP TRIGGER IF EXISTS cs_estrutura_usos_no_truncate ON social_wiring.cs_estrutura_usos;
CREATE TRIGGER cs_estrutura_usos_no_truncate BEFORE TRUNCATE ON social_wiring.cs_estrutura_usos
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.cs_estruturas_recusa_truncate();

-- ----------------------------------------------------------------------------
-- 8. Seed: the block-type catalog (generated by estruturas_tipos_bloco.seed_sql(); a test pins this text)
-- ----------------------------------------------------------------------------
-- BEGIN seed_sql
INSERT INTO social_wiring.cs_estrutura_tipos_bloco (nome, ordem, tempo_tipico, instrucao_referencia, sistema)
VALUES
    ('Headline', 1, '0–3s', 'Frase de abertura que para a rolagem: entrega a promessa ou o conflito do vídeo em uma frase falada, seguindo a fórmula da estrutura. Nada de saudação antes.', false),
    ('Intensificador do Mistério', 2, '3–8s', 'Aumenta a tensão aberta pela headline sem entregar a resposta: aponta que há algo que a maioria não percebe, levanta uma pergunta ou adia a revelação.', false),
    ('Revelação', 3, '5–10s', 'Entrega a resposta que a headline e o intensificador seguraram, de forma clara e direta.', false),
    ('Opinião Polêmica', 4, '5–10s', 'Afirmação forte que contraria o senso comum ou toma posição clara sobre o tema; dita com convicção, sem relativizar.', false),
    ('Pontos de Identificação', 5, '5–10s', 'Descreve situações, pensamentos ou sentimentos concretos do público para que ele se reconheça ("você que…"); específico, nunca genérico.', false),
    ('Provas e Argumentações', 6, '5–12s', 'Sustenta a afirmação com prova por especificidade (um caso, uma cena, um detalhe concreto, um conceito com fonte). Nunca inventar números, estudos, nomes ou casos; sem prova real, usar raciocínio e sinalizar o que precisa ser inserido.', false),
    ('Fatos Curiosos', 7, '5–10s', 'Um dado, conceito ou fato surpreendente que reenquadra o tema e gera o efeito "eu não sabia disso"; precisa ser verdadeiro e verificável.', false),
    ('Histórias Magnéticas', 8, '10–25s', 'Narra uma história (própria, de cliente ou de figura pública) com começo, tensão e virada, em cenas concretas, conectada à mensagem do vídeo.', false),
    ('Notícia do Momento', 9, '5–10s', 'Ancora o vídeo em um acontecimento atual e conhecido (notícia, caso viral, figura pública) e faz a ponte para o tema.', false),
    ('Valor Prático', 10, '8–15s', 'Entrega algo aplicável agora: um passo, uma dica, um exercício ou um critério de decisão, em linguagem simples.', false),
    ('Contraste', 11, '5–8s', 'Coloca lado a lado o jeito comum e o jeito certo (antes/depois, errado/certo) para deixar a virada evidente.', false),
    ('Pergunta Reflexiva', 12, '3–6s', 'Faz uma pergunta direta ao espectador que o obriga a se posicionar ou pensar na própria vida.', false),
    ('Apresentação Magnética', 13, '3–6s', 'O criador se apresenta com a SUA apresentação magnética cadastrada (quem é + para quem trabalha + autoridade). Se a marca não tiver uma, omitir o bloco; nunca inventar credenciais.', false),
    ('Encerramento', 14, '3–8s', 'Fecha a ideia com uma frase de impacto ou síntese que deixa a mensagem principal na cabeça de quem assistiu.', false),
    ('CTA Salvar', 15, '2–4s', 'Pede para salvar o vídeo, dando o motivo (vai precisar disso depois).', false),
    ('CTA Compartilhar', 16, '2–4s', 'Pede para enviar o vídeo a uma pessoa específica ("manda pra quem…").', false),
    ('CTA Comentar', 17, '2–4s', 'Pede um comentário específico e fácil (uma palavra, uma opinião, uma experiência).', false),
    ('CTA Seguir', 18, '2–4s', 'Pede para seguir o perfil, dizendo o que a pessoa vai receber ao seguir.', false),
    ('CTA Curtir', 19, '2–3s', 'Pede a curtida, ligada à concordância com a mensagem.', false),
    ('CTA Link/Produto', 20, '3–6s', 'Direciona para a oferta (link na bio, direct, produto), dizendo o benefício.', false),
    ('CTA', 21, '2–4s', 'Chamada para ação genérica: escolher a mais adequada ao objetivo (salvar, compartilhar, comentar ou seguir).', false),
    ('Outro', 22, NULL, 'Bloco que não se encaixa em nenhum tipo do catálogo: siga a instrução própria do bloco; se ela estiver ausente, entregue exatamente o que o nome do bloco descreve, sem inventar fatos.', true)
ON CONFLICT (nome) DO NOTHING;
-- END seed_sql
-- Every seeded row records its creation (idempotent: a row that already has a `criado` event gets no second one).
INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, ator_id)
SELECT t.id, 'criado', NULL
  FROM social_wiring.cs_estrutura_tipos_bloco t
 WHERE NOT EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_tipo_eventos e WHERE e.tipo_id = t.id AND e.tipo = 'criado');

-- ----------------------------------------------------------------------------
-- 9. Derived view: blocos_total / campos_pendentes / busca (never stored)
-- ----------------------------------------------------------------------------
-- campos_pendentes = fields still `referencia` or `ia_sugerido`: the 3 estrutura columns + (nome, tipo, tempo,
-- instrucao) x blocks (the contract lists tipo/tempo/instrucao; nome is added: an AI draft's names are ia_sugerido).
-- busca = formula + block names, for the admin/library search (PostgREST `wfts`, 'portuguese').
-- security_invoker: the view reads with the CALLER's privileges (service role only).
CREATE OR REPLACE VIEW social_wiring.cs_estruturas_resumo
WITH (security_invoker = true) AS
SELECT e.id,
       e.codigo,
       e.perfil_id,
       e.viral_id,
       e.formula_headline,
       e.formato,
       e.objetivos,
       e.status,
       e.origem,
       e.updated_at,
       e.created_at,
       (SELECT count(*) FROM social_wiring.cs_estrutura_blocos b WHERE b.estrutura_id = e.id)::int AS blocos_total,
       ( (e.formula_origem IN ('referencia', 'ia_sugerido'))::int
       + (e.formato_origem IN ('referencia', 'ia_sugerido'))::int
       + (e.objetivos_origem IN ('referencia', 'ia_sugerido'))::int
       + COALESCE((SELECT sum((b.nome_origem IN ('referencia', 'ia_sugerido'))::int
                            + (b.tipo_origem IN ('referencia', 'ia_sugerido'))::int
                            + (b.tempo_origem IN ('referencia', 'ia_sugerido'))::int
                            + (b.instrucao_origem IN ('referencia', 'ia_sugerido'))::int)
                     FROM social_wiring.cs_estrutura_blocos b WHERE b.estrutura_id = e.id), 0)
       )::int AS campos_pendentes,
       to_tsvector('portuguese', e.formula_headline || ' '
                   || COALESCE((SELECT string_agg(b.nome, ' ') FROM social_wiring.cs_estrutura_blocos b
                                 WHERE b.estrutura_id = e.id), '')) AS busca
  FROM social_wiring.cs_estruturas e;

-- ----------------------------------------------------------------------------
-- 10. RPCs (service role only; SECURITY DEFINER, REVOKE EXECUTE below). One call = one transaction.
-- ----------------------------------------------------------------------------
-- Refusals are coded exceptions: RAISE EXCEPTION '<code>' [USING DETAIL = '<csv>'], mapped to HTTP by the API.

-- 10.0 internal helpers (not part of the contract surface; no grant to any API role)
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_evento(
    p_estrutura_id UUID, p_perfil_id UUID, p_tipo TEXT, p_campo TEXT, p_anterior TEXT, p_nova TEXT,
    p_ator UUID, p_ator_tipo TEXT, p_importacao UUID, p_versao INTEGER)
RETURNS void
LANGUAGE sql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
    INSERT INTO social_wiring.cs_estrutura_eventos
        (estrutura_id, perfil_id, tipo, campo, origem_anterior, origem_nova, ator_id, ator_tipo, importacao_id, versao)
    VALUES (p_estrutura_id, p_perfil_id, p_tipo, p_campo, p_anterior, p_nova, p_ator, p_ator_tipo, p_importacao, p_versao);
$fn$;

-- Row-lock the Estrutura and check the optimistic-concurrency token (NULL = no check).
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_travar(p_id UUID, p_expected_versao INTEGER)
RETURNS social_wiring.cs_estruturas
LANGUAGE plpgsql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r social_wiring.cs_estruturas;
BEGIN
    SELECT * INTO r FROM social_wiring.cs_estruturas WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'estrutura_nao_encontrada';
    END IF;
    IF p_expected_versao IS NOT NULL AND r.versao <> p_expected_versao THEN
        RAISE EXCEPTION 'versao_desatualizada';
    END IF;
    RETURN r;
END;
$fn$;

-- 10.1 criar -----------------------------------------------------------------
-- p = {perfil_id, viral_id?, formula_headline, formato?, objetivos[], status?('ativa'), origem?('manual'),
--      fonte_externa?, ref_externa?, fonte_hash?, formula_herdada_de?, referencia_rotulo?,
--      formula_origem?, formato_origem?, objetivos_origem? (default 'admin'), ator_id?, ator_tipo?, importacao_id?,
--      blocos: [{nome, tipo_id, tempo?, instrucao?, nota?, repeticoes?, nome_origem?, tipo_origem?, tempo_origem?,
--      instrucao_origem?}]}
-- Returns {id, codigo, versao}. The event is `criada` (manual) / `importada` (import_*) / `criada_automatica`
-- (viral_auto), plus `ia_preenchida` when any field is `ia_sugerido`.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_criar(p JSONB)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_id        UUID := gen_random_uuid();
    v_perfil    UUID := NULLIF(p ->> 'perfil_id', '')::uuid;
    v_viral     UUID := NULLIF(p ->> 'viral_id', '')::uuid;
    v_origem    TEXT := COALESCE(NULLIF(p ->> 'origem', ''), 'manual');
    v_status    TEXT := COALESCE(NULLIF(p ->> 'status', ''), 'ativa');
    v_ator      UUID := NULLIF(p ->> 'ator_id', '')::uuid;
    v_ator_tipo TEXT := COALESCE(NULLIF(p ->> 'ator_tipo', ''),
                                 CASE v_origem WHEN 'manual' THEN 'admin' WHEN 'viral_auto' THEN 'sistema_ia' ELSE 'sistema_import' END);
    v_imp       UUID := NULLIF(p ->> 'importacao_id', '')::uuid;
    v_blocos    JSONB := COALESCE(p -> 'blocos', '[]'::jsonb);
    v_formula   TEXT := btrim(COALESCE(p ->> 'formula_headline', ''));
    v_formato   TEXT := NULLIF(p ->> 'formato', '');
    v_obj       TEXT[];
    v_f_o       TEXT := COALESCE(NULLIF(p ->> 'formula_origem', ''), 'admin');
    v_fo_o      TEXT := COALESCE(NULLIF(p ->> 'formato_origem', ''), 'admin');
    v_ob_o      TEXT := COALESCE(NULLIF(p ->> 'objetivos_origem', ''), 'admin');
    v_n         INTEGER;
    v_codigo    BIGINT;
    v_b         JSONB;
    v_i         INTEGER := 0;
    v_ia        BOOLEAN;
    v_falta     TEXT[] := '{}'::text[];
BEGIN
    IF jsonb_typeof(v_blocos) <> 'array' THEN
        RAISE EXCEPTION 'blocos_invalidos';
    END IF;
    v_n := jsonb_array_length(v_blocos);
    IF v_n > 60 THEN
        RAISE EXCEPTION 'blocos_invalidos' USING DETAIL = 'max 60';
    END IF;
    IF v_formula = '' THEN
        RAISE EXCEPTION 'formula_invalida';
    END IF;
    v_obj := ARRAY(SELECT jsonb_array_elements_text(COALESCE(p -> 'objetivos', '[]'::jsonb)));
    IF v_status = 'ativa' THEN
        IF v_formato IS NULL THEN v_falta := array_append(v_falta, 'formato'::text); END IF;
        IF cardinality(v_obj) < 1 THEN v_falta := array_append(v_falta, 'objetivos'::text); END IF;
        IF v_n < 1 THEN v_falta := array_append(v_falta, 'blocos'::text); END IF;
        IF cardinality(v_falta) > 0 THEN
            RAISE EXCEPTION 'estrutura_incompleta' USING DETAIL = array_to_string(v_falta, ',');
        END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_perfis_monitorados WHERE id = v_perfil) THEN
        RAISE EXCEPTION 'perfil_nao_encontrado';
    END IF;
    IF v_viral IS NOT NULL AND NOT EXISTS (SELECT 1 FROM social_wiring.cs_virais WHERE id = v_viral) THEN
        RAISE EXCEPTION 'viral_nao_encontrado';
    END IF;

    INSERT INTO social_wiring.cs_estruturas
        (id, perfil_id, viral_id, formula_headline, formato, objetivos, status, origem, fonte_externa, ref_externa,
         fonte_hash, formula_herdada_de, referencia_rotulo, formula_origem, formato_origem, objetivos_origem,
         created_by, updated_by, publicada_em)
    VALUES (v_id, v_perfil, v_viral, v_formula, v_formato, v_obj, v_status, v_origem,
            NULLIF(p ->> 'fonte_externa', ''), NULLIF(p ->> 'ref_externa', ''), NULLIF(p ->> 'fonte_hash', ''),
            NULLIF(p ->> 'formula_herdada_de', ''), NULLIF(p ->> 'referencia_rotulo', ''),
            v_f_o, v_fo_o, v_ob_o,
            CASE WHEN v_ator_tipo = 'admin' THEN v_ator END, CASE WHEN v_ator_tipo = 'admin' THEN v_ator END,
            CASE WHEN v_status = 'ativa' THEN now() END)
    RETURNING codigo INTO v_codigo;

    v_ia := (v_f_o = 'ia_sugerido' OR v_fo_o = 'ia_sugerido' OR v_ob_o = 'ia_sugerido');
    FOR v_b IN SELECT * FROM jsonb_array_elements(v_blocos) LOOP
        v_i := v_i + 1;
        IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_tipos_bloco WHERE id = NULLIF(v_b ->> 'tipo_id', '')::uuid) THEN
            RAISE EXCEPTION 'tipo_nao_encontrado';
        END IF;
        INSERT INTO social_wiring.cs_estrutura_blocos
            (estrutura_id, ordem, tipo_id, nome, tempo, instrucao, nota, repeticoes,
             nome_origem, tipo_origem, tempo_origem, instrucao_origem)
        VALUES (v_id, v_i, (v_b ->> 'tipo_id')::uuid, btrim(v_b ->> 'nome'),
                NULLIF(btrim(COALESCE(v_b ->> 'tempo', '')), ''), NULLIF(btrim(COALESCE(v_b ->> 'instrucao', '')), ''),
                NULLIF(btrim(COALESCE(v_b ->> 'nota', '')), ''), COALESCE(NULLIF(v_b ->> 'repeticoes', '')::int, 1),
                COALESCE(NULLIF(v_b ->> 'nome_origem', ''), 'admin'), COALESCE(NULLIF(v_b ->> 'tipo_origem', ''), 'admin'),
                COALESCE(NULLIF(v_b ->> 'tempo_origem', ''), 'admin'), COALESCE(NULLIF(v_b ->> 'instrucao_origem', ''), 'admin'));
        IF 'ia_sugerido' IN (COALESCE(v_b ->> 'nome_origem', ''), COALESCE(v_b ->> 'tipo_origem', ''),
                             COALESCE(v_b ->> 'tempo_origem', ''), COALESCE(v_b ->> 'instrucao_origem', '')) THEN
            v_ia := true;
        END IF;
    END LOOP;

    PERFORM social_wiring.cs_estrutura_evento(
        v_id, v_perfil,
        CASE v_origem WHEN 'manual' THEN 'criada' WHEN 'viral_auto' THEN 'criada_automatica' ELSE 'importada' END,
        NULL, NULL, NULL, v_ator, v_ator_tipo, v_imp, 1);
    IF v_ia THEN
        PERFORM social_wiring.cs_estrutura_evento(v_id, v_perfil, 'ia_preenchida', NULL, NULL, 'ia_sugerido', v_ator, v_ator_tipo, v_imp, 1);
    END IF;
    RETURN jsonb_build_object('id', v_id, 'codigo', v_codigo, 'versao', 1);
END;
$fn$;

-- 10.2 atualizar -------------------------------------------------------------
-- p_patch keys: formula_headline, formato, objetivos, viral_id (null clears), and for a system actor also
-- formula_origem / formato_origem / objetivos_origem, fonte_hash, formula_herdada_de, referencia_rotulo,
-- _ator_tipo ('admin' default), _evento ('campo_editado' default | 'atualizada_import'), _importacao_id.
-- A field the patch CHANGES gets its origem (default 'admin') and one event; an unchanged field is untouched and
-- writes nothing; nothing changed = no version bump. Returns {id, versao, alterada}.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_atualizar(
    p_id UUID, p_expected_versao INTEGER, p_patch JSONB, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r          social_wiring.cs_estruturas;
    v_ator_tipo TEXT := COALESCE(NULLIF(p_patch ->> '_ator_tipo', ''), 'admin');
    v_evento   TEXT := COALESCE(NULLIF(p_patch ->> '_evento', ''), 'campo_editado');
    v_imp      UUID := NULLIF(p_patch ->> '_importacao_id', '')::uuid;
    v_nv       INTEGER;
    v_formula  TEXT := r.formula_headline;
    v_formula_o TEXT;
    v_formato  TEXT;
    v_formato_o TEXT;
    v_obj      TEXT[];
    v_obj_o    TEXT;
    v_viral    UUID;
    v_hash     TEXT;
    v_herdada  TEXT;
    v_rotulo   TEXT;
    v_mudou    BOOLEAN := false;
    v_eventou  BOOLEAN := false;
    v_novo     TEXT;
BEGIN
    r := social_wiring.cs_estrutura_travar(p_id, p_expected_versao);
    IF r.status = 'arquivada' THEN
        RAISE EXCEPTION 'estrutura_inativa';
    END IF;
    v_nv := r.versao + 1;
    v_formula := r.formula_headline;   v_formula_o := r.formula_origem;
    v_formato := r.formato;            v_formato_o := r.formato_origem;
    v_obj := r.objetivos;              v_obj_o := r.objetivos_origem;
    v_viral := r.viral_id;             v_hash := r.fonte_hash;
    v_herdada := r.formula_herdada_de; v_rotulo := r.referencia_rotulo;

    IF p_patch ? 'formula_headline' THEN
        v_novo := btrim(COALESCE(p_patch ->> 'formula_headline', ''));
        IF v_novo = '' THEN
            RAISE EXCEPTION 'formula_invalida';
        END IF;
        IF v_novo IS DISTINCT FROM r.formula_headline THEN
            v_formula := v_novo;
            v_formula_o := COALESCE(NULLIF(p_patch ->> 'formula_origem', ''), 'admin');
            PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'formula_headline', r.formula_origem, v_formula_o, p_ator, v_ator_tipo, v_imp, v_nv);
            v_mudou := true; v_eventou := true;
        END IF;
    END IF;
    IF p_patch ? 'formato' THEN
        v_novo := NULLIF(p_patch ->> 'formato', '');
        IF v_novo IS DISTINCT FROM r.formato THEN
            v_formato := v_novo;
            v_formato_o := COALESCE(NULLIF(p_patch ->> 'formato_origem', ''), 'admin');
            PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'formato', r.formato_origem, v_formato_o, p_ator, v_ator_tipo, v_imp, v_nv);
            v_mudou := true; v_eventou := true;
        END IF;
    END IF;
    IF p_patch ? 'objetivos' THEN
        IF ARRAY(SELECT jsonb_array_elements_text(COALESCE(p_patch -> 'objetivos', '[]'::jsonb))) IS DISTINCT FROM r.objetivos THEN
            v_obj := ARRAY(SELECT jsonb_array_elements_text(COALESCE(p_patch -> 'objetivos', '[]'::jsonb)));
            v_obj_o := COALESCE(NULLIF(p_patch ->> 'objetivos_origem', ''), 'admin');
            PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'objetivos', r.objetivos_origem, v_obj_o, p_ator, v_ator_tipo, v_imp, v_nv);
            v_mudou := true; v_eventou := true;
        END IF;
    END IF;
    IF p_patch ? 'viral_id' THEN
        IF NULLIF(p_patch ->> 'viral_id', '')::uuid IS DISTINCT FROM r.viral_id THEN
            v_viral := NULLIF(p_patch ->> 'viral_id', '')::uuid;
            IF v_viral IS NOT NULL AND NOT EXISTS (SELECT 1 FROM social_wiring.cs_virais WHERE id = v_viral) THEN
                RAISE EXCEPTION 'viral_nao_encontrado';
            END IF;
            PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'viral_id', NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
            v_mudou := true; v_eventou := true;
        END IF;
    END IF;
    -- source metadata (a load re-stamping its hash / label): a change, no field provenance
    IF p_patch ? 'fonte_hash' AND NULLIF(p_patch ->> 'fonte_hash', '') IS DISTINCT FROM r.fonte_hash THEN
        v_hash := NULLIF(p_patch ->> 'fonte_hash', ''); v_mudou := true;
    END IF;
    IF p_patch ? 'formula_herdada_de' AND NULLIF(p_patch ->> 'formula_herdada_de', '') IS DISTINCT FROM r.formula_herdada_de THEN
        v_herdada := NULLIF(p_patch ->> 'formula_herdada_de', ''); v_mudou := true;
    END IF;
    IF p_patch ? 'referencia_rotulo' AND NULLIF(p_patch ->> 'referencia_rotulo', '') IS DISTINCT FROM r.referencia_rotulo THEN
        v_rotulo := NULLIF(p_patch ->> 'referencia_rotulo', ''); v_mudou := true;
    END IF;

    IF NOT v_mudou THEN
        RETURN jsonb_build_object('id', p_id, 'versao', r.versao, 'alterada', false);
    END IF;
    IF r.status = 'ativa' AND (v_formato IS NULL OR cardinality(v_obj) < 1) THEN
        RAISE EXCEPTION 'estrutura_incompleta' USING DETAIL = 'formato,objetivos';
    END IF;
    IF NOT v_eventou AND v_evento = 'atualizada_import' THEN
        PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'atualizada_import', NULL, NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
    END IF;
    UPDATE social_wiring.cs_estruturas
       SET formula_headline = v_formula, formula_origem = v_formula_o,
           formato = v_formato, formato_origem = v_formato_o,
           objetivos = v_obj, objetivos_origem = v_obj_o,
           viral_id = v_viral, fonte_hash = v_hash, formula_herdada_de = v_herdada, referencia_rotulo = v_rotulo,
           versao = v_nv, updated_at = now(), updated_by = CASE WHEN v_ator_tipo = 'admin' THEN p_ator END
     WHERE id = p_id;
    RETURN jsonb_build_object('id', p_id, 'versao', v_nv, 'alterada', true);
END;
$fn$;

-- 10.3 substituir_blocos -----------------------------------------------------
-- p_blocos = the FULL ordered list (position = ordem) [{id?, nome, tipo_id, tempo?, instrucao?, nota?, repeticoes?,
-- nome_origem?, tipo_origem?, tempo_origem?, instrucao_origem?}], or an object {blocos:[...], ator_tipo?, evento?,
-- importacao_id?} for a system actor. A block with `id` keeps its identity AND its provenance for unchanged fields
-- (a changed field -> its origem, default 'admin'); no id = new; absent = removed. Returns {id, versao, alterada}.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_substituir_blocos(
    p_id UUID, p_expected_versao INTEGER, p_blocos JSONB, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r           social_wiring.cs_estruturas;
    o           social_wiring.cs_estrutura_blocos;
    v_arr       JSONB;
    v_opts      JSONB := '{}'::jsonb;
    v_ator_tipo TEXT := 'admin';
    v_evento    TEXT := 'campo_editado';
    v_imp       UUID;
    v_nv        INTEGER;
    v_n         INTEGER;
    v_b         JSONB;
    v_i         INTEGER := 0;
    v_bid       UUID;
    v_ids       UUID[] := '{}'::uuid[];
    v_seq_old   UUID[];
    v_seq_new   UUID[] := '{}'::uuid[];
    v_mudou     BOOLEAN := false;
    v_tipo      UUID;
    v_nome      TEXT;
    v_tempo     TEXT;
    v_instr     TEXT;
    v_nota      TEXT;
    v_rep       INTEGER;
    v_nome_o    TEXT;
    v_tipo_o    TEXT;
    v_tempo_o   TEXT;
    v_instr_o   TEXT;
    v_campo     TEXT;
BEGIN
    IF jsonb_typeof(p_blocos) = 'object' THEN
        v_opts := p_blocos;
        v_arr := p_blocos -> 'blocos';
    ELSE
        v_arr := p_blocos;
    END IF;
    IF v_arr IS NULL OR jsonb_typeof(v_arr) <> 'array' THEN
        RAISE EXCEPTION 'blocos_invalidos';
    END IF;
    v_ator_tipo := COALESCE(NULLIF(v_opts ->> 'ator_tipo', ''), 'admin');
    v_evento := COALESCE(NULLIF(v_opts ->> 'evento', ''), 'campo_editado');
    v_imp := NULLIF(v_opts ->> 'importacao_id', '')::uuid;
    v_n := jsonb_array_length(v_arr);
    IF v_n < 1 OR v_n > 60 THEN
        RAISE EXCEPTION 'blocos_invalidos' USING DETAIL = 'between 1 and 60';
    END IF;

    r := social_wiring.cs_estrutura_travar(p_id, p_expected_versao);
    IF r.status = 'arquivada' THEN
        RAISE EXCEPTION 'estrutura_inativa';
    END IF;
    v_nv := r.versao + 1;

    -- validate every element before the first write
    FOR v_b IN SELECT * FROM jsonb_array_elements(v_arr) LOOP
        v_bid := NULLIF(v_b ->> 'id', '')::uuid;
        IF v_bid IS NOT NULL THEN
            IF v_bid = ANY (v_ids) THEN
                RAISE EXCEPTION 'blocos_invalidos' USING DETAIL = 'duplicate id';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_blocos WHERE id = v_bid AND estrutura_id = p_id) THEN
                RAISE EXCEPTION 'bloco_nao_encontrado';
            END IF;
            v_ids := v_ids || v_bid;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_tipos_bloco WHERE id = NULLIF(v_b ->> 'tipo_id', '')::uuid) THEN
            RAISE EXCEPTION 'tipo_nao_encontrado';
        END IF;
    END LOOP;

    SELECT COALESCE(array_agg(b.id ORDER BY b.ordem) FILTER (WHERE b.id = ANY (v_ids)), '{}'::uuid[])
      INTO v_seq_old FROM social_wiring.cs_estrutura_blocos b WHERE b.estrutura_id = p_id;

    -- removed blocks
    FOR o IN SELECT * FROM social_wiring.cs_estrutura_blocos WHERE estrutura_id = p_id AND NOT (id = ANY (v_ids)) ORDER BY ordem LOOP
        DELETE FROM social_wiring.cs_estrutura_blocos WHERE id = o.id;
        PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'bloco_removido', 'bloco.' || o.id::text, NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
        v_mudou := true;
    END LOOP;

    -- kept / new blocks, in the requested order
    FOR v_b IN SELECT * FROM jsonb_array_elements(v_arr) LOOP
        v_i := v_i + 1;
        v_bid := NULLIF(v_b ->> 'id', '')::uuid;
        v_tipo := (v_b ->> 'tipo_id')::uuid;
        v_nome := btrim(COALESCE(v_b ->> 'nome', ''));
        v_tempo := NULLIF(btrim(COALESCE(v_b ->> 'tempo', '')), '');
        v_instr := NULLIF(btrim(COALESCE(v_b ->> 'instrucao', '')), '');
        v_nota := NULLIF(btrim(COALESCE(v_b ->> 'nota', '')), '');
        v_rep := COALESCE(NULLIF(v_b ->> 'repeticoes', '')::int, 1);
        IF v_nome = '' THEN
            RAISE EXCEPTION 'blocos_invalidos' USING DETAIL = 'nome';
        END IF;
        IF v_bid IS NULL THEN
            v_bid := gen_random_uuid();
            INSERT INTO social_wiring.cs_estrutura_blocos
                (id, estrutura_id, ordem, tipo_id, nome, tempo, instrucao, nota, repeticoes,
                 nome_origem, tipo_origem, tempo_origem, instrucao_origem)
            VALUES (v_bid, p_id, v_i, v_tipo, v_nome, v_tempo, v_instr, v_nota, v_rep,
                    COALESCE(NULLIF(v_b ->> 'nome_origem', ''), 'admin'), COALESCE(NULLIF(v_b ->> 'tipo_origem', ''), 'admin'),
                    COALESCE(NULLIF(v_b ->> 'tempo_origem', ''), 'admin'), COALESCE(NULLIF(v_b ->> 'instrucao_origem', ''), 'admin'));
            PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'bloco_adicionado', 'bloco.' || v_bid::text, NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
            v_mudou := true;
        ELSE
            v_seq_new := v_seq_new || v_bid;
            SELECT * INTO o FROM social_wiring.cs_estrutura_blocos WHERE id = v_bid;
            v_nome_o := o.nome_origem; v_tipo_o := o.tipo_origem; v_tempo_o := o.tempo_origem; v_instr_o := o.instrucao_origem;
            IF v_nome IS DISTINCT FROM o.nome THEN
                v_nome_o := COALESCE(NULLIF(v_b ->> 'nome_origem', ''), 'admin');
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'bloco.' || v_bid::text || '.nome', o.nome_origem, v_nome_o, p_ator, v_ator_tipo, v_imp, v_nv);
                v_mudou := true;
            END IF;
            IF v_tipo IS DISTINCT FROM o.tipo_id THEN
                v_tipo_o := COALESCE(NULLIF(v_b ->> 'tipo_origem', ''), 'admin');
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'bloco.' || v_bid::text || '.tipo', o.tipo_origem, v_tipo_o, p_ator, v_ator_tipo, v_imp, v_nv);
                v_mudou := true;
            END IF;
            IF v_tempo IS DISTINCT FROM o.tempo THEN
                v_tempo_o := COALESCE(NULLIF(v_b ->> 'tempo_origem', ''), 'admin');
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'bloco.' || v_bid::text || '.tempo', o.tempo_origem, v_tempo_o, p_ator, v_ator_tipo, v_imp, v_nv);
                v_mudou := true;
            END IF;
            IF v_instr IS DISTINCT FROM o.instrucao THEN
                v_instr_o := COALESCE(NULLIF(v_b ->> 'instrucao_origem', ''), 'admin');
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'bloco.' || v_bid::text || '.instrucao', o.instrucao_origem, v_instr_o, p_ator, v_ator_tipo, v_imp, v_nv);
                v_mudou := true;
            END IF;
            IF v_nota IS DISTINCT FROM o.nota THEN
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'bloco.' || v_bid::text || '.nota', NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
                v_mudou := true;
            END IF;
            IF v_rep IS DISTINCT FROM o.repeticoes THEN
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, v_evento, 'bloco.' || v_bid::text || '.repeticoes', NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
                v_mudou := true;
            END IF;
            UPDATE social_wiring.cs_estrutura_blocos
               SET ordem = v_i, tipo_id = v_tipo, nome = v_nome, tempo = v_tempo, instrucao = v_instr, nota = v_nota,
                   repeticoes = v_rep, nome_origem = v_nome_o, tipo_origem = v_tipo_o, tempo_origem = v_tempo_o,
                   instrucao_origem = v_instr_o
             WHERE id = v_bid
               AND (ordem, tipo_id, nome, tempo, instrucao, nota, repeticoes, nome_origem, tipo_origem, tempo_origem, instrucao_origem)
                   IS DISTINCT FROM
                   (v_i, v_tipo, v_nome, v_tempo, v_instr, v_nota, v_rep, v_nome_o, v_tipo_o, v_tempo_o, v_instr_o);
        END IF;
    END LOOP;

    IF v_seq_new IS DISTINCT FROM v_seq_old THEN
        PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'blocos_reordenados', NULL, NULL, NULL, p_ator, v_ator_tipo, v_imp, v_nv);
        v_mudou := true;
    END IF;

    IF NOT v_mudou THEN
        RETURN jsonb_build_object('id', p_id, 'versao', r.versao, 'alterada', false);
    END IF;
    UPDATE social_wiring.cs_estruturas
       SET versao = v_nv, updated_at = now(), updated_by = CASE WHEN v_ator_tipo = 'admin' THEN p_ator END
     WHERE id = p_id;
    RETURN jsonb_build_object('id', p_id, 'versao', v_nv, 'alterada', true);
END;
$fn$;

-- 10.4 confirmar -------------------------------------------------------------
-- p_campos: formula_headline | formato | objetivos | bloco.<id>.(nome|tipo|tempo|instrucao); ARRAY['*'] = every
-- field. `referencia`/`ia_sugerido` -> `admin` (content untouched, one `campo_confirmado` event per field flipped);
-- a field already `fonte`/`admin` is a no-op. Returns {id, versao, confirmados}.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_confirmar(
    p_id UUID, p_expected_versao INTEGER, p_campos TEXT[], p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r        social_wiring.cs_estruturas;
    b        social_wiring.cs_estrutura_blocos;
    v_campos TEXT[] := p_campos;
    v_c      TEXT;
    v_bid    UUID;
    v_col    TEXT;
    v_n      INTEGER := 0;
    v_nv     INTEGER;
    v_pend   TEXT[] := ARRAY['referencia', 'ia_sugerido']::text[];
BEGIN
    r := social_wiring.cs_estrutura_travar(p_id, p_expected_versao);
    v_nv := r.versao + 1;
    IF v_campos IS NULL OR cardinality(v_campos) = 0 THEN
        RAISE EXCEPTION 'campo_desconhecido';
    END IF;
    IF v_campos = ARRAY['*']::text[] THEN
        v_campos := ARRAY['formula_headline', 'formato', 'objetivos']::text[]
            || ARRAY(SELECT 'bloco.' || bl.id::text || '.' || c.col
                       FROM social_wiring.cs_estrutura_blocos bl
                      CROSS JOIN (VALUES ('nome'), ('tipo'), ('tempo'), ('instrucao')) AS c(col)
                      WHERE bl.estrutura_id = p_id ORDER BY bl.ordem, c.col);
    END IF;
    FOREACH v_c IN ARRAY v_campos LOOP
        IF v_c = 'formula_headline' THEN
            IF r.formula_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estruturas SET formula_origem = 'admin' WHERE id = p_id;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, r.formula_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            END IF;
        ELSIF v_c = 'formato' THEN
            IF r.formato_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estruturas SET formato_origem = 'admin' WHERE id = p_id;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, r.formato_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            END IF;
        ELSIF v_c = 'objetivos' THEN
            IF r.objetivos_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estruturas SET objetivos_origem = 'admin' WHERE id = p_id;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, r.objetivos_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            END IF;
        ELSIF v_c ~ '^bloco\.[0-9a-fA-F-]{36}\.(nome|tipo|tempo|instrucao)$' THEN
            v_bid := split_part(v_c, '.', 2)::uuid;
            v_col := split_part(v_c, '.', 3);
            SELECT * INTO b FROM social_wiring.cs_estrutura_blocos WHERE id = v_bid AND estrutura_id = p_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'campo_desconhecido';
            END IF;
            IF v_col = 'nome' AND b.nome_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estrutura_blocos SET nome_origem = 'admin' WHERE id = v_bid;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, b.nome_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            ELSIF v_col = 'tipo' AND b.tipo_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estrutura_blocos SET tipo_origem = 'admin' WHERE id = v_bid;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, b.tipo_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            ELSIF v_col = 'tempo' AND b.tempo_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estrutura_blocos SET tempo_origem = 'admin' WHERE id = v_bid;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, b.tempo_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            ELSIF v_col = 'instrucao' AND b.instrucao_origem = ANY (v_pend) THEN
                UPDATE social_wiring.cs_estrutura_blocos SET instrucao_origem = 'admin' WHERE id = v_bid;
                PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'campo_confirmado', v_c, b.instrucao_origem, 'admin', p_ator, 'admin', NULL, v_nv);
                v_n := v_n + 1;
            END IF;
        ELSE
            RAISE EXCEPTION 'campo_desconhecido';
        END IF;
    END LOOP;
    IF v_n = 0 THEN
        RETURN jsonb_build_object('id', p_id, 'versao', r.versao, 'confirmados', 0);
    END IF;
    UPDATE social_wiring.cs_estruturas SET versao = v_nv, updated_at = now(), updated_by = p_ator WHERE id = p_id;
    RETURN jsonb_build_object('id', p_id, 'versao', v_nv, 'confirmados', v_n);
END;
$fn$;

-- 10.5 publicar --------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_publicar(p_id UUID, p_expected_versao INTEGER, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r       social_wiring.cs_estruturas;
    v_falta TEXT[] := '{}'::text[];
    v_nv    INTEGER;
BEGIN
    r := social_wiring.cs_estrutura_travar(p_id, p_expected_versao);
    IF r.status <> 'rascunho' THEN
        RAISE EXCEPTION 'estrutura_inativa';
    END IF;
    IF r.formato IS NULL THEN v_falta := array_append(v_falta, 'formato'::text); END IF;
    IF cardinality(r.objetivos) < 1 THEN v_falta := array_append(v_falta, 'objetivos'::text); END IF;
    IF NOT EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_blocos WHERE estrutura_id = p_id) THEN
        v_falta := array_append(v_falta, 'blocos'::text);
    END IF;
    IF cardinality(v_falta) > 0 THEN
        RAISE EXCEPTION 'rascunho_incompleto' USING DETAIL = array_to_string(v_falta, ',');
    END IF;
    v_nv := r.versao + 1;
    UPDATE social_wiring.cs_estruturas
       SET status = 'ativa', publicada_em = now(), versao = v_nv, updated_at = now(), updated_by = p_ator
     WHERE id = p_id;
    PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'publicada', NULL, NULL, NULL, p_ator, 'admin', NULL, v_nv);
    RETURN jsonb_build_object('id', p_id, 'versao', v_nv, 'alterada', true);
END;
$fn$;

-- 10.6 arquivar / restaurar --------------------------------------------------
-- A `rascunho` can be archived too. Restore returns to `ativa` only when it was ever published, else `rascunho`.
-- Idempotent: archiving an archived row (or restoring a non-archived one) changes nothing.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_arquivar(p_id UUID, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r    social_wiring.cs_estruturas;
    v_nv INTEGER;
BEGIN
    r := social_wiring.cs_estrutura_travar(p_id, NULL);
    IF r.status = 'arquivada' THEN
        RETURN jsonb_build_object('id', p_id, 'versao', r.versao, 'alterada', false);
    END IF;
    v_nv := r.versao + 1;
    UPDATE social_wiring.cs_estruturas
       SET status = 'arquivada', arquivada_em = now(), versao = v_nv, updated_at = now(), updated_by = p_ator
     WHERE id = p_id;
    PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'arquivada', NULL, NULL, NULL, p_ator, 'admin', NULL, v_nv);
    RETURN jsonb_build_object('id', p_id, 'versao', v_nv, 'alterada', true);
END;
$fn$;

CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_restaurar(p_id UUID, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r    social_wiring.cs_estruturas;
    v_nv INTEGER;
BEGIN
    r := social_wiring.cs_estrutura_travar(p_id, NULL);
    IF r.status <> 'arquivada' THEN
        RETURN jsonb_build_object('id', p_id, 'versao', r.versao, 'alterada', false);
    END IF;
    v_nv := r.versao + 1;
    UPDATE social_wiring.cs_estruturas
       SET status = CASE WHEN r.publicada_em IS NOT NULL THEN 'ativa' ELSE 'rascunho' END,
           arquivada_em = NULL, versao = v_nv, updated_at = now(), updated_by = p_ator
     WHERE id = p_id;
    PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'restaurada', NULL, NULL, NULL, p_ator, 'admin', NULL, v_nv);
    RETURN jsonb_build_object('id', p_id, 'versao', v_nv, 'alterada', true);
END;
$fn$;

-- 10.7 excluir ---------------------------------------------------------------
-- Hard delete only when no use exists. The event is written first and has no FK, so it outlives the row.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_excluir(p_id UUID, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    r social_wiring.cs_estruturas;
BEGIN
    r := social_wiring.cs_estrutura_travar(p_id, NULL);
    IF EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_usos WHERE estrutura_id = p_id) THEN
        RAISE EXCEPTION 'estrutura_em_uso';
    END IF;
    PERFORM social_wiring.cs_estrutura_evento(p_id, r.perfil_id, 'excluida', NULL, NULL, NULL, p_ator, 'admin', NULL, r.versao);
    DELETE FROM social_wiring.cs_estruturas WHERE id = p_id;
    RETURN jsonb_build_object('id', p_id, 'excluida', true);
END;
$fn$;

-- 10.8 block-type catalog ----------------------------------------------------
-- p = {id?, expected_versao?, nome, tempo_tipico?, instrucao_referencia, ativo?, ordem?, ator_id?}. A new row lands
-- at `ordem` (default: last), shifting the others down; `Outro` (sistema) is never changed.
CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_tipo_salvar(p JSONB)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_id    UUID := NULLIF(p ->> 'id', '')::uuid;
    v_ator  UUID := NULLIF(p ->> 'ator_id', '')::uuid;
    t       social_wiring.cs_estrutura_tipos_bloco;
    v_nome  TEXT;
    v_tempo TEXT;
    v_instr TEXT;
    v_ativo BOOLEAN;
    v_ordem INTEGER;
    v_mudou BOOLEAN := false;
    v_nv    INTEGER;
BEGIN
    IF v_id IS NULL THEN
        v_nome := btrim(COALESCE(p ->> 'nome', ''));
        v_instr := btrim(COALESCE(p ->> 'instrucao_referencia', ''));
        IF v_nome = '' OR v_instr = '' THEN
            RAISE EXCEPTION 'tipo_invalido';
        END IF;
        v_ordem := COALESCE(NULLIF(p ->> 'ordem', '')::int,
                            (SELECT COALESCE(max(ordem), 0) + 1 FROM social_wiring.cs_estrutura_tipos_bloco));
        IF p ? 'ordem' THEN
            UPDATE social_wiring.cs_estrutura_tipos_bloco SET ordem = ordem + 1 WHERE ordem >= v_ordem;
        END IF;
        INSERT INTO social_wiring.cs_estrutura_tipos_bloco
            (nome, ordem, tempo_tipico, instrucao_referencia, ativo, created_by, updated_by)
        VALUES (v_nome, v_ordem, NULLIF(btrim(COALESCE(p ->> 'tempo_tipico', '')), ''), v_instr,
                COALESCE((p ->> 'ativo')::boolean, true), v_ator, v_ator)
        RETURNING id INTO v_id;
        INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, ator_id) VALUES (v_id, 'criado', v_ator);
        RETURN jsonb_build_object('id', v_id, 'versao', 1, 'alterada', true);
    END IF;

    SELECT * INTO t FROM social_wiring.cs_estrutura_tipos_bloco WHERE id = v_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tipo_nao_encontrado';
    END IF;
    IF NULLIF(p ->> 'expected_versao', '') IS NOT NULL AND (p ->> 'expected_versao')::int <> t.versao THEN
        RAISE EXCEPTION 'versao_desatualizada';
    END IF;
    IF t.sistema THEN
        RAISE EXCEPTION 'tipo_protegido';
    END IF;
    v_nv := t.versao + 1;
    v_nome := t.nome; v_tempo := t.tempo_tipico; v_instr := t.instrucao_referencia; v_ativo := t.ativo; v_ordem := t.ordem;
    IF p ? 'nome' AND btrim(COALESCE(p ->> 'nome', '')) <> '' AND btrim(p ->> 'nome') IS DISTINCT FROM t.nome THEN
        v_nome := btrim(p ->> 'nome'); v_mudou := true;
        INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, campo, ator_id) VALUES (v_id, 'editado', 'nome', v_ator);
    END IF;
    IF p ? 'tempo_tipico' AND NULLIF(btrim(COALESCE(p ->> 'tempo_tipico', '')), '') IS DISTINCT FROM t.tempo_tipico THEN
        v_tempo := NULLIF(btrim(COALESCE(p ->> 'tempo_tipico', '')), ''); v_mudou := true;
        INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, campo, ator_id) VALUES (v_id, 'editado', 'tempo_tipico', v_ator);
    END IF;
    IF p ? 'instrucao_referencia' AND btrim(COALESCE(p ->> 'instrucao_referencia', '')) <> ''
       AND btrim(p ->> 'instrucao_referencia') IS DISTINCT FROM t.instrucao_referencia THEN
        v_instr := btrim(p ->> 'instrucao_referencia'); v_mudou := true;
        INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, campo, ator_id) VALUES (v_id, 'editado', 'instrucao_referencia', v_ator);
    END IF;
    IF p ? 'ativo' AND (p ->> 'ativo')::boolean IS DISTINCT FROM t.ativo THEN
        v_ativo := (p ->> 'ativo')::boolean; v_mudou := true;
        INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, ator_id)
        VALUES (v_id, CASE WHEN v_ativo THEN 'ativado' ELSE 'desativado' END, v_ator);
    END IF;
    IF p ? 'ordem' AND NULLIF(p ->> 'ordem', '')::int IS DISTINCT FROM t.ordem THEN
        v_ordem := (p ->> 'ordem')::int; v_mudou := true;
        UPDATE social_wiring.cs_estrutura_tipos_bloco SET ordem = ordem + 1 WHERE ordem >= v_ordem AND id <> v_id;
        INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, campo, ator_id) VALUES (v_id, 'editado', 'ordem', v_ator);
    END IF;
    IF NOT v_mudou THEN
        RETURN jsonb_build_object('id', v_id, 'versao', t.versao, 'alterada', false);
    END IF;
    UPDATE social_wiring.cs_estrutura_tipos_bloco
       SET nome = v_nome, tempo_tipico = v_tempo, instrucao_referencia = v_instr, ativo = v_ativo, ordem = v_ordem,
           versao = v_nv, updated_at = now(), updated_by = v_ator
     WHERE id = v_id;
    RETURN jsonb_build_object('id', v_id, 'versao', v_nv, 'alterada', true);
END;
$fn$;

CREATE OR REPLACE FUNCTION social_wiring.cs_estrutura_tipo_excluir(p_id UUID, p_ator UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    t social_wiring.cs_estrutura_tipos_bloco;
BEGIN
    SELECT * INTO t FROM social_wiring.cs_estrutura_tipos_bloco WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tipo_nao_encontrado';
    END IF;
    IF t.sistema THEN
        RAISE EXCEPTION 'tipo_protegido';
    END IF;
    IF EXISTS (SELECT 1 FROM social_wiring.cs_estrutura_blocos WHERE tipo_id = p_id) THEN
        RAISE EXCEPTION 'tipo_em_uso';
    END IF;
    INSERT INTO social_wiring.cs_estrutura_tipo_eventos (tipo_id, tipo, ator_id) VALUES (p_id, 'excluido', p_ator);
    DELETE FROM social_wiring.cs_estrutura_tipos_bloco WHERE id = p_id;
    RETURN jsonb_build_object('id', p_id, 'excluido', true);
END;
$fn$;

-- ----------------------------------------------------------------------------
-- 11. RPC privileges: service role only (SECURITY DEFINER => no EXECUTE for PUBLIC / anon / authenticated)
-- ----------------------------------------------------------------------------
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_evento(UUID, UUID, TEXT, TEXT, TEXT, TEXT, UUID, TEXT, UUID, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_travar(UUID, INTEGER) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_criar(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_atualizar(UUID, INTEGER, JSONB, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_substituir_blocos(UUID, INTEGER, JSONB, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_confirmar(UUID, INTEGER, TEXT[], UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_publicar(UUID, INTEGER, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_arquivar(UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_restaurar(UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_excluir(UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_tipo_salvar(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_tipo_excluir(UUID, UUID) FROM PUBLIC, anon, authenticated;
-- The guard functions are trigger functions (never called directly); no browser role needs EXECUTE on them either.
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_tipos_bloco_protegido() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_eventos_imutavel() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_tipo_eventos_imutavel() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estrutura_usos_imutavel() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION social_wiring.cs_estruturas_recusa_truncate() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_criar(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_atualizar(UUID, INTEGER, JSONB, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_substituir_blocos(UUID, INTEGER, JSONB, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_confirmar(UUID, INTEGER, TEXT[], UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_publicar(UUID, INTEGER, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_arquivar(UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_restaurar(UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_excluir(UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_tipo_salvar(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.cs_estrutura_tipo_excluir(UUID, UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- 12. RLS + grants (service-only), tiers
-- ----------------------------------------------------------------------------
-- The service role READS the library tables and can write them ONLY through the RPCs above (DEFINER), so it holds
-- no INSERT/UPDATE/DELETE on cs_estruturas / cs_estrutura_blocos / cs_estrutura_tipos_bloco / the two event tables.
-- importacoes and usos are written by the service directly (state of a load run; an append-only fact).
ALTER TABLE social_wiring.cs_estrutura_tipos_bloco ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estrutura_tipos_bloco_service_role" ON social_wiring.cs_estrutura_tipos_bloco;
CREATE POLICY "cs_estrutura_tipos_bloco_service_role" ON social_wiring.cs_estrutura_tipos_bloco FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estrutura_tipos_bloco FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_estrutura_tipos_bloco TO service_role;

ALTER TABLE social_wiring.cs_estrutura_tipo_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estrutura_tipo_eventos_service_role" ON social_wiring.cs_estrutura_tipo_eventos;
CREATE POLICY "cs_estrutura_tipo_eventos_service_role" ON social_wiring.cs_estrutura_tipo_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estrutura_tipo_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_estrutura_tipo_eventos TO service_role;

ALTER TABLE social_wiring.cs_estruturas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estruturas_service_role" ON social_wiring.cs_estruturas;
CREATE POLICY "cs_estruturas_service_role" ON social_wiring.cs_estruturas FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estruturas FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_estruturas TO service_role;

ALTER TABLE social_wiring.cs_estrutura_blocos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estrutura_blocos_service_role" ON social_wiring.cs_estrutura_blocos;
CREATE POLICY "cs_estrutura_blocos_service_role" ON social_wiring.cs_estrutura_blocos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estrutura_blocos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_estrutura_blocos TO service_role;

ALTER TABLE social_wiring.cs_estrutura_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estrutura_eventos_service_role" ON social_wiring.cs_estrutura_eventos;
CREATE POLICY "cs_estrutura_eventos_service_role" ON social_wiring.cs_estrutura_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estrutura_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_estrutura_eventos TO service_role;

ALTER TABLE social_wiring.cs_estrutura_importacoes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estrutura_importacoes_service_role" ON social_wiring.cs_estrutura_importacoes;
CREATE POLICY "cs_estrutura_importacoes_service_role" ON social_wiring.cs_estrutura_importacoes FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estrutura_importacoes FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE social_wiring.cs_estrutura_importacoes TO service_role;

ALTER TABLE social_wiring.cs_estrutura_usos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_estrutura_usos_service_role" ON social_wiring.cs_estrutura_usos;
CREATE POLICY "cs_estrutura_usos_service_role" ON social_wiring.cs_estrutura_usos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_estrutura_usos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.cs_estrutura_usos TO service_role;

REVOKE ALL ON TABLE social_wiring.cs_estruturas_resumo FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE social_wiring.cs_estruturas_resumo TO service_role;

COMMENT ON TABLE social_wiring.cs_estrutura_tipos_bloco IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_estrutura_tipo_eventos IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_estruturas IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_estrutura_blocos IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_estrutura_eventos IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_estrutura_importacoes IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_estrutura_usos IS 'tier:org';
COMMENT ON VIEW social_wiring.cs_estruturas_resumo IS 'tier:platform';
COMMENT ON COLUMN social_wiring.cs_estruturas.formula_origem IS
    'Provenance (DC2): fonte | referencia | ia_sugerido | admin. referencia/ia_sugerido = pending review; shown to admins only. Migration 350.';
COMMENT ON COLUMN social_wiring.cs_estrutura_blocos.nota IS
    'The source''s parenthetical: describes the ORIGINAL video''s content. Shown, never templated. Migration 350.';
