-- ============================================================================
-- Migration 224 · social_wiring: Segundo Cérebro (CoreStudio rebuild) —
-- `cs_brain_templates` + `cs_brain_questions` (static seed), `cs_brains`,
-- `cs_brain_answers`, `cs_brain_imports`, `cs_extractions`,
-- `cs_extraction_targets`, `cs_marca_perfil`, `cs_brain_append()`, the private
-- `social-wiring-cerebro` bucket and the `media-creation-cerebro` nav row
-- ============================================================================
-- WHY
-- ---
-- Per-marca "brains": 4 Sistema brains (questionnaire -> AI synthesis) + custom
-- markdown brains, a profile bio per marca, and pasted-text extractions.
-- Contract: projects/core-studio/specs/cerebro-contract.md section 2, with the
-- tech-lead amendments of section 10 (transcription goes through the shared
-- `social_wiring.transcricoes` product layer, NOT a module-local table).
--
-- The 4 templates + 35 questions are GENERATED from the Python source of truth
-- (app/modules/media_creation/cerebro_templates.py :: seed_sql()); a test asserts
-- this file carries exactly that text.
--
-- `cs_brain_append` is the ONLY write path for imports/extractions: one
-- statement appends a block and bumps `content_version`, so a concurrent editor
-- save can never lose an appended block (it gets a version conflict instead).
--
-- NOC-REMEDIATE[fk-transcricoes]: `transcricao_id` on cs_brain_answers /
-- cs_brain_imports / cs_extractions is a plain nullable uuid for now --
-- `social_wiring.transcricoes` does not exist yet. The shared transcription
-- product slice (transcription-contract.md S3) owns adding the FK
-- (`REFERENCES social_wiring.transcricoes (id) ON DELETE SET NULL`). -- 2026-10-09
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'Migration 224 requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regclass('social_wiring.cs_research_items') IS NULL THEN
    RAISE EXCEPTION 'Migration 224 requires social_wiring.cs_research_items (migration 217) -- apply 217 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. Static templates + questions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_brain_templates (
    slug        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_order  INTEGER NOT NULL
);

COMMENT ON TABLE social_wiring.cs_brain_templates IS
    'Migration 224 - Segundo Cerebro Sistema brain templates (4 rows). Seeded from cerebro_templates.py; '
    'read-only for authenticated users.';

CREATE TABLE IF NOT EXISTS social_wiring.cs_brain_questions (
    id            TEXT PRIMARY KEY,
    template_slug TEXT NOT NULL REFERENCES social_wiring.cs_brain_templates (slug) ON DELETE CASCADE,
    position      INTEGER NOT NULL CHECK (position >= 1),
    text          TEXT NOT NULL,
    hint          TEXT,
    optional      BOOLEAN NOT NULL DEFAULT false
);

COMMENT ON TABLE social_wiring.cs_brain_questions IS
    'Migration 224 - questionnaire per template; id = <template_slug>.<NN>; group = (position-1)/3. '
    'Seeded from cerebro_templates.py.';

CREATE INDEX IF NOT EXISTS cs_brain_questions_template_idx
    ON social_wiring.cs_brain_questions (template_slug, position);

-- ----------------------------------------------------------------------------
-- 2. Brains
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_brains (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id              UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    kind                  TEXT NOT NULL CHECK (kind IN ('sistema', 'custom')),
    template_slug         TEXT REFERENCES social_wiring.cs_brain_templates (slug),
    name                  TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80 AND name = btrim(name)),
    content               TEXT NOT NULL DEFAULT '' CHECK (char_length(content) <= 200000),
    content_version       INTEGER NOT NULL DEFAULT 0,
    synthesis_status      TEXT NOT NULL DEFAULT 'idle' CHECK (synthesis_status IN ('idle', 'processing', 'error')),
    synthesis_error       TEXT,
    synthesis_started_at  TIMESTAMPTZ,
    synthesized_at        TIMESTAMPTZ,
    created_by            UUID,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((kind = 'sistema') = (template_slug IS NOT NULL))
);

COMMENT ON TABLE social_wiring.cs_brains IS
    'Migration 224 - Segundo Cerebro brains, per marca. sistema => template_slug set (cannot be renamed/deleted); '
    'custom => free markdown. content_version is bumped on every content write (optimistic concurrency); '
    'imports/extractions append through cs_brain_append().';

