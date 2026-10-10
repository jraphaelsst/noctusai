-- ============================================================================
-- Migration 229 · social_wiring: Geração (CoreStudio rebuild) — Meu Perfil columns,
-- static taxonomies, Biblioteca (monitored profiles, virais, per-marca allow-list),
-- Headlines (lotes + headlines), Roteiros, Chat (conversas, mensagens, memórias),
-- Treinamentos, the private `sw-biblioteca` bucket, the transcription "biblioteca"
-- lane (origem + reservar_transcricao_biblioteca) and the 10 `status_pagina` rows
-- ============================================================================
-- WHY
-- ---
-- Contract: projects/core-studio/specs/geracao-contract.md section 2 (+ 2.7 for the
-- transcription lane). ONE shared migration written by BE-0; no other slice writes SQL.
--
-- The static seed (nichos, profissoes, formatos de video, the 5 treinamentos) is GENERATED
-- from the Python source of truth (app/modules/media_creation/geracao_taxonomias.py ::
-- seed_sql()); a test asserts this file carries exactly that text.
--
-- RLS: every `org_id` table matches 217/224 (own-org authenticated, service_role ALL).
-- Exceptions: the static taxonomies and `cs_treinamentos` (authenticated SELECT true), and
-- `cs_chat_*` / `cs_memorias` (private to their user: AND user_id = auth.uid()).
--
-- `reservar_transcricao` (225) is REDEFINED so every counter sees only origem = 'usuario':
-- library rows can never cause a 429 / fila_cheia for a voice answer (contract 2.7 / 3.4).
--
-- FORWARD-ONLY, IDEMPOTENT. Requires 217, 221, 224 and 225.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'Migration 229 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.cs_research_items') IS NULL THEN
    RAISE EXCEPTION 'Migration 229 requires social_wiring.cs_research_items (migration 217) -- apply 217 first';
  END IF;
  IF to_regclass('social_wiring.cs_extraction_jobs') IS NULL THEN
    RAISE EXCEPTION 'Migration 229 requires social_wiring.cs_extraction_jobs (migration 221) -- apply 221 first';
  END IF;
  IF to_regclass('social_wiring.cs_marca_perfil') IS NULL THEN
    RAISE EXCEPTION 'Migration 229 requires social_wiring.cs_marca_perfil (migration 224) -- apply 224 first';
  END IF;
  IF to_regclass('social_wiring.transcricoes') IS NULL THEN
    RAISE EXCEPTION 'Migration 229 requires social_wiring.transcricoes (migration 225) -- apply 225 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Meu Perfil: new columns on cs_marca_perfil (same row as the cerebro bio card)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_marca_perfil
    ADD COLUMN IF NOT EXISTS nichos INTEGER[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS profissoes INTEGER[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS apresentacao_magnetica TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ctas TEXT NOT NULL DEFAULT '';

-- Postgres has no array FK: the service checks the ids against cs_nichos / cs_profissoes (422).
DO $chk$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_marca_perfil_nichos_max3') THEN
    ALTER TABLE social_wiring.cs_marca_perfil
      ADD CONSTRAINT cs_marca_perfil_nichos_max3 CHECK (cardinality(nichos) <= 3);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_marca_perfil_profissoes_max3') THEN
    ALTER TABLE social_wiring.cs_marca_perfil
      ADD CONSTRAINT cs_marca_perfil_profissoes_max3 CHECK (cardinality(profissoes) <= 3);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_marca_perfil_apresentacao_len') THEN
    ALTER TABLE social_wiring.cs_marca_perfil
      ADD CONSTRAINT cs_marca_perfil_apresentacao_len CHECK (char_length(apresentacao_magnetica) <= 3000);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_marca_perfil_ctas_len') THEN
    ALTER TABLE social_wiring.cs_marca_perfil
      ADD CONSTRAINT cs_marca_perfil_ctas_len CHECK (char_length(ctas) <= 3000);
  END IF;
END
$chk$;

-- ----------------------------------------------------------------------------
-- 2. Static taxonomies (seeded in section 12) + Treinamentos (platform-wide)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_nichos (
    id         INTEGER PRIMARY KEY,
    nome       TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);
COMMENT ON TABLE social_wiring.cs_nichos IS
    'Migration 229 - CoreStudio nichos (28 rows, CoreStudio ids). Seeded from geracao_taxonomias.py; read-only for authenticated users.';

CREATE TABLE IF NOT EXISTS social_wiring.cs_profissoes (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL
);
COMMENT ON TABLE social_wiring.cs_profissoes IS
    'Migration 229 - CoreStudio profissoes (102 rows, CoreStudio ids). Seeded from geracao_taxonomias.py; read-only for authenticated users.';

CREATE TABLE IF NOT EXISTS social_wiring.cs_formatos_video (
    id         INTEGER PRIMARY KEY,
    nome       TEXT NOT NULL,
    definicao  TEXT NOT NULL
);
COMMENT ON TABLE social_wiring.cs_formatos_video IS
    'Migration 229 - the 15 video formats and their classification definition. Seeded from geracao_taxonomias.py; read-only for authenticated users.';

CREATE TABLE IF NOT EXISTS social_wiring.cs_treinamentos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ordem       INTEGER NOT NULL UNIQUE,
    titulo      TEXT NOT NULL CHECK (char_length(titulo) BETWEEN 1 AND 160),
    descricao   TEXT NOT NULL DEFAULT '' CHECK (char_length(descricao) <= 1000),
    video_url   TEXT CHECK (video_url ~ '^https://'),
    ativo       BOOLEAN NOT NULL DEFAULT true,
    updated_by  UUID,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_treinamentos IS
    'Migration 229 - platform-wide training lessons (no org_id). Seeded with the 5 CoreStudio lessons, video_url NULL; '
    'writes go through the backend only (platform admin).';

-- ----------------------------------------------------------------------------
-- 3. Biblioteca: monitored profiles, virais, per-marca allow-list
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_perfis_monitorados (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    rede                 TEXT NOT NULL DEFAULT 'instagram' CHECK (rede IN ('instagram')),
    handle               TEXT NOT NULL CHECK (handle ~ '^[a-z0-9._]{1,30}$'),
    -- the provider='meta' (Facebook Login) account whose token runs Business Discovery
    conta_descoberta_id  UUID REFERENCES social_wiring.integration_accounts (id) ON DELETE SET NULL,
    ig_user_id           TEXT,
    nome                 TEXT,
    foto_path            TEXT,
    seguidores           BIGINT,
    media_count          INTEGER,
    status               TEXT NOT NULL DEFAULT 'aguardando'
                         CHECK (status IN ('aguardando', 'ativo', 'pausado', 'nao_encontrado', 'sem_conta', 'erro')),
    erro_codigo          TEXT,
    erro_mensagem        TEXT,
    ultima_sync_em       TIMESTAMPTZ,
    proxima_sync_em      TIMESTAMPTZ,
    metrica_base         TEXT NOT NULL DEFAULT 'engajamento' CHECK (metrica_base IN ('views', 'engajamento')),
    -- NULL = fewer than 10 posts ("dados insuficientes")
    mediana_metrica      NUMERIC,
    created_by           UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_perfis_monitorados IS
    'Migration 229 - Biblioteca corpus source: one row per Instagram handle per org, synced through Business Discovery.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_perfis_monitorados_org_handle_uq
    ON social_wiring.cs_perfis_monitorados (org_id, rede, handle);
CREATE INDEX IF NOT EXISTS cs_perfis_monitorados_sync_idx
    ON social_wiring.cs_perfis_monitorados (proxima_sync_em) WHERE status = 'ativo';

CREATE TABLE IF NOT EXISTS social_wiring.cs_virais (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    perfil_id             UUID NOT NULL REFERENCES social_wiring.cs_perfis_monitorados (id) ON DELETE CASCADE,
    -- short human id ("estrutura #codigo"), used in chat citations and deep links
    codigo                BIGINT GENERATED ALWAYS AS IDENTITY,
    ig_media_id           TEXT NOT NULL,
    permalink             TEXT,
    media_type            TEXT,
    media_product_type    TEXT,
    caption               TEXT CHECK (char_length(caption) <= 5000),
    publicado_em          TIMESTAMPTZ,
    -- NULL = the API did not serve it (never 0)
    likes                 BIGINT,
    comments              BIGINT,
    views                 BIGINT,
    duracao_s             NUMERIC,
    thumbnail_path        TEXT,
    metricas_em           TIMESTAMPTZ,
    score_viral           NUMERIC,
    e_viral               BOOLEAN NOT NULL DEFAULT false,
    transcricao_status    TEXT NOT NULL DEFAULT 'nao_aplicavel'
                          CHECK (transcricao_status IN ('nao_aplicavel', 'pendente', 'na_fila', 'concluida', 'falhou',
                                                        'grande_demais', 'longa_demais', 'sem_orcamento')),
    transcricao_id        UUID REFERENCES social_wiring.transcricoes (id) ON DELETE SET NULL,
    transcricao_texto     TEXT CHECK (char_length(transcricao_texto) <= 50000),
    classificacao_status  TEXT NOT NULL DEFAULT 'pendente'
                          CHECK (classificacao_status IN ('pendente', 'processando', 'concluida', 'falhou')),
    gancho                TEXT CHECK (char_length(gancho) <= 1000),
    blueprint             TEXT CHECK (char_length(blueprint) <= 10000),
    blueprint_slots       TEXT[] NOT NULL DEFAULT '{}',
    formato_ids           INTEGER[] NOT NULL DEFAULT '{}' CHECK (cardinality(formato_ids) <= 3),
    nicho_ids             INTEGER[] NOT NULL DEFAULT '{}' CHECK (cardinality(nicho_ids) <= 3),
    profissao_ids         INTEGER[] NOT NULL DEFAULT '{}' CHECK (cardinality(profissao_ids) <= 3),
    gatilho               TEXT CHECK (gatilho IN ('recompensa', 'misterio', 'reconhecimento', 'popularidade',
                                                  'crenca', 'autoridade', 'disrupcao')),
    classificado_em       TIMESTAMPTZ,
    classificacao_modelo  TEXT,
    classificacao_erro    TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_virais_org_codigo_uq UNIQUE (org_id, codigo)
);
COMMENT ON TABLE social_wiring.cs_virais IS
    'Migration 229 - one row per post of a monitored profile (every ingested post; e_viral flags the outliers). '
    'Thumbnails live in the private sw-biblioteca bucket; transcription mirrors the shared transcricoes row.';

CREATE UNIQUE INDEX IF NOT EXISTS cs_virais_perfil_media_uq
    ON social_wiring.cs_virais (perfil_id, ig_media_id);
CREATE INDEX IF NOT EXISTS cs_virais_org_viral_score_idx
    ON social_wiring.cs_virais (org_id, e_viral, score_viral DESC);
CREATE INDEX IF NOT EXISTS cs_virais_perfil_publicado_idx
    ON social_wiring.cs_virais (perfil_id, publicado_em DESC);
CREATE INDEX IF NOT EXISTS cs_virais_nicho_gin ON social_wiring.cs_virais USING GIN (nicho_ids);
CREATE INDEX IF NOT EXISTS cs_virais_profissao_gin ON social_wiring.cs_virais USING GIN (profissao_ids);
CREATE INDEX IF NOT EXISTS cs_virais_formato_gin ON social_wiring.cs_virais USING GIN (formato_ids);
CREATE INDEX IF NOT EXISTS cs_virais_slots_gin ON social_wiring.cs_virais USING GIN (blueprint_slots);
CREATE INDEX IF NOT EXISTS cs_virais_busca_gin ON social_wiring.cs_virais USING GIN (
    to_tsvector('portuguese', coalesce(gancho, '') || ' ' || coalesce(transcricao_texto, '')));
CREATE INDEX IF NOT EXISTS cs_virais_transcricao_idx
    ON social_wiring.cs_virais (transcricao_id) WHERE transcricao_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS social_wiring.cs_biblioteca_referencias (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id         UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    modo             TEXT NOT NULL CHECK (modo IN ('perfil', 'video')),
    perfil_id        UUID REFERENCES social_wiring.cs_perfis_monitorados (id) ON DELETE CASCADE,
    viral_id         UUID REFERENCES social_wiring.cs_virais (id) ON DELETE CASCADE,
    auto_atualizar   BOOLEAN NOT NULL DEFAULT true,
    posts_ate        DATE,
    created_by       UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_biblioteca_referencias_modo_alvo CHECK (
        (modo = 'perfil' AND perfil_id IS NOT NULL AND viral_id IS NULL)
        OR (modo = 'video' AND viral_id IS NOT NULL AND perfil_id IS NULL))
);
COMMENT ON TABLE social_wiring.cs_biblioteca_referencias IS
    'Migration 229 - Minha Biblioteca: the per-marca allow-list of monitored profiles (modo=perfil) or single virais (modo=video).';

CREATE UNIQUE INDEX IF NOT EXISTS cs_biblioteca_referencias_perfil_uq
    ON social_wiring.cs_biblioteca_referencias (marca_id, perfil_id) WHERE modo = 'perfil';
CREATE UNIQUE INDEX IF NOT EXISTS cs_biblioteca_referencias_video_uq
    ON social_wiring.cs_biblioteca_referencias (marca_id, viral_id) WHERE modo = 'video';

-- ----------------------------------------------------------------------------
-- 4. Headlines: lotes (one generation request) + headlines
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_headline_lotes (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id                  UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    created_by                UUID,
    origem                    TEXT NOT NULL
                              CHECK (origem IN ('form_me', 'form_public', 'form_viral', 'biblioteca', 'sugestao_auto')),
    parametros                JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                    TEXT NOT NULL DEFAULT 'criando'
                              CHECK (status IN ('criando', 'processando', 'completo', 'falha')),
    etapa                     TEXT,
    estruturas_total          INTEGER NOT NULL DEFAULT 0,
    estruturas_processadas    INTEGER NOT NULL DEFAULT 0,
    estruturas_com_erro       INTEGER NOT NULL DEFAULT 0,
    aviso_poucas_estruturas   BOOLEAN NOT NULL DEFAULT false,
    fallback_metodo           BOOLEAN NOT NULL DEFAULT false,
    erro                      TEXT,
    queue_job_id              UUID,
    modelo                    TEXT,
    prompt_versao             TEXT,
    started_at                TIMESTAMPTZ,
    finished_at               TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_headline_lotes IS
    'Migration 229 - one headline generation request. criando -> processando -> completo | falha; etapa + counters are the real progress. '
    'At most one active manual batch per user (partial unique index).';

CREATE INDEX IF NOT EXISTS cs_headline_lotes_marca_created_idx
    ON social_wiring.cs_headline_lotes (marca_id, created_at DESC);
CREATE INDEX IF NOT EXISTS cs_headline_lotes_user_created_idx
    ON social_wiring.cs_headline_lotes (created_by, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS cs_headline_lotes_um_ativo_por_usuario_uq
    ON social_wiring.cs_headline_lotes (created_by)
    WHERE status IN ('criando', 'processando') AND origem <> 'sugestao_auto';

CREATE TABLE IF NOT EXISTS social_wiring.cs_headlines (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id         UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    -- NULL = saved from the chat
    lote_id          UUID REFERENCES social_wiring.cs_headline_lotes (id) ON DELETE CASCADE,
    -- the structure used; NULL for a Metodo template or a chat headline
    viral_id         UUID REFERENCES social_wiring.cs_virais (id) ON DELETE SET NULL,
    template_metodo  INTEGER CHECK (template_metodo BETWEEN 1 AND 32),
    texto            TEXT NOT NULL CHECK (char_length(texto) BETWEEN 1 AND 1000 AND texto = btrim(texto)),
    texto_original   TEXT,
    angulo           INTEGER CHECK (angulo IN (1, 2)),
    itens_usados     JSONB NOT NULL DEFAULT '[]'::jsonb,
    favorita         BOOLEAN NOT NULL DEFAULT false,
    favoritada_em    TIMESTAMPTZ,
    modo             TEXT CHECK (modo IN ('manual', 'automatico')),
    created_by       UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_headlines IS
    'Migration 229 - generated or chat-saved headlines. itens_usados holds only literal matches the server verified.';

CREATE INDEX IF NOT EXISTS cs_headlines_marca_fav_idx
    ON social_wiring.cs_headlines (marca_id, favorita, favoritada_em DESC);
CREATE INDEX IF NOT EXISTS cs_headlines_marca_modo_idx
    ON social_wiring.cs_headlines (marca_id, modo, created_at DESC);
CREATE INDEX IF NOT EXISTS cs_headlines_lote_idx
    ON social_wiring.cs_headlines (lote_id) WHERE lote_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 5. Roteiros
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_roteiros (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id            UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    created_by          UUID,
    nome                TEXT NOT NULL CHECK (char_length(nome) BETWEEN 1 AND 160),
    headline_id         UUID REFERENCES social_wiring.cs_headlines (id) ON DELETE SET NULL,
    headline_texto      TEXT NOT NULL CHECK (char_length(headline_texto) BETWEEN 1 AND 1000),
    instrucoes          TEXT NOT NULL DEFAULT '' CHECK (char_length(instrucoes) <= 5000),
    fonte               TEXT NOT NULL DEFAULT 'ia' CHECK (fonte IN ('ia', 'web', 'link')),
    duracao             TEXT NOT NULL DEFAULT 'auto' CHECK (duracao IN ('auto', '1', '2', '3')),
    brain_id            UUID REFERENCES social_wiring.cs_brains (id) ON DELETE SET NULL,
    viral_id            UUID REFERENCES social_wiring.cs_virais (id) ON DELETE SET NULL,
    perguntas           JSONB NOT NULL DEFAULT '[]'::jsonb,
    status              TEXT NOT NULL DEFAULT 'criando'
                        CHECK (status IN ('criando', 'perguntas', 'processando', 'completo', 'falha')),
    etapa               TEXT,
    erro                TEXT,
    conteudo            TEXT NOT NULL DEFAULT '' CHECK (char_length(conteudo) <= 30000),
    conteudo_original   TEXT,
    versao              INTEGER NOT NULL DEFAULT 1,
    -- always NULL in v1; filled when web/link sources land
    fontes              TEXT,
    feedback            TEXT CHECK (feedback IN ('gostei', 'nao_gostei')),
    feedback_motivo     TEXT CHECK (char_length(feedback_motivo) <= 1000),
    queue_job_id        UUID,
    modelo              TEXT,
    prompt_versao       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ
);
COMMENT ON TABLE social_wiring.cs_roteiros IS
    'Migration 229 - roteiros. criando -> perguntas -> processando -> completo | falha; headline_texto is copied so it survives a deleted headline.';

CREATE INDEX IF NOT EXISTS cs_roteiros_marca_created_idx
    ON social_wiring.cs_roteiros (marca_id, created_at DESC);
CREATE INDEX IF NOT EXISTS cs_roteiros_headline_idx
    ON social_wiring.cs_roteiros (headline_id) WHERE headline_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 6. Chat and memory (private to their user)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_chat_conversas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id         UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    user_id          UUID NOT NULL,
    agente           TEXT NOT NULL CHECK (agente IN ('headline', 'roteiro')),
    titulo           TEXT NOT NULL CHECK (char_length(titulo) BETWEEN 1 AND 100),
    last_message_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_chat_conversas IS
    'Migration 229 - chat conversations, private to their user (RLS adds user_id = auth.uid()).';

CREATE INDEX IF NOT EXISTS cs_chat_conversas_lista_idx
    ON social_wiring.cs_chat_conversas (user_id, marca_id, agente, last_message_at DESC);

CREATE TABLE IF NOT EXISTS social_wiring.cs_chat_mensagens (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    conversa_id      UUID NOT NULL REFERENCES social_wiring.cs_chat_conversas (id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    conteudo         TEXT NOT NULL CHECK (char_length(conteudo) <= 100000),
    -- the resolved `@` references: [{tipo, id, rotulo}]
    referencias      JSONB NOT NULL DEFAULT '[]'::jsonb,
    status           TEXT NOT NULL DEFAULT 'completa' CHECK (status IN ('completa', 'parcial', 'erro')),
    truncada         BOOLEAN NOT NULL DEFAULT false,
    modelo           TEXT,
    contexto_chars   INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_chat_mensagens IS
    'Migration 229 - chat messages. Private to the conversation owner (RLS goes through cs_chat_conversas.user_id).';

CREATE INDEX IF NOT EXISTS cs_chat_mensagens_conversa_idx
    ON social_wiring.cs_chat_mensagens (conversa_id, created_at);

CREATE TABLE IF NOT EXISTS social_wiring.cs_memorias (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,
    marca_id    UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    texto       TEXT NOT NULL CHECK (char_length(texto) BETWEEN 1 AND 500 AND texto = btrim(texto)),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE social_wiring.cs_memorias IS
    'Migration 229 - chat memories (max 50 per user+marca, enforced by the service: 409). Private to their user.';

CREATE INDEX IF NOT EXISTS cs_memorias_user_marca_idx
    ON social_wiring.cs_memorias (user_id, marca_id, created_at);

-- ----------------------------------------------------------------------------
-- 7. Private bucket for library thumbnails (never public; signed URLs only)
-- ----------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('sw-biblioteca', 'sw-biblioteca', false)
ON CONFLICT (id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 8. Transcription lane for the library (contract 2.7 / 3.4)
-- ----------------------------------------------------------------------------
-- `user_id` stays NOT NULL: a library row carries the created_by of the monitored profile,
-- so the existing owner-SELECT RLS still holds. Library rows are excluded from every voice counter.
ALTER TABLE social_wiring.transcricoes
    ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'usuario';

DO $chk$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'transcricoes_origem_valida') THEN
    ALTER TABLE social_wiring.transcricoes
      ADD CONSTRAINT transcricoes_origem_valida CHECK (origem IN ('usuario', 'biblioteca'));
  END IF;
END
$chk$;

CREATE INDEX IF NOT EXISTS transcricoes_origem_status_idx
    ON social_wiring.transcricoes (origem, status);

-- reservar_transcricao: REDEFINED. Identical to 225 except that EVERY counter (per user, per org,
-- global minutes, global depth) adds `AND origem = 'usuario'`.
CREATE OR REPLACE FUNCTION social_wiring.reservar_transcricao(
    p_id            UUID,
    p_org           UUID,
    p_user          UUID,
    p_duracao_s     NUMERIC,
    p_bytes         BIGINT,
    p_formato       TEXT,
    p_contexto_tipo TEXT,
    p_contexto_ref  TEXT,
    p_storage_path  TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = social_wiring, public
AS $fn$
DECLARE
    v_agora      TIMESTAMPTZ := now();
    v_n          INTEGER;
    v_soma       NUMERIC;
    v_mais_antigo TIMESTAMPTZ;
    v_row        social_wiring.transcricoes%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:user:' || p_user::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:global', 0));

    -- per user: in flight
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE user_id = p_user AND origem = 'usuario' AND status IN ('na_fila', 'processando');
    IF v_n >= 2 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_usuario', 'http', 429, 'retry_after_s', 60);
    END IF;

    -- per user: submissions per hour
    SELECT count(*), min(criado_em) INTO v_n, v_mais_antigo FROM social_wiring.transcricoes
     WHERE user_id = p_user AND origem = 'usuario' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '1 hour';
    IF v_n >= 10 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'limite_usuario', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '1 hour' - v_agora)))::int));
    END IF;

    -- per user: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE user_id = p_user AND origem = 'usuario' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 1800 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_usuario', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    -- per org: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE org_id = p_org AND origem = 'usuario' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 7200 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_org', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    -- global: queue depth
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE origem = 'usuario' AND status IN ('na_fila', 'processando');
    IF v_n >= 20 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'fila_cheia', 'http', 503, 'retry_after_s', 120);
    END IF;

    -- global: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE origem = 'usuario' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 36000 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'capacidade_diaria', 'http', 503,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    INSERT INTO social_wiring.transcricoes
        (id, org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato, criado_em, origem)
    VALUES
        (p_id, p_org, p_user, p_contexto_tipo, p_contexto_ref, p_storage_path, p_bytes, p_duracao_s, p_formato, v_agora, 'usuario')
    RETURNING * INTO v_row;

    RETURN jsonb_build_object('ok', true, 'row', to_jsonb(v_row));
END
$fn$;

COMMENT ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT) IS
    'Migration 225, redefined by 229 - atomic quota gate + insert for a VOICE transcription (every counter sees only origem = usuario). Service role only.';

REVOKE EXECUTE ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.reservar_transcricao(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT, TEXT)
    TO service_role;

-- reservar_transcricao_biblioteca: the library lane's own budget (contract 3.4). Counters see only
-- origem = 'biblioteca': <= 60 min / 24 h platform-wide, <= 30 min / 24 h per org, <= 180 s per reel,
-- <= 5 library rows queued or processing. These mirror BIBLIOTECA_TRANSCRICAO_* in app/config.py (the
-- RPC is the enforcing copy; the service pre-checks with the config values for a friendly error).
-- Returns jsonb like reservar_transcricao.
CREATE OR REPLACE FUNCTION social_wiring.reservar_transcricao_biblioteca(
    p_id            UUID,
    p_org           UUID,
    p_user          UUID,
    p_duracao_s     NUMERIC,
    p_bytes         BIGINT,
    p_formato       TEXT,
    p_contexto_ref  TEXT,
    p_storage_path  TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = social_wiring, public
AS $fn$
DECLARE
    v_agora      TIMESTAMPTZ := now();
    v_n          INTEGER;
    v_soma       NUMERIC;
    v_mais_antigo TIMESTAMPTZ;
    v_row        social_wiring.transcricoes%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('transcricoes:biblioteca', 0));

    -- per reel
    IF p_duracao_s > 180 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'reel_longo', 'http', 422, 'retry_after_s', 0);
    END IF;

    -- library rows queued or processing
    SELECT count(*) INTO v_n FROM social_wiring.transcricoes
     WHERE origem = 'biblioteca' AND status IN ('na_fila', 'processando');
    IF v_n >= 5 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'fila_biblioteca_cheia', 'http', 503, 'retry_after_s', 120);
    END IF;

    -- per org: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE org_id = p_org AND origem = 'biblioteca' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 1800 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'cota_diaria_biblioteca_org', 'http', 429,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    -- platform-wide: rolling 24 h seconds
    SELECT COALESCE(sum(duracao_s), 0), min(criado_em) INTO v_soma, v_mais_antigo FROM social_wiring.transcricoes
     WHERE origem = 'biblioteca' AND NOT minutos_reembolsados AND criado_em > v_agora - interval '24 hours';
    IF v_soma + p_duracao_s > 3600 THEN
        RETURN jsonb_build_object('ok', false, 'codigo', 'capacidade_diaria_biblioteca', 'http', 503,
            'retry_after_s', GREATEST(60, ceil(extract(epoch FROM (v_mais_antigo + interval '24 hours' - v_agora)))::int));
    END IF;

    INSERT INTO social_wiring.transcricoes
        (id, org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato, criado_em, origem)
    VALUES
        (p_id, p_org, p_user, 'biblioteca_viral', p_contexto_ref, p_storage_path, p_bytes, p_duracao_s, p_formato, v_agora, 'biblioteca')
    RETURNING * INTO v_row;

    RETURN jsonb_build_object('ok', true, 'row', to_jsonb(v_row));
