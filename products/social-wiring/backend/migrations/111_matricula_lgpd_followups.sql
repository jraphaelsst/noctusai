-- ============================================================================
-- Migration 111 · social_wiring: F2 security-review follow-ups — logging the
-- reads 109 missed, giving the matrícula surface a retention clock, and
-- closing the write-once gap 092's policy left open
--
-- CONTEXT: this is the "ship with follow-ups" half of the F2 (matrícula
-- estruturada, migration 109) security review. Five gaps, one migration.
--
-- 1. TEXT READS WERE NEVER LOGGED
-- --------------------------------
-- Migration 109 logs a `view`/`download`/`delete` of the PDF itself
-- (`imovel_documento_acessos`), but three routes hand back the CPF-bearing
-- TEXT — `GET /extracoes/{id}` (`texto_extraido`), `GET /extracoes/{id}/atos`
-- and `GET /contratos/{id}/atos` (both literal slices of it) — with no log
-- row at all. `acao` gains `'text_view'`.
--
-- 🔴 `documento_id` BECOMES OPTIONAL, `extracao_id` IS NEW. Not every
-- extraction that exposes text has a kept PDF to log against: the 092
-- "unlinked upload" shape (no `codigo`, no `imovel_documento_id`) is still
-- reachable through these three routes, and its text is exactly as
-- CPF-bearing as a linked one's. So the log row is keyed to EITHER a
-- document OR an extraction, never both and never neither — the
-- `imovel_documento_acessos_um_alvo` CHECK is what makes "log an access with
-- no subject" impossible to write rather than a convention to remember.
--
-- 2. THE MATRÍCULA SURFACE HAD NO RETENTION CLOCK — AND NOW THE REASON IS GONE
-- ------------------------------------------------------------------------------
-- Migration 079's header (`documento_retencao_politicas`) says: "`imovel_documentos`
-- is absent from `superficie` on purpose. 075 gave it no `retencao_ate` column
-- and no access log, because a matrícula is a public registry document about a
-- PROPERTY. [...] when that surface earns a clock, it earns a CHECK value here
-- in the same change." That reasoning is STALE as of 109: this file's own
-- point (1) is the access log 079 was waiting on. USER DECISION (2026-09): the
-- surface earns its clock now, in the same shape as the others —
-- `superficie = 'imovel'`, resolved by the existing two-tier
-- `app/services/documento_retencao.py`, anchored at `envio` (there is no
-- deal-level `closed_at` a standalone matrícula upload can anchor to; a
-- property can outlive many atendimentos). Two kept surfaces earn a policy
-- row: the PDF itself (`imovel_documentos`, tipos `matricula` / `guia_iptu`)
-- and the raw transcription (`matricula_extracoes.texto_extraido`, tipo
-- `texto_extraido` — a different table, same LGPD posture, so it rides under
-- the same `superficie` rather than inventing a second one).
--
-- 3. THE WRITE-ONCE GUARANTEE WAS A COMMENT, NOT A CONSTRAINT
-- --------------------------------------------------------------
-- Migration 092 grants `authenticated FOR ALL` on `matricula_extracoes` — the
-- request-path policy that lets an upload/list/delete work through the
-- caller's own token (092's header). Combined with 109's RESTRICT foreign
-- keys and offset arithmetic ("An extraction's text is written exactly once
-- [...] the offsets stay valid for the life of the row"), that ALL grant is
-- also a same-org caller's ability to PATCH `texto_extraido` / `codigo` /
-- `imovel_documento_id` straight through PostgREST — silently invalidating
-- every `matricula_atos` offset and every citation that quotes them. The
-- background pipeline (`app/modules/matriculas/service.py`) writes through
-- `get_background_client()` (service-role, bypasses RLS) and only ever sets
-- these three columns on an INSERT or on the ONE UPDATE that moves a row to
-- `concluida` — never afterwards, and never a re-link. A trigger enforces
-- that in the database, for every role including service_role: once
-- `status = 'concluida'`, `texto_extraido` cannot be REPLACED by different
-- text; once `codigo` / `imovel_documento_id` are non-NULL, they are frozen
-- independently of status (a linked extraction is never re-pointed at a
-- different imóvel). 🔴 Purging is NOT a replacement — `estrutura_service.
-- purgar_texto_expirado` (point 2, below) sets `texto_extraido` to NULL past
-- its retention date, and the trigger deliberately lets that one transition
-- through: the write-once guarantee protects the text from being REWRITTEN,
-- not from being retired.
--
-- 4. A CROSS-ORG FK HOLE ON `imovel_documento_id`
-- --------------------------------------------------
-- 109 FK'd `matricula_extracoes.imovel_documento_id` to
-- `imovel_documentos(id)` alone — `id` is globally unique, so nothing stopped
-- (org A, extraction) from pointing at (org B, document) as long as the
-- literal UUID matched, which application code never sends but the
-- constraint itself did not rule out. Re-keyed to the composite
-- `(org_id, imovel_documento_id)` -> `imovel_documentos(org_id, id)`, the same
-- shape migration 076 uses for `imovel_dados` / `imovel_documentos` ->
-- `imovel_registry`: the referenced row is now provably the SAME org's.
--
-- 5. AN `/acessos` READ ROUTE FOR THE IMÓVEL SURFACE
-- -----------------------------------------------------
-- `card_hub` ships `GET .../documentos/{id}/acessos` for both its document
-- surfaces; `imovel_hub` has had the LOG since 109 but no way to READ it back
-- short of a direct table query. `app/modules/imovel_hub/documentos_service.py`
-- gains `listar_acessos`, wired to a new route — no schema change, listed
-- here because it ships in the same commit as the rest of this file's LGPD
-- work.
--
-- WHAT THIS DOES NOT DO
-- ----------------------
-- No scheduler wires `documento_store.DocumentoStore.varrer_expirados` (which
-- already sweeps `imovel_documentos` once `retencao_ate` is set — no new code
-- needed there) or the new `matriculas.estrutura_service.purgar_texto_expirado`
-- for `matricula_extracoes` to a cron job. Neither does the `cliente` nor the
-- `atendimento` surface today (079/078) — this migration gives the imóvel
-- surface the SAME clock and the SAME purge primitive the other two already
-- have, not a more-finished version of it. Wiring all three to a schedule is
-- one change, tracked as `NOC-REMEDIATE[retention-sweep-scheduler]` where the
-- primitives live, not invented ad hoc here for one surface.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_documento_acessos — log a text read, linked or not
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documento_acessos
    ALTER COLUMN documento_id DROP NOT NULL;

ALTER TABLE social_wiring.imovel_documento_acessos
    ADD COLUMN IF NOT EXISTS extracao_id UUID
        REFERENCES social_wiring.matricula_extracoes (id) ON DELETE CASCADE;

COMMENT ON COLUMN social_wiring.imovel_documento_acessos.extracao_id IS
    'Set instead of documento_id for a text_view whose extraction has no '
    'imovel_documentos row (the 092 unlinked-upload shape) — see migration '
    '111. Exactly one of the two columns is set; never both, never neither.';

ALTER TABLE social_wiring.imovel_documento_acessos
    DROP CONSTRAINT IF EXISTS imovel_documento_acessos_um_alvo;
ALTER TABLE social_wiring.imovel_documento_acessos
    ADD CONSTRAINT imovel_documento_acessos_um_alvo
    CHECK ((documento_id IS NOT NULL) <> (extracao_id IS NOT NULL));

ALTER TABLE social_wiring.imovel_documento_acessos
    DROP CONSTRAINT IF EXISTS imovel_documento_acessos_acao_check;
ALTER TABLE social_wiring.imovel_documento_acessos
    ADD CONSTRAINT imovel_documento_acessos_acao_check
    CHECK (acao IN ('view', 'download', 'delete', 'text_view'));

CREATE INDEX IF NOT EXISTS idx_sw_imovel_documento_acessos_extracao
    ON social_wiring.imovel_documento_acessos (extracao_id, created_at DESC)
    WHERE extracao_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. Retention clock — the imóvel surface joins documento_retencao_politicas
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.documento_retencao_politicas
    DROP CONSTRAINT IF EXISTS documento_retencao_politicas_superficie_check;
ALTER TABLE social_wiring.documento_retencao_politicas
    ADD CONSTRAINT documento_retencao_politicas_superficie_check
    CHECK (superficie IN ('cliente', 'atendimento', 'imovel'));

-- The kept PDF (matricula / guia_iptu) and the raw transcription
-- (texto_extraido) each get a platform-default row — the allow-list
-- `app/services/documento_retencao.py::_exigir_conhecido` reads. 10 years:
-- the same prescrição decenal (CC art. 205) 079 already used for the
-- deal-level título/regime-de-bens documents — a matrícula IS the title
-- evidence, so it gets the SAME reasoning, not a shorter, arbitrary number.
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'imovel', 'matricula',      3650,
     'Evidência do título aquisitivo: prescrição decenal de pretensões '
     'contratuais (CC art. 205).'),
    (NULL, 'imovel', 'guia_iptu',      3650,
     'Acompanha a matrícula no mesmo dossiê do imóvel.'),
    (NULL, 'imovel', 'texto_extraido', 3650,
     'Transcrição da matrícula — mesma evidência, mesma janela.')