CREATE UNIQUE INDEX IF NOT EXISTS cs_brains_marca_sistema_uq
    ON social_wiring.cs_brains (marca_id, template_slug)
    WHERE kind = 'sistema';

CREATE UNIQUE INDEX IF NOT EXISTS cs_brains_marca_name_uq
    ON social_wiring.cs_brains (marca_id, lower(name));

CREATE INDEX IF NOT EXISTS cs_brains_marca_created_idx
    ON social_wiring.cs_brains (marca_id, created_at);

-- ----------------------------------------------------------------------------
-- 3. Answers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_brain_answers (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    brain_id             UUID NOT NULL REFERENCES social_wiring.cs_brains (id) ON DELETE CASCADE,
    question_id          TEXT NOT NULL REFERENCES social_wiring.cs_brain_questions (id),
    text                 TEXT NOT NULL DEFAULT '' CHECK (char_length(text) <= 10000),
    -- NOC-REMEDIATE[fk-transcricoes]: plain uuid until social_wiring.transcricoes exists; the
    -- transcription product slice adds the FK (ON DELETE SET NULL). -- 2026-10-09
    transcricao_id       UUID,
    review_status        TEXT NOT NULL DEFAULT 'none' CHECK (review_status IN ('none', 'pending', 'done', 'error')),
    review_verdict       TEXT CHECK (review_verdict IN ('approved', 'rejected')),
    review_reason        TEXT,
    review_improved      TEXT,
    review_decision      TEXT CHECK (review_decision IN ('accepted', 'dismissed')),
    review_error         TEXT,
    reviewed_text_sha    TEXT,
    review_requested_at  TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_brain_answers IS
    'Migration 224 - one answer per (brain, question). Any later text change resets review_* to none '
    '(the service compares sha256(text) with reviewed_text_sha). The non-blocking AI review writes verdict/reason/improved; '
    'the user accepts or dismisses (review_decision).';

CREATE UNIQUE INDEX IF NOT EXISTS cs_brain_answers_brain_question_uq
    ON social_wiring.cs_brain_answers (brain_id, question_id);

-- ----------------------------------------------------------------------------
-- 4. Imports (editor appends)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_brain_imports (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    brain_id       UUID NOT NULL REFERENCES social_wiring.cs_brains (id) ON DELETE CASCADE,
    kind           TEXT NOT NULL CHECK (kind IN ('file', 'youtube')),
    filename       TEXT,
    storage_path   TEXT,
    size_bytes     BIGINT,
    source_url     TEXT,
    -- NOC-REMEDIATE[fk-transcricoes]: see cs_brain_answers.transcricao_id. -- 2026-10-09
    transcricao_id UUID,
    status         TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'appended', 'error')),
    chars_appended INTEGER,
    error_message  TEXT,
    created_by     UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_brain_imports IS
    'Migration 224 - file / youtube imports appended to a brain (file in v1, youtube is phase 2). '
    'processing -> appended | error; stale processing is swept to error.';