END
$fn$;

COMMENT ON FUNCTION social_wiring.reservar_transcricao_biblioteca(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT) IS
    'Migration 229 - the library lane quota gate + insert (origem = biblioteca; geracao-contract.md 3.4). Service role only.';

REVOKE EXECUTE ON FUNCTION social_wiring.reservar_transcricao_biblioteca(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.reservar_transcricao_biblioteca(UUID, UUID, UUID, NUMERIC, BIGINT, TEXT, TEXT, TEXT)
    TO service_role;

-- ----------------------------------------------------------------------------
-- 9. updated_at triggers
-- ----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS set_updated_at_cs_perfis_monitorados ON social_wiring.cs_perfis_monitorados;
CREATE TRIGGER set_updated_at_cs_perfis_monitorados
    BEFORE UPDATE ON social_wiring.cs_perfis_monitorados
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_virais ON social_wiring.cs_virais;
CREATE TRIGGER set_updated_at_cs_virais
    BEFORE UPDATE ON social_wiring.cs_virais
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_biblioteca_referencias ON social_wiring.cs_biblioteca_referencias;
CREATE TRIGGER set_updated_at_cs_biblioteca_referencias
    BEFORE UPDATE ON social_wiring.cs_biblioteca_referencias
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_headline_lotes ON social_wiring.cs_headline_lotes;
CREATE TRIGGER set_updated_at_cs_headline_lotes
    BEFORE UPDATE ON social_wiring.cs_headline_lotes
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_headlines ON social_wiring.cs_headlines;
CREATE TRIGGER set_updated_at_cs_headlines
    BEFORE UPDATE ON social_wiring.cs_headlines
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_roteiros ON social_wiring.cs_roteiros;
CREATE TRIGGER set_updated_at_cs_roteiros
    BEFORE UPDATE ON social_wiring.cs_roteiros
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_chat_conversas ON social_wiring.cs_chat_conversas;
CREATE TRIGGER set_updated_at_cs_chat_conversas
    BEFORE UPDATE ON social_wiring.cs_chat_conversas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_treinamentos ON social_wiring.cs_treinamentos;
CREATE TRIGGER set_updated_at_cs_treinamentos
    BEFORE UPDATE ON social_wiring.cs_treinamentos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

-- ----------------------------------------------------------------------------
-- 10. RLS (same shape as 217/224: own-org authenticated, service_role ALL)
-- ----------------------------------------------------------------------------
-- Static / platform-wide tables: authenticated SELECT true, service_role ALL.
ALTER TABLE social_wiring.cs_nichos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_nichos_select" ON social_wiring.cs_nichos;
CREATE POLICY "cs_nichos_select"
    ON social_wiring.cs_nichos
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_nichos_service_role" ON social_wiring.cs_nichos;
CREATE POLICY "cs_nichos_service_role"
    ON social_wiring.cs_nichos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_profissoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_profissoes_select" ON social_wiring.cs_profissoes;
CREATE POLICY "cs_profissoes_select"
    ON social_wiring.cs_profissoes
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_profissoes_service_role" ON social_wiring.cs_profissoes;
CREATE POLICY "cs_profissoes_service_role"
    ON social_wiring.cs_profissoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_formatos_video ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_formatos_video_select" ON social_wiring.cs_formatos_video;
CREATE POLICY "cs_formatos_video_select"
    ON social_wiring.cs_formatos_video
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_formatos_video_service_role" ON social_wiring.cs_formatos_video;
CREATE POLICY "cs_formatos_video_service_role"
    ON social_wiring.cs_formatos_video
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_treinamentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_treinamentos_select" ON social_wiring.cs_treinamentos;
CREATE POLICY "cs_treinamentos_select"
    ON social_wiring.cs_treinamentos
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_treinamentos_service_role" ON social_wiring.cs_treinamentos;
CREATE POLICY "cs_treinamentos_service_role"
    ON social_wiring.cs_treinamentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Org-scoped tables.
ALTER TABLE social_wiring.cs_perfis_monitorados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_perfis_monitorados_select_own_org" ON social_wiring.cs_perfis_monitorados;
CREATE POLICY "cs_perfis_monitorados_select_own_org"
    ON social_wiring.cs_perfis_monitorados
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_perfis_monitorados_write_own_org" ON social_wiring.cs_perfis_monitorados;
CREATE POLICY "cs_perfis_monitorados_write_own_org"
    ON social_wiring.cs_perfis_monitorados
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_perfis_monitorados_service_role" ON social_wiring.cs_perfis_monitorados;
CREATE POLICY "cs_perfis_monitorados_service_role"
    ON social_wiring.cs_perfis_monitorados
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_virais ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_virais_select_own_org" ON social_wiring.cs_virais;
CREATE POLICY "cs_virais_select_own_org"
    ON social_wiring.cs_virais
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_virais_write_own_org" ON social_wiring.cs_virais;
CREATE POLICY "cs_virais_write_own_org"
    ON social_wiring.cs_virais
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_virais_service_role" ON social_wiring.cs_virais;
CREATE POLICY "cs_virais_service_role"
    ON social_wiring.cs_virais
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_biblioteca_referencias ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_biblioteca_referencias_select_own_org" ON social_wiring.cs_biblioteca_referencias;
CREATE POLICY "cs_biblioteca_referencias_select_own_org"
    ON social_wiring.cs_biblioteca_referencias
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_biblioteca_referencias_write_own_org" ON social_wiring.cs_biblioteca_referencias;
CREATE POLICY "cs_biblioteca_referencias_write_own_org"
    ON social_wiring.cs_biblioteca_referencias
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_biblioteca_referencias_service_role" ON social_wiring.cs_biblioteca_referencias;
CREATE POLICY "cs_biblioteca_referencias_service_role"
    ON social_wiring.cs_biblioteca_referencias
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_headline_lotes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_headline_lotes_select_own_org" ON social_wiring.cs_headline_lotes;
CREATE POLICY "cs_headline_lotes_select_own_org"
    ON social_wiring.cs_headline_lotes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_headline_lotes_write_own_org" ON social_wiring.cs_headline_lotes;
CREATE POLICY "cs_headline_lotes_write_own_org"
    ON social_wiring.cs_headline_lotes
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_headline_lotes_service_role" ON social_wiring.cs_headline_lotes;
CREATE POLICY "cs_headline_lotes_service_role"
    ON social_wiring.cs_headline_lotes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_headlines ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_headlines_select_own_org" ON social_wiring.cs_headlines;
CREATE POLICY "cs_headlines_select_own_org"
    ON social_wiring.cs_headlines
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_headlines_write_own_org" ON social_wiring.cs_headlines;
CREATE POLICY "cs_headlines_write_own_org"
    ON social_wiring.cs_headlines
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_headlines_service_role" ON social_wiring.cs_headlines;
CREATE POLICY "cs_headlines_service_role"
    ON social_wiring.cs_headlines
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_roteiros ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_roteiros_select_own_org" ON social_wiring.cs_roteiros;
CREATE POLICY "cs_roteiros_select_own_org"
    ON social_wiring.cs_roteiros
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_roteiros_write_own_org" ON social_wiring.cs_roteiros;
CREATE POLICY "cs_roteiros_write_own_org"
    ON social_wiring.cs_roteiros
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_roteiros_service_role" ON social_wiring.cs_roteiros;
CREATE POLICY "cs_roteiros_service_role"
    ON social_wiring.cs_roteiros
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Private-to-user tables: own org AND own user.
ALTER TABLE social_wiring.cs_chat_conversas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_chat_conversas_own_user" ON social_wiring.cs_chat_conversas;
CREATE POLICY "cs_chat_conversas_own_user"
    ON social_wiring.cs_chat_conversas
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')) AND user_id = (SELECT auth.uid()))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')) AND user_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "cs_chat_conversas_service_role" ON social_wiring.cs_chat_conversas;
CREATE POLICY "cs_chat_conversas_service_role"
    ON social_wiring.cs_chat_conversas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_memorias ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_memorias_own_user" ON social_wiring.cs_memorias;