ON CONFLICT DO NOTHING;

ALTER TABLE social_wiring.imovel_documentos
    ADD COLUMN IF NOT EXISTS retencao_ate DATE;

COMMENT ON COLUMN social_wiring.imovel_documentos.retencao_ate IS
    'Stamped at upload from documento_retencao.dias_para(..., "imovel", '
    'tipo_documento) — see migration 111. NULL = no policy row (keep) or '
    'the policy says keep indefinitely; both read as "does not expire".';

CREATE INDEX IF NOT EXISTS idx_sw_imovel_documentos_retencao
    ON social_wiring.imovel_documentos (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;

ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS retencao_ate DATE;

COMMENT ON COLUMN social_wiring.matricula_extracoes.retencao_ate IS
    'Stamped when status -> concluida, from documento_retencao.dias_para('
    '..., "imovel", "texto_extraido") — see migration 111. Purge (NULLing '
    'texto_extraido, never a row delete — matricula_atos offsets and every '
    'RESTRICT citation survive) is app/modules/matriculas/estrutura_service.'
    'py::purgar_texto_expirado, unwired to a scheduler same as the other '
    'two surfaces today.';

CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_retencao
    ON social_wiring.matricula_extracoes (retencao_ate)
    WHERE retencao_ate IS NOT NULL AND texto_extraido IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Write-once guard — texto_extraido / codigo / imovel_documento_id
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.matricula_extracoes_protege_concluida()
  RETURNS trigger
  LANGUAGE plpgsql
AS $$
BEGIN
    -- Purging (-> NULL) is the one sanctioned post-concluida change — see
    -- `estrutura_service.purgar_texto_expirado`. Anything else that changes
    -- the text (a different string) is a rewrite and is refused.
    IF OLD.status = 'concluida'
       AND NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido
       AND NEW.texto_extraido IS NOT NULL THEN
        RAISE EXCEPTION
            'matricula_extracoes %: texto_extraido não pode ser alterado '
            'após status = concluida', OLD.id;
    END IF;

    IF OLD.codigo IS NOT NULL
       AND NEW.codigo IS DISTINCT FROM OLD.codigo THEN
        RAISE EXCEPTION
            'matricula_extracoes %: codigo não pode ser alterado após '
            'vinculado a um imóvel', OLD.id;
    END IF;

    IF OLD.imovel_documento_id IS NOT NULL
       AND NEW.imovel_documento_id IS DISTINCT FROM OLD.imovel_documento_id THEN
        RAISE EXCEPTION
            'matricula_extracoes %: imovel_documento_id não pode ser '
            'alterado após vinculado', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION social_wiring.matricula_extracoes_protege_concluida() IS
    'Backstop for the write-once guarantee migration 109''s offsets rely on. '
    'Applies to EVERY role, including service_role — the background pipeline '
    '(app/modules/matriculas/service.py) never touches these three columns '
    'after the one write that sets them, so there is no legitimate case to '
    'exempt. See migration 111.';

DROP TRIGGER IF EXISTS protege_concluida_matricula_extracoes
    ON social_wiring.matricula_extracoes;
CREATE TRIGGER protege_concluida_matricula_extracoes
    BEFORE UPDATE ON social_wiring.matricula_extracoes
    FOR EACH ROW EXECUTE FUNCTION social_wiring.matricula_extracoes_protege_concluida();

-- ----------------------------------------------------------------------------
-- 4. Composite FK — imovel_documento_id, same-org only (match 076)
-- ----------------------------------------------------------------------------
-- A composite FK target needs a UNIQUE constraint on exactly those columns;
-- `id` is already the primary key, so this adds no new uniqueness, only a
-- constraint Postgres can point the FK at.
ALTER TABLE social_wiring.imovel_documentos
    DROP CONSTRAINT IF EXISTS imovel_documentos_org_id_id_key;
ALTER TABLE social_wiring.imovel_documentos
    ADD CONSTRAINT imovel_documentos_org_id_id_key UNIQUE (org_id, id);

ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_imovel_documento_fk;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_imovel_documento_fk
    FOREIGN KEY (org_id, imovel_documento_id)
    REFERENCES social_wiring.imovel_documentos (org_id, id)
    ON DELETE SET NULL;