CREATE INDEX IF NOT EXISTS cs_brain_imports_brain_created_idx
    ON social_wiring.cs_brain_imports (brain_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 5. Extractions (Minhas extracoes) + targets
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_extractions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    marca_id       UUID NOT NULL REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    name           TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    source_kind    TEXT NOT NULL CHECK (source_kind IN ('url', 'text')),
    source_url     TEXT,
    transcript     TEXT CHECK (char_length(transcript) <= 200000),
    -- NOC-REMEDIATE[fk-transcricoes]: see cs_brain_answers.transcricao_id. -- 2026-10-09
    transcricao_id UUID,
    status         TEXT NOT NULL CHECK (status IN ('transcribing', 'ready', 'applied', 'error')),
    error_message  TEXT,
    created_by     UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_extractions IS
    'Migration 224 - Minhas extracoes: pasted text (v1) or URL (phase 2) applied to N brains of one marca. '
    'Distinct from the Pesquisa cs_extraction_jobs (migration 221).';

CREATE INDEX IF NOT EXISTS cs_extractions_marca_created_idx
    ON social_wiring.cs_extractions (marca_id, created_at DESC);

CREATE TABLE IF NOT EXISTS social_wiring.cs_extraction_targets (
    extraction_id UUID NOT NULL REFERENCES social_wiring.cs_extractions (id) ON DELETE CASCADE,
    brain_id      UUID NOT NULL REFERENCES social_wiring.cs_brains (id) ON DELETE CASCADE,
    org_id        UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    applied_at    TIMESTAMPTZ,
    PRIMARY KEY (extraction_id, brain_id)
);

COMMENT ON TABLE social_wiring.cs_extraction_targets IS
    'Migration 224 - which brains an extraction feeds; applied_at makes the apply idempotent per target. '
    'org_id is carried (contract section 2 omits it) so RLS is the uniform own-org shape.';

-- ----------------------------------------------------------------------------
-- 6. Profile bio (headline "Nucleo de Influencia" source)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cs_marca_perfil (
    marca_id   UUID PRIMARY KEY REFERENCES social_wiring.marcas (id) ON DELETE CASCADE,
    org_id     UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    bio        TEXT NOT NULL DEFAULT '' CHECK (char_length(bio) <= 5000),
    updated_by UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.cs_marca_perfil IS
    'Migration 224 - profile bio per marca (the headline Nucleo de Influencia source), separate from the brain of that name.';

-- ----------------------------------------------------------------------------
-- 7. updated_at triggers
-- ----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS set_updated_at_cs_brains ON social_wiring.cs_brains;
CREATE TRIGGER set_updated_at_cs_brains
    BEFORE UPDATE ON social_wiring.cs_brains
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_brain_answers ON social_wiring.cs_brain_answers;
CREATE TRIGGER set_updated_at_cs_brain_answers
    BEFORE UPDATE ON social_wiring.cs_brain_answers
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_brain_imports ON social_wiring.cs_brain_imports;
CREATE TRIGGER set_updated_at_cs_brain_imports
    BEFORE UPDATE ON social_wiring.cs_brain_imports
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_extractions ON social_wiring.cs_extractions;
CREATE TRIGGER set_updated_at_cs_extractions
    BEFORE UPDATE ON social_wiring.cs_extractions
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

DROP TRIGGER IF EXISTS set_updated_at_cs_marca_perfil ON social_wiring.cs_marca_perfil;
CREATE TRIGGER set_updated_at_cs_marca_perfil
    BEFORE UPDATE ON social_wiring.cs_marca_perfil
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_media_creation();

-- ----------------------------------------------------------------------------
-- 8. cs_brain_append: the ONLY write path for imports / extractions
-- ----------------------------------------------------------------------------
-- One UPDATE statement: appends p_block (separated by a rule when the brain already
-- has content), bumps content_version, returns the new version. Over 200 000 chars the
-- table CHECK raises check_violation -- nothing is truncated. SECURITY INVOKER (RLS applies).
CREATE OR REPLACE FUNCTION social_wiring.cs_brain_append(p_brain uuid, p_org uuid, p_block text)
RETURNS integer
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = social_wiring, public
AS $fn$
DECLARE
  v_version integer;
BEGIN
  UPDATE social_wiring.cs_brains
     SET content = CASE WHEN btrim(content) = '' THEN p_block
                        ELSE content || E'\n\n---\n\n' || p_block END,
         content_version = content_version + 1
   WHERE id = p_brain AND org_id = p_org
   RETURNING content_version INTO v_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'cs_brain_append: brain % not found for org %', p_brain, p_org
      USING ERRCODE = 'no_data_found';
  END IF;
  RETURN v_version;
END;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_brain_append(uuid, uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_brain_append(uuid, uuid, text) TO service_role;

-- ----------------------------------------------------------------------------
-- 9. RLS (same shape as 217: own-org authenticated, service_role ALL)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_brain_templates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_brain_templates_select" ON social_wiring.cs_brain_templates;
CREATE POLICY "cs_brain_templates_select"
    ON social_wiring.cs_brain_templates
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_brain_templates_service_role" ON social_wiring.cs_brain_templates;
CREATE POLICY "cs_brain_templates_service_role"
    ON social_wiring.cs_brain_templates
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_brain_questions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_brain_questions_select" ON social_wiring.cs_brain_questions;
CREATE POLICY "cs_brain_questions_select"
    ON social_wiring.cs_brain_questions
    FOR SELECT TO authenticated
    USING (true);

DROP POLICY IF EXISTS "cs_brain_questions_service_role" ON social_wiring.cs_brain_questions;
CREATE POLICY "cs_brain_questions_service_role"
    ON social_wiring.cs_brain_questions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_brains ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_brains_select_own_org" ON social_wiring.cs_brains;
CREATE POLICY "cs_brains_select_own_org"
    ON social_wiring.cs_brains
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_brains_write_own_org" ON social_wiring.cs_brains;
CREATE POLICY "cs_brains_write_own_org"
    ON social_wiring.cs_brains
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_brains_service_role" ON social_wiring.cs_brains;
CREATE POLICY "cs_brains_service_role"
    ON social_wiring.cs_brains
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_brain_answers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_brain_answers_select_own_org" ON social_wiring.cs_brain_answers;
CREATE POLICY "cs_brain_answers_select_own_org"
    ON social_wiring.cs_brain_answers
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_brain_answers_write_own_org" ON social_wiring.cs_brain_answers;
CREATE POLICY "cs_brain_answers_write_own_org"
    ON social_wiring.cs_brain_answers
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_brain_answers_service_role" ON social_wiring.cs_brain_answers;
CREATE POLICY "cs_brain_answers_service_role"
    ON social_wiring.cs_brain_answers
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_brain_imports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_brain_imports_select_own_org" ON social_wiring.cs_brain_imports;
CREATE POLICY "cs_brain_imports_select_own_org"
    ON social_wiring.cs_brain_imports
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_brain_imports_write_own_org" ON social_wiring.cs_brain_imports;
CREATE POLICY "cs_brain_imports_write_own_org"
    ON social_wiring.cs_brain_imports
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_brain_imports_service_role" ON social_wiring.cs_brain_imports;
CREATE POLICY "cs_brain_imports_service_role"
    ON social_wiring.cs_brain_imports
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_extractions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_extractions_select_own_org" ON social_wiring.cs_extractions;
CREATE POLICY "cs_extractions_select_own_org"
    ON social_wiring.cs_extractions
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extractions_write_own_org" ON social_wiring.cs_extractions;
CREATE POLICY "cs_extractions_write_own_org"
    ON social_wiring.cs_extractions
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extractions_service_role" ON social_wiring.cs_extractions;
CREATE POLICY "cs_extractions_service_role"
    ON social_wiring.cs_extractions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_extraction_targets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_extraction_targets_select_own_org" ON social_wiring.cs_extraction_targets;
CREATE POLICY "cs_extraction_targets_select_own_org"
    ON social_wiring.cs_extraction_targets
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extraction_targets_write_own_org" ON social_wiring.cs_extraction_targets;
CREATE POLICY "cs_extraction_targets_write_own_org"
    ON social_wiring.cs_extraction_targets
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_extraction_targets_service_role" ON social_wiring.cs_extraction_targets;
CREATE POLICY "cs_extraction_targets_service_role"
    ON social_wiring.cs_extraction_targets
    FOR ALL TO service_role USING (true) WITH CHECK (true);

ALTER TABLE social_wiring.cs_marca_perfil ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cs_marca_perfil_select_own_org" ON social_wiring.cs_marca_perfil;
CREATE POLICY "cs_marca_perfil_select_own_org"
    ON social_wiring.cs_marca_perfil
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_marca_perfil_write_own_org" ON social_wiring.cs_marca_perfil;
CREATE POLICY "cs_marca_perfil_write_own_org"
    ON social_wiring.cs_marca_perfil
    FOR ALL TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')))
    WITH CHECK (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "cs_marca_perfil_service_role" ON social_wiring.cs_marca_perfil;
CREATE POLICY "cs_marca_perfil_service_role"
    ON social_wiring.cs_marca_perfil
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 10. Private bucket for uploaded files ONLY (voice audio lives in the transcription bucket).
-- Backend-only: NO authenticated storage policy; the UI gets short-TTL signed URLs.
-- Paths: {org}/{marca}/{brain}/files/{uuid}-{filename}
-- ----------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('social-wiring-cerebro', 'social-wiring-cerebro', false)
ON CONFLICT (id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 11. Nav: the page ships hidden behind status 'desenvolvimento'
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('media-creation-cerebro', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 12. Seed: 4 templates + 35 questions (generated -- do not hand-edit)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.cs_brain_templates (slug, name, description, sort_order)
VALUES
    ('historia-de-criacao', 'História de Criação', 'Como você chegou até aqui: de onde veio, o que te moveu e o que quer deixar.', 1),
    ('historias-de-vida', 'Histórias de Vida do Especialista', 'As histórias reais que forjaram o especialista e que sustentam o conteúdo.', 2),
    ('metodo-do-especialista', 'Método do Especialista', 'O passo a passo, os pilares e o nome do método que o especialista ensina.', 3),
    ('nucleo-de-influencia', 'Núcleo de Influência', 'Quem você é, quem você ajuda, a dor, o inimigo e a transformação: a base de toda a sua comunicação.', 4)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, description = EXCLUDED.description,
    sort_order = EXCLUDED.sort_order;

INSERT INTO social_wiring.cs_brain_questions
    (id, template_slug, position, text, hint, optional)
VALUES
    ('historia-de-criacao.01', 'historia-de-criacao', 1, 'Como era sua vida antes de trabalhar com o que você trabalha hoje?', NULL, false),
    ('historia-de-criacao.02', 'historia-de-criacao', 2, 'O que te motivou a iniciar nessa área?', NULL, false),
    ('historia-de-criacao.03', 'historia-de-criacao', 3, 'Qual ou quais foram os maiores desafios que você enfrentou nesse caminho?', NULL, false),
    ('historia-de-criacao.04', 'historia-de-criacao', 4, 'Teve um momento em que você pensou em desistir? O que te fez continuar?', NULL, false),
    ('historia-de-criacao.05', 'historia-de-criacao', 5, 'Qual foi o ponto de virada que fez tudo mudar?', NULL, false),
    ('historia-de-criacao.06', 'historia-de-criacao', 6, 'Quem você se tornou hoje?', NULL, false),
    ('historia-de-criacao.07', 'historia-de-criacao', 7, 'O que você aprendeu com tudo isso e quer passar para outras pessoas? Qual é sua missão nessa área?', NULL, false),
    ('historia-de-criacao.08', 'historia-de-criacao', 8, 'O que te motiva a continuar todos os dias?', NULL, false),
    ('historia-de-criacao.09', 'historia-de-criacao', 9, 'Qual legado você quer deixar por meio do seu trabalho?', NULL, false),
    ('historias-de-vida.01', 'historias-de-vida', 1, 'Agora precisamos das histórias que te forjaram na sua jornada.', NULL, false),
    ('historias-de-vida.02', 'historias-de-vida', 2, 'Agora, conte histórias de grandes descobertas ou ensinamentos que você teve ao longo da sua jornada.', NULL, false),
    ('historias-de-vida.03', 'historias-de-vida', 3, 'Conte histórias de pessoas que você ajudou.', NULL, false),
    ('historias-de-vida.04', 'historias-de-vida', 4, 'Agora para finalizar, conte histórias de grandes conquistas que você teve na vida.', NULL, false),
    ('metodo-do-especialista.01', 'metodo-do-especialista', 1, 'Qual é o passo a passo que você ensina para a pessoa sair do ponto A até o resultado?', NULL, false),
    ('metodo-do-especialista.02', 'metodo-do-especialista', 2, 'Quais são os 3 a 5 pilares que toda pessoa precisa entender ou aplicar pra ter resultado com o que você ensina?', NULL, false),
    ('metodo-do-especialista.03', 'metodo-do-especialista', 3, 'Se alguém seguisse só o essencial do que você faz, o que não poderia faltar?', NULL, false),
    ('metodo-do-especialista.04', 'metodo-do-especialista', 4, 'Existe uma ordem certa ou fases que a pessoa precisa seguir? Quais são elas?', NULL, false),
    ('metodo-do-especialista.05', 'metodo-do-especialista', 5, 'Você tem nomes para cada etapa ou princípio do seu método? Quer criar?', NULL, false),
    ('metodo-do-especialista.06', 'metodo-do-especialista', 6, 'Se você pudesse resumir seu método em uma frase ou nome forte, como ele se chamaria?', NULL, false),
    ('metodo-do-especialista.07', 'metodo-do-especialista', 7, 'Tem alguma parte do processo que as pessoas costumam pular e depois se arrependem? Qual é?', NULL, false),
    ('nucleo-de-influencia.01', 'nucleo-de-influencia', 1, 'Qual é o seu nome, e o que você faz?', 'Ex: Meu nome é Elias Maman, Especialista em Atenção Digital', false),
    ('nucleo-de-influencia.02', 'nucleo-de-influencia', 2, 'Você se autointitula por algum nome/termo?', 'Ex: O Rei da Creatina; O Barbeiro dos Milionários; O Dentista do SUS', true),
    ('nucleo-de-influencia.03', 'nucleo-de-influencia', 3, 'Quem você ajuda?', 'Descreva claramente o tipo de pessoa que você ajuda. Pode ser por profissão, dor, momento de vida ou contexto.', false),
    ('nucleo-de-influencia.04', 'nucleo-de-influencia', 4, 'Você costuma chamar sua audiência por um nome específico?', 'Ex: Os Remanescentes; Homens da Verdade, etc', true),
    ('nucleo-de-influencia.05', 'nucleo-de-influencia', 5, 'Qual é a principal dor que você resolve?', 'O que mais machuca, trava ou impede essa pessoa de avançar?', false),
    ('nucleo-de-influencia.06', 'nucleo-de-influencia', 6, 'Qual é o inimigo e principal motivo causador dessa dor?', 'O que está por trás disso tudo? Uma crença? Uma prática comum? Uma negligência?', false),
    ('nucleo-de-influencia.07', 'nucleo-de-influencia', 7, 'Você costuma dar um nome para esse inimigo?', 'Ex: Geração Dopamina; Mundo de 3 Segundos; Satanás; etc', true),
    ('nucleo-de-influencia.08', 'nucleo-de-influencia', 8, 'O que sua audiência está tentando fazer para resolver isso, mas que não está funcionando?', 'Quais tentativas frustradas seu público já fez?', false),
    ('nucleo-de-influencia.09', 'nucleo-de-influencia', 9, 'Qual crença errada ou visão limitada você gostaria que as pessoas mudassem?', 'O que seu público acredita hoje que está atrapalhando mais do que ajudando?', false),
    ('nucleo-de-influencia.10', 'nucleo-de-influencia', 10, 'Qual problema filosófico existe por trás desse cenário?', 'O que te indigna no mundo em relação a esse problema? O que não deveria ser como é?', false),
    ('nucleo-de-influencia.11', 'nucleo-de-influencia', 11, 'Qual é o segredo, atalho ou nova abordagem que resolve essa dor — e que você ensina?', 'Aquela grande virada que poucas pessoas conhecem, mas faz toda a diferença.', false),
    ('nucleo-de-influencia.12', 'nucleo-de-influencia', 12, 'Qual é a grande transformação que você acredita que seu trabalho gera?', 'O que muda na vida da pessoa que realmente aplica o que você ensina?', false),
    ('nucleo-de-influencia.13', 'nucleo-de-influencia', 13, 'Você já criou algum método? Se sim, tem algum nome específico?', 'Ex: Erupção de Seguidores; etc', true),
    ('nucleo-de-influencia.14', 'nucleo-de-influencia', 14, 'Quais argumentos fortes você pode usar para defender essa transformação?', 'Dados, metáforas, analogias, raciocínios lógicos, comparações, etc.', false),
    ('nucleo-de-influencia.15', 'nucleo-de-influencia', 15, 'Você conhece histórias reais de pessoas que saíram do ponto A para o ponto B com sua ajuda?', 'Conte brevemente essas histórias: de onde elas saíram e onde chegaram.', true)
ON CONFLICT (id) DO UPDATE SET
    template_slug = EXCLUDED.template_slug, position = EXCLUDED.position,
    text = EXCLUDED.text, hint = EXCLUDED.hint, optional = EXCLUDED.optional;