CREATE POLICY "cs_memorias_own_user"
    ON social_wiring.cs_memorias
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')) AND user_id = (SELECT auth.uid()))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')) AND user_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "cs_memorias_service_role" ON social_wiring.cs_memorias;
CREATE POLICY "cs_memorias_service_role"
    ON social_wiring.cs_memorias
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Messages carry no user_id: they are private through their conversation.
ALTER TABLE social_wiring.cs_chat_mensagens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_chat_mensagens_own_user" ON social_wiring.cs_chat_mensagens;
CREATE POLICY "cs_chat_mensagens_own_user"
    ON social_wiring.cs_chat_mensagens
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')) AND conversa_id IN (
        SELECT c.id FROM social_wiring.cs_chat_conversas c WHERE c.user_id = (SELECT auth.uid())))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')) AND conversa_id IN (
        SELECT c.id FROM social_wiring.cs_chat_conversas c WHERE c.user_id = (SELECT auth.uid())));

DROP POLICY IF EXISTS "cs_chat_mensagens_service_role" ON social_wiring.cs_chat_mensagens;
CREATE POLICY "cs_chat_mensagens_service_role"
    ON social_wiring.cs_chat_mensagens
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 11. Nav: the pages ship hidden behind status 'desenvolvimento'
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('media-creation-dashboard', 'desenvolvimento'),
    ('media-creation-chat', 'desenvolvimento'),
    ('media-creation-biblioteca', 'desenvolvimento'),
    ('media-creation-perfil', 'desenvolvimento'),
    ('media-creation-minha-biblioteca', 'desenvolvimento'),
    ('media-creation-treinamentos', 'desenvolvimento'),
    ('media-creation-headlines-gerar', 'desenvolvimento'),
    ('media-creation-headlines-favoritas', 'desenvolvimento'),
    ('media-creation-headlines-sugeridas', 'desenvolvimento'),
    ('media-creation-roteiros', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 12. Seed: nichos, profissoes, formatos de video, treinamentos (generated -- do not hand-edit)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.cs_nichos (id, nome, sort_order)
VALUES
    (1, 'Saúde e Bem-Estar', 1),
    (2, 'Relacionamentos', 2),
    (3, 'Finanças', 3),
    (4, 'Educação', 4),
    (5, 'Empreendedorismo/Business', 5),
    (6, 'Espiritualidade', 6),
    (7, 'Beleza & Estética', 7),
    (8, 'Moda & Estilo', 8),
    (9, 'Desenvolvimento Pessoal', 9),
    (13, 'Emagrecimento e Dieta', 10),
    (14, 'Saúde Mental', 11),
    (17, 'Tech & IA', 12),
    (18, 'Cripto', 13),
    (19, 'Marketing Digital', 14),
    (20, 'Direito', 15),
    (21, 'Comunicação & Liderança', 16),
    (22, 'Criação de Filhos', 17),
    (23, 'Vendas', 18),
    (24, 'Trends do Momento', 19),
    (25, 'Casa & Decoração', 20),
    (26, 'Imobiliário', 21),
    (27, 'Culinária', 22),
    (28, 'Emagrecimento', 23),
    (29, 'Imigração', 24),
    (30, 'Turismo & Viagem', 25),
    (31, 'Pets & Animais', 26),
    (32, 'Tributação Fiscal', 27),
    (33, 'Construção Civil', 28)
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, sort_order = EXCLUDED.sort_order;

INSERT INTO social_wiring.cs_profissoes (id, nome)
VALUES
    (25, 'Acupunturista'),
    (70, 'Advogado Administrativo'),
    (72, 'Advogado Ambiental'),
    (64, 'Advogado Civil'),
    (74, 'Advogado Constitucional'),
    (75, 'Advogado de Consumidor'),
    (67, 'Advogado de Família'),
    (76, 'Advogado Digital'),
    (68, 'Advogado Empresarial'),
    (71, 'Advogado Imobiliário'),
    (73, 'Advogado Internacional'),
    (65, 'Advogado Penal'),
    (77, 'Advogado Previdenciário'),
    (66, 'Advogado Trabalhista'),
    (69, 'Advogado Tributário'),
    (85, 'Agente de Turismo'),
    (20, 'Arquiteto(a)'),
    (102, 'Auditor Fiscal'),
    (3, 'Autor(a)'),
    (95, 'Breathwork'),
    (18, 'Cabeleireiro(a)'),
    (56, 'Chef de Cozinha'),
    (105, 'Cirurgião Plástico'),
    (27, 'Coach'),
    (57, 'Confeiteiro'),
    (54, 'Consultor de Imagem'),
    (49, 'Contador(a)'),
    (62, 'Copywriter'),
    (82, 'Corretor de Imóveis'),
    (90, 'Corretor de seguro de vida'),
    (21, 'Dentista'),
    (79, 'Designer de Interiores'),
    (100, 'Designer de joias'),
    (52, 'Designer de Sobrancelhas'),
    (60, 'Designer Gráfico'),
    (28, 'Economista'),
    (23, 'Empreendedor(a)'),
    (92, 'Enfermagem'),
    (80, 'Engenheiro'),
    (15, 'Esteticista'),
    (32, 'Estrategista de Marca'),
    (2, 'Farmacêutico(a)'),
    (14, 'Fisioterapeuta'),
    (47, 'Fisioterapeuta Pélvico'),
    (106, 'Fonoaudiólogo'),
    (55, 'Fotógrafo'),
    (61, 'Gestor de Tráfego/Media Buyer'),
    (22, 'Gestor(a)'),
    (83, 'Higienista Ocupacional'),
    (30, 'Influenciador(a)'),
    (31, 'Investidor(a)'),
    (99, 'Joalheira'),
    (84, 'Jornalista'),
    (78, 'Juiz'),
    (51, 'Líder Religioso'),
    (53, 'Maquiador(a)'),
    (26, 'Marketeiro(a)'),
    (98, 'Medicina Regenerativa'),
    (91, 'Medico Otorrinolaringologia'),
    (93, 'Medico Radiologia'),
    (50, 'Mentor(a)'),
    (24, 'Moda'),
    (97, 'Musculação'),
    (37, 'Médico Cardiologista'),
    (12, 'Médico Cirurgião'),
    (33, 'Médico Dermatologista'),
    (38, 'Médico Endocrinologista'),
    (101, 'Médico geral'),
    (89, 'Médico Geriatra'),
    (36, 'Médico Ginecologista'),
    (43, 'Médico Integrativo'),
    (39, 'Médico Neurologista'),
    (87, 'Médico Nutrólogo'),
    (104, 'Médico Obstetra'),
    (40, 'Médico Oftalmologista'),
    (34, 'Médico Ortopedista'),
    (35, 'Médico Pediatra'),
    (8, 'Médico Psiquiatra'),
    (103, 'Médico ultrassonografista'),
    (41, 'Médico Urologista'),
    (42, 'Médico Veterinário'),
    (4, 'Neurocientista'),
    (16, 'Nutricionista'),
    (81, 'Paisagista'),
    (5, 'Pastor(a)'),
    (48, 'Personal Trainer'),
    (94, 'Professor de Yoga'),
    (29, 'Professor(a)'),
    (63, 'Programador(a)'),
    (46, 'Psicanalista'),
    (45, 'Psicoterapeuta'),
    (44, 'Psicólogo Infantil'),
    (7, 'Psicólogo(a)'),
    (86, 'Quiropraxista'),
    (59, 'Social Media'),
    (58, 'Sommelier'),
    (9, 'Terapeuta'),
    (10, 'Terapeuta Holístico'),
    (96, 'Terapeuta Somatico'),
    (6, 'Teólogo(a)'),
    (13, 'Vendedor(a)'),
    (19, 'Visagista')
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome;

INSERT INTO social_wiring.cs_formatos_video (id, nome, definicao)
VALUES
    (1, 'Lista de Valor Prático', 'Dicas/passos/recomendações aplicáveis imediatamente.'),
    (2, 'Lista de Pontos de Identificação', 'Situações em que o público se reconhece.'),
    (3, 'Lista de Crenças', 'Valores ou princípios afirmados com clareza.'),
    (4, 'Mistério', 'Informação-chave retida até o final.'),
    (5, 'Comparação', 'Contrasta duas opções/ideias.'),
    (6, 'Tutorial', 'Passo a passo de COMO fazer.'),
    (7, 'Análise do Mundo e Novas Tendências', 'Mudanças sociais/leis/mercado e impactos.'),
    (8, 'Histórias Pessoais', 'Relato em 1ª pessoa com vulnerabilidade.'),
    (9, 'Histórias de Terceiros', 'Caso de cliente/paciente/figura pública.'),
    (10, 'Fatos Curiosos', 'Dados/estatísticas surpreendentes.'),
    (11, 'Metáforas e Analogias', 'Explica por comparação familiar.'),
    (12, 'Assunto do Momento', 'Trending (notícia, meme, evento).'),
    (13, 'Defesa de Crença Forte', 'Opinião polarizadora, linguagem absoluta.'),
    (14, 'Palavras de Motivação', 'Encorajamento curto.'),
    (15, 'Websérie', 'Conteúdo seriado.')
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, definicao = EXCLUDED.definicao;

-- video_url / ativo are deliberately NOT updated: a platform admin owns them.
INSERT INTO social_wiring.cs_treinamentos (ordem, titulo, descricao)
VALUES
    (1, 'Como preencher a Bio', 'Como preencher sua Bio do jeito certo para a IA entender seu contexto.'),
    (2, 'Como aprovar itens da Pesquisa (automático e manual)', 'Aprenda a aprovar itens gerados na Pesquisa, tanto no modo automático quanto no manual.'),
    (3, 'Como gerar roteiros Headlines Favoritas', 'Gere roteiros a partir das suas Headlines Favoritas com poucos cliques.'),
    (4, 'Como gerar roteiros Headlines Biblioteca de Virais', 'Use a Biblioteca de Virais para gerar roteiros prontos para produção.'),
    (5, 'Como gerar roteiros com Headlines Próprias', 'Crie seus próprios ganchos/headlines e gere roteiros a partir deles.')
ON CONFLICT (ordem) DO UPDATE SET titulo = EXCLUDED.titulo, descricao = EXCLUDED.descricao;
