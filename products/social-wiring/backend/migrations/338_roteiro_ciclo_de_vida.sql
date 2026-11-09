-- ============================================================================
-- Migration 338 · social_wiring: the roteiro lifecycle (rascunho -> gerado),
-- the visita outcome vocabulary, the supervisor role.
-- ============================================================================
-- CONTRACT products/social-wiring/projects/roteiro-ciclo-CONTRACT.md §1. Owner decisions 2026-11-09:
--
--   * every edit of a roteiro is saved: a roteiro is born `rascunho` and is `gerado` only when somebody says so
--     (POST .../gerar). A gerado roteiro keeps its imóveis fixed; date, time, observations and the visit outcomes
--     stay editable.
--   * the data tracks how many visits each lead consolidated or lost, how many each imóvel received or lost, and
--     the corretor's performance: `consolidadas = realizada`, `perdidas = cancelada + nao_compareceu`,
--     `neutras = reagendada + pendente`. A REAGENDADA visit is neutral — its new date lives in a NEW roteiro.
--   * reopening a gerado roteiro is for a SUPERVISOR (a new role), owners and admins, and only while no visita has
--     an outcome.
--
-- WHAT THIS FILE DOES
--   1. roteiros: status / gerado_* / reaberto_* / criado_por / updated_at (+ trigger). BACKFILL: every existing row is
--      `gerado` (those roteiros were consolidated on creation) with gerado_em = created_at. `status` is added with
--      DEFAULT 'gerado' so the fill IS the backfill, then the default flips to 'rascunho' for new rows — which also
--      makes the file safe to run twice (a re-run can never flip a live draft to gerado).
--   2. visitas: status CHECK -> pendente|realizada|cancelada|nao_compareceu|reagendada; cancelada_por,
--      cancelada_motivo, reagendada_para_visita_id, resultado_em, resultado_por, horario (the visit's own time). BACKFILL from the old
--      `nao_realizada` + `nao_realizada_motivo`:
--        cliente_nao_compareceu -> nao_compareceu          reagendada -> reagendada
--        cliente_desistiu | imovel_indisponivel | outro -> cancelada (same cancelada_motivo, cancelada_por NULL = legacy)
--        nao_realizada with motivo NULL -> cancelada, cancelada_motivo 'outro'
--      `nao_realizada_motivo` is now VESTIGIAL: the column and its CHECK stay (legacy, read-only); NOTHING writes it
--      after this change and the API no longer returns it.
--   3. `cancelada` needs `cancelada_por` + `cancelada_motivo`: a CHECK added NOT VALID AFTER the backfill, so legacy
--      rows stand and every new or updated row is checked.
--   4. usuario_papeis: the per-org role table ('supervisor'). SEED-FIRST CHECK (2026-11-09): neither the seed
--      (`noctusai_lib.primitives.roles`: ORG_ROLES = base roles + market roles, `noctus_users.org_role` / `org_memberships`
--      are ONE role per org) nor core carries a per-product, additive role mechanism, and a new org_role would be
--      assignable on the team page of every product. So the product owns this one small table.
--      SERVICE-ONLY (REVOKE browser roles, as 328/330 did): nothing in the browser reads it — the server computes
--      `permissoes` — and a new browser grant would be a new access-tier finding (contract §1 said "org SELECT";
--      reported as a deliberate tightening).
--   5. cliente_imovel_interesses.origem: + 'julia' (F4).
--   6. roteiro_gerar(): the ONE atomic write of "gerar" (status flip + lead link). The funnel move is Python
--      (stage gate, pipeline_movimentos, handoffs) and stays a REPORTED, never-raising step, exactly as the old
--      create did.
--   7. vw_imovel_visita_contagem moves to the same derivation (drafts excluded).
--   8. roteiro_eventos (v1.2, owner: "everything inside our products must be measured"): an APPEND-ONLY event ledger of
--      the whole lifecycle — who did what to which roteiro / visita, from what to what, when. It is written by TRIGGERS on
--      `roteiros` and `visitas`, so the event and the change are ONE statement's transaction by construction (a failed event
--      write fails the change) and no code path can forget it. The actor comes from the row (`criado_por`, `gerado_por`,
--      `reaberto_por`, `resultado_por`, else `atualizado_por`, which every write route stamps). Backfilled history carries
--      `dados.origem = 'backfill'`. No route reads it yet (a timeline endpoint can come later).
--
-- POST-DEPLOY (owner-run, NOT part of this migration, never auto-applied) — grant Cindy Kumagai `supervisor` in the
-- One org (fd169d29-4d0a-4b04-9a5e-25e69407614d). Look her user id up in public.noctus_users first:
--
--   INSERT INTO social_wiring.usuario_papeis (org_id, user_id, papel, concedido_por, concedido_em)
--   VALUES ('fd169d29-4d0a-4b04-9a5e-25e69407614d', '<CINDY_KUMAGAI_USER_ID>', 'supervisor',
--           '<GRANTING_OWNER_USER_ID>', now())
--   ON CONFLICT (org_id, user_id, papel) DO NOTHING;
--
-- FORWARD-ONLY, IDEMPOTENT. Backward-compatible with the previous image for READS only on the columns it knows; the
-- old image's `nao_realizada` writes would now violate the CHECK, which is why the BE and FE ship in the same release.
-- ============================================================================

SET search_path = social_wiring, public;
SET lock_timeout = '5s';

-- ----------------------------------------------------------------------------
-- 1. roteiros — the lifecycle
-- ----------------------------------------------------------------------------
-- DEFAULT 'gerado' on the ADD COLUMN backfills every existing row in one step (a constant default is a metadata-only
-- change on PG11+, no table rewrite); the default is then flipped for every FUTURE row.
ALTER TABLE social_wiring.roteiros
    ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'gerado',
    ADD COLUMN IF NOT EXISTS gerado_em     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gerado_por    UUID,
    ADD COLUMN IF NOT EXISTS reaberto_em   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reaberto_por  UUID,
    ADD COLUMN IF NOT EXISTS criado_por    UUID,
    ADD COLUMN IF NOT EXISTS updated_at    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS atualizado_por UUID;

ALTER TABLE social_wiring.roteiros ALTER COLUMN status SET DEFAULT 'rascunho';

UPDATE social_wiring.roteiros
   SET gerado_em = created_at
 WHERE status = 'gerado' AND gerado_em IS NULL;

-- Existing rows have no edit history: their last change is their creation (NULL-guarded, so a re-run is a no-op).
UPDATE social_wiring.roteiros SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE social_wiring.roteiros ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE social_wiring.roteiros ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE social_wiring.roteiros DROP CONSTRAINT IF EXISTS roteiros_status_valido;
ALTER TABLE social_wiring.roteiros
    ADD CONSTRAINT roteiros_status_valido CHECK (status IN ('rascunho', 'gerado'));

-- `data_visita` stays NULLABLE in the DB (a draft may not have one yet); it is REQUIRED only to gerar.

CREATE OR REPLACE FUNCTION social_wiring.roteiros_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_updated_at_roteiros ON social_wiring.roteiros;
CREATE TRIGGER set_updated_at_roteiros
    BEFORE UPDATE ON social_wiring.roteiros
    FOR EACH ROW EXECUTE FUNCTION social_wiring.roteiros_touch_updated_at();

COMMENT ON COLUMN social_wiring.roteiros.status IS
    'rascunho = being built (autosaved, imóveis editable, no PDF, outside the feedback flow and every count); '
    'gerado = consolidated (imóveis fixed, PDF available, enters the funnel/feedback/counts). Migration 338.';
COMMENT ON COLUMN social_wiring.roteiros.gerado_em IS 'When the roteiro was generated (backfill: created_at). Migration 338.';
COMMENT ON COLUMN social_wiring.roteiros.reaberto_em IS 'Last reopen as rascunho; a supervisor/owner/admin act. Migration 338.';

-- ----------------------------------------------------------------------------
-- 2. visitas — the outcome vocabulary
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.visitas DROP CONSTRAINT IF EXISTS visitas_status_valido;
ALTER TABLE social_wiring.visitas DROP CONSTRAINT IF EXISTS visitas_cancelada_completa;

ALTER TABLE social_wiring.visitas
    ADD COLUMN IF NOT EXISTS cancelada_por             TEXT,
    ADD COLUMN IF NOT EXISTS cancelada_motivo          TEXT,
    ADD COLUMN IF NOT EXISTS reagendada_para_visita_id UUID
        REFERENCES social_wiring.visitas (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS resultado_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resultado_por             UUID,
    ADD COLUMN IF NOT EXISTS horario                   TIME,
    ADD COLUMN IF NOT EXISTS atualizado_por            UUID;

-- The backfill runs while NO status CHECK is in place (the old one is gone, the new one is added below).
UPDATE social_wiring.visitas
   SET status = CASE
           WHEN nao_realizada_motivo = 'cliente_nao_compareceu' THEN 'nao_compareceu'
           WHEN nao_realizada_motivo = 'reagendada'             THEN 'reagendada'
           ELSE 'cancelada'
       END,
       cancelada_motivo = CASE
           WHEN nao_realizada_motivo IN ('cliente_desistiu', 'imovel_indisponivel') THEN nao_realizada_motivo
           WHEN nao_realizada_motivo IN ('cliente_nao_compareceu', 'reagendada')    THEN NULL
           ELSE 'outro'
       END
 WHERE status = 'nao_realizada';

-- When the outcome was recorded: the stamp that already existed (feedback_em). Never invented for a pendente row.
UPDATE social_wiring.visitas
   SET resultado_em = feedback_em
 WHERE status <> 'pendente' AND resultado_em IS NULL AND feedback_em IS NOT NULL;

ALTER TABLE social_wiring.visitas
    ADD CONSTRAINT visitas_status_valido
    CHECK (status IN ('pendente', 'realizada', 'cancelada', 'nao_compareceu', 'reagendada'));

ALTER TABLE social_wiring.visitas DROP CONSTRAINT IF EXISTS visitas_cancelada_por_valido;
ALTER TABLE social_wiring.visitas
    ADD CONSTRAINT visitas_cancelada_por_valido
    CHECK (cancelada_por IS NULL OR cancelada_por IN ('cliente', 'proprietario', 'corretor'));

ALTER TABLE social_wiring.visitas DROP CONSTRAINT IF EXISTS visitas_cancelada_motivo_valido;
ALTER TABLE social_wiring.visitas
    ADD CONSTRAINT visitas_cancelada_motivo_valido
    CHECK (cancelada_motivo IS NULL OR cancelada_motivo IN ('cliente_desistiu', 'imovel_indisponivel', 'outro'));

-- NOT VALID, AFTER the backfill: the legacy canceladas (cancelada_por NULL) stand; every INSERT and every UPDATE of
-- a row from here on is checked (an UPDATE of a legacy row must complete it — the API answers 422 cancelada_incompleta).
ALTER TABLE social_wiring.visitas
    ADD CONSTRAINT visitas_cancelada_completa
    CHECK (status <> 'cancelada' OR (cancelada_por IS NOT NULL AND cancelada_motivo IS NOT NULL))
    NOT VALID;

COMMENT ON COLUMN social_wiring.visitas.nao_realizada_motivo IS
    'VESTIGIAL (migration 338): legacy read-only. Nothing writes it any more; the outcome is status + cancelada_por + '
    'cancelada_motivo. Originally migration 219.';
COMMENT ON COLUMN social_wiring.visitas.cancelada_por IS
    'Who cancelled: cliente | proprietario | corretor. NULL only on legacy canceladas (backfill). Migration 338.';
COMMENT ON COLUMN social_wiring.visitas.cancelada_motivo IS
    'Why it was cancelled: cliente_desistiu | imovel_indisponivel | outro. Migration 338.';
COMMENT ON COLUMN social_wiring.visitas.reagendada_para_visita_id IS
    'A reagendada visita points at the visita of the NEW roteiro that replaces it. Neutral in every count. Migration 338.';
COMMENT ON COLUMN social_wiring.visitas.horario IS
    'The visit''s own time of day (optional, editable in both roteiro statuses). Migration 338.';
COMMENT ON COLUMN social_wiring.visitas.resultado_em IS 'When the outcome was recorded (cleared if set back to pendente). Migration 338.';

-- ----------------------------------------------------------------------------
-- 3. usuario_papeis — per-org additive roles (supervisor)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.usuario_papeis (
    org_id         UUID NOT NULL,
    user_id        UUID NOT NULL,
    papel          TEXT NOT NULL CHECK (papel IN ('supervisor')),
    concedido_por  UUID,
    concedido_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id, papel)
);

ALTER TABLE social_wiring.usuario_papeis ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "usuario_papeis_service_role" ON social_wiring.usuario_papeis;
CREATE POLICY "usuario_papeis_service_role" ON social_wiring.usuario_papeis
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE social_wiring.usuario_papeis FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.usuario_papeis TO service_role;

COMMENT ON TABLE social_wiring.usuario_papeis IS 'tier:org';
COMMENT ON COLUMN social_wiring.usuario_papeis.papel IS
    'Additive per-org role on top of noctus_users.org_role. supervisor may reopen a gerado roteiro (with owners and '
    'admins). Granted by an owner-run statement (service client only). Migration 338.';

-- ----------------------------------------------------------------------------
-- 4. interesses: the Julia origin (F4)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cliente_imovel_interesses
    DROP CONSTRAINT IF EXISTS cliente_imovel_interesses_origem_valida;
ALTER TABLE social_wiring.cliente_imovel_interesses
    ADD CONSTRAINT cliente_imovel_interesses_origem_valida
    CHECK (origem IN ('lead', 'manual', 'campanha', 'roteiro', 'permuta', 'julia'));

-- ----------------------------------------------------------------------------
-- 5. roteiro_gerar — the atomic "gerar" (contract R8)
-- ----------------------------------------------------------------------------
-- ONE transaction (a plpgsql function body is one): the row lock, the guards, the status flip and the lead link
-- commit together or not at all. A refusal is a RETURN VALUE `{status:'recusado', code}` so the API maps it to
-- its typed error; a failure inside rolls the flip back.
--
-- LEAD LINK: for each live visita, an interesse (cliente, codigo, origem='roteiro') carrying the atendimento's
-- lead_id / meta_ads_lead_id. FILLS EMPTY ONLY and never changes an existing row's origem; a (cliente, codigo) that
-- has ANY row — including a soft-deleted one — is never resurrected (a removal stays removed until a human re-adds).
CREATE OR REPLACE FUNCTION social_wiring.roteiro_gerar(p_org_id uuid, p_roteiro_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path = pg_catalog, social_wiring, pg_temp
AS $$
DECLARE
    r        social_wiring.roteiros%ROWTYPE;
    a        social_wiring.atendimentos%ROWTYPE;
    n_vis    integer;
    n_novos  integer := 0;
    n_fill   integer := 0;
BEGIN
    SELECT * INTO r
      FROM social_wiring.roteiros
     WHERE id = p_roteiro_id AND org_id = p_org_id AND deleted_at IS NULL
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'recusado', 'code', 'nao_encontrado');
    END IF;
    IF r.status = 'gerado' THEN
        RETURN jsonb_build_object('status', 'recusado', 'code', 'roteiro_ja_gerado');
    END IF;

    SELECT count(*) INTO n_vis
      FROM social_wiring.visitas
     WHERE roteiro_id = r.id AND org_id = p_org_id AND deleted_at IS NULL;
    IF n_vis = 0 THEN
        RETURN jsonb_build_object('status', 'recusado', 'code', 'roteiro_sem_imoveis');
    END IF;
    IF r.data_visita IS NULL THEN
        RETURN jsonb_build_object('status', 'recusado', 'code', 'roteiro_sem_data');
    END IF;

    UPDATE social_wiring.roteiros
       SET status = 'gerado', gerado_em = now(), gerado_por = p_user_id
     WHERE id = r.id;

    SELECT * INTO a FROM social_wiring.atendimentos WHERE id = r.atendimento_id AND org_id = p_org_id;
    IF FOUND AND a.cliente_id IS NOT NULL THEN
        -- Fill the empty lead link of a LIVE row (never its origem).
        UPDATE social_wiring.cliente_imovel_interesses i
           SET lead_id = a.lead_id, meta_ads_lead_id = a.meta_ads_lead_id
         WHERE i.org_id = p_org_id AND i.cliente_id = a.cliente_id AND i.deleted_at IS NULL
           AND i.lead_id IS NULL AND i.meta_ads_lead_id IS NULL
           AND (a.lead_id IS NOT NULL OR a.meta_ads_lead_id IS NOT NULL)
           AND i.codigo IN (SELECT v.codigo FROM social_wiring.visitas v
                             WHERE v.roteiro_id = r.id AND v.org_id = p_org_id AND v.deleted_at IS NULL);
        GET DIAGNOSTICS n_fill = ROW_COUNT;

        INSERT INTO social_wiring.cliente_imovel_interesses
            (org_id, cliente_id, codigo, origem, lead_id, meta_ads_lead_id, created_by)
        SELECT DISTINCT p_org_id, a.cliente_id, v.codigo, 'roteiro', a.lead_id, a.meta_ads_lead_id, p_user_id
          FROM social_wiring.visitas v
         WHERE v.roteiro_id = r.id AND v.org_id = p_org_id AND v.deleted_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM social_wiring.cliente_imovel_interesses i
                            WHERE i.cliente_id = a.cliente_id AND i.codigo = v.codigo);
        GET DIAGNOSTICS n_novos = ROW_COUNT;
    END IF;

    RETURN jsonb_build_object('status', 'ok', 'interesses_criados', n_novos, 'interesses_preenchidos', n_fill);
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.roteiro_gerar(uuid, uuid, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.roteiro_gerar(uuid, uuid, uuid) TO service_role;

COMMENT ON FUNCTION social_wiring.roteiro_gerar(uuid, uuid, uuid) IS
    'Atomic "gerar roteiro": lock + guards + status flip + lead link in one transaction. Migration 338.';


-- ----------------------------------------------------------------------------
-- 7. roteiro_eventos — the append-only event ledger (v1.2)
-- ----------------------------------------------------------------------------
-- Shape follows the product's other append-only ledger (057 `cliente_documento_acessos`): no UPDATE/DELETE for anybody,
-- here enforced three ways — no grant (service_role included: SELECT + INSERT only), a trigger that refuses UPDATE/DELETE
-- for any role that still holds the privilege (the table owner), and no FK to roteiros/visitas (an event must outlive a
-- deleted roteiro; deletion is soft anyway). Service-only like every table since 328/330: reads go through the API.
CREATE TABLE IF NOT EXISTS social_wiring.roteiro_eventos (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL,
    roteiro_id UUID NOT NULL,
    visita_id  UUID,
    tipo       TEXT NOT NULL CHECK (tipo IN (
        'roteiro_criado', 'roteiro_gerado', 'roteiro_reaberto', 'roteiro_excluido',
        'visita_adicionada', 'visita_removida', 'visita_reordenada', 'visita_resultado',
        'visita_horario', 'visita_reagendada', 'data_alterada')),
    de         TEXT,
    para       TEXT,
    dados      JSONB NOT NULL DEFAULT '{}'::jsonb,
    ator_id    UUID,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_roteiro_eventos_roteiro ON social_wiring.roteiro_eventos (org_id, roteiro_id, criado_em);
CREATE INDEX IF NOT EXISTS idx_sw_roteiro_eventos_tipo ON social_wiring.roteiro_eventos (org_id, tipo, criado_em);

ALTER TABLE social_wiring.roteiro_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "roteiro_eventos_service_role" ON social_wiring.roteiro_eventos;
CREATE POLICY "roteiro_eventos_service_role" ON social_wiring.roteiro_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.roteiro_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.roteiro_eventos TO service_role;

COMMENT ON TABLE social_wiring.roteiro_eventos IS 'tier:org';
COMMENT ON COLUMN social_wiring.roteiro_eventos.dados IS
    'Event payload. visita_resultado: cancelada_por / cancelada_motivo; visita_reagendada: nova_visita_id / novo_roteiro_id; '
    'backfilled rows carry origem = backfill. Migration 338.';

CREATE OR REPLACE FUNCTION social_wiring.roteiro_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'roteiro_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$;
DROP TRIGGER IF EXISTS roteiro_eventos_imutavel ON social_wiring.roteiro_eventos;
CREATE TRIGGER roteiro_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.roteiro_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.roteiro_eventos_imutavel();

-- BACKFILL (history that existed before the ledger): one roteiro_criado + one roteiro_gerado per existing roteiro (at
-- created_at), and one visita_resultado per visita that already has an outcome (at feedback_em / realizada_em). Only
-- roteiros with NO event yet, so a re-run never duplicates and never touches a roteiro the triggers already follow.
-- Runs BEFORE the triggers are (re)created, so the backfill never writes events about itself.
INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, dados, ator_id, criado_em)
SELECT r.org_id, r.id, 'roteiro_criado', NULL, 'rascunho',
       jsonb_build_object('origem', 'backfill', 'data_visita', r.data_visita, 'titulo', r.titulo), r.criado_por, r.created_at
  FROM social_wiring.roteiros r
 WHERE NOT EXISTS (SELECT 1 FROM social_wiring.roteiro_eventos e WHERE e.roteiro_id = r.id);

INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, dados, ator_id, criado_em)
SELECT r.org_id, r.id, 'roteiro_gerado', 'rascunho', 'gerado', jsonb_build_object('origem', 'backfill'), r.gerado_por,
       COALESCE(r.gerado_em, r.created_at)
  FROM social_wiring.roteiros r
 WHERE r.status = 'gerado'
   AND EXISTS (SELECT 1 FROM social_wiring.roteiro_eventos e
                WHERE e.roteiro_id = r.id AND e.tipo = 'roteiro_criado' AND e.dados->>'origem' = 'backfill')
   AND NOT EXISTS (SELECT 1 FROM social_wiring.roteiro_eventos e WHERE e.roteiro_id = r.id AND e.tipo = 'roteiro_gerado');

INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, de, para, dados, ator_id, criado_em)
SELECT v.org_id, v.roteiro_id, v.id, 'visita_resultado', 'pendente', v.status,
       jsonb_build_object('origem', 'backfill', 'cancelada_por', v.cancelada_por, 'cancelada_motivo', v.cancelada_motivo),
       v.resultado_por, COALESCE(v.feedback_em, v.realizada_em, v.created_at)
  FROM social_wiring.visitas v
 WHERE v.status <> 'pendente'
   AND EXISTS (SELECT 1 FROM social_wiring.roteiro_eventos e
                WHERE e.roteiro_id = v.roteiro_id AND e.tipo = 'roteiro_criado' AND e.dados->>'origem' = 'backfill')
   AND NOT EXISTS (SELECT 1 FROM social_wiring.roteiro_eventos e WHERE e.visita_id = v.id AND e.tipo = 'visita_resultado');

-- The writers: AFTER triggers, so an event is inserted in the SAME transaction as the row change that caused it; if the
-- event insert fails the statement fails (a roteiro change is never un-measured). INVOKER rights, search_path pinned.
CREATE OR REPLACE FUNCTION social_wiring.roteiros_registrar_evento()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, social_wiring, pg_temp
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.id, 'roteiro_criado', NULL, NEW.status,
                jsonb_build_object('data_visita', NEW.data_visita, 'hora_visita', NEW.hora_visita, 'titulo', NEW.titulo,
                                   'atendimento_id', NEW.atendimento_id),
                NEW.criado_por);
        RETURN NEW;
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF NEW.status = 'gerado' THEN
            INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, ator_id)
            VALUES (NEW.org_id, NEW.id, 'roteiro_gerado', OLD.status, NEW.status, NEW.gerado_por);
        ELSE
            INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, ator_id)
            VALUES (NEW.org_id, NEW.id, 'roteiro_reaberto', OLD.status, NEW.status, NEW.reaberto_por);
        END IF;
    END IF;
    IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, ator_id)
        VALUES (NEW.org_id, NEW.id, 'roteiro_excluido', OLD.status, NEW.status, NEW.atualizado_por);
    END IF;
    IF NEW.data_visita IS DISTINCT FROM OLD.data_visita OR NEW.hora_visita IS DISTINCT FROM OLD.hora_visita THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.id, 'data_alterada', OLD.data_visita::text, NEW.data_visita::text,
                jsonb_build_object('hora_de', OLD.hora_visita, 'hora_para', NEW.hora_visita), NEW.atualizado_por);
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS roteiros_evento ON social_wiring.roteiros;
CREATE TRIGGER roteiros_evento
    AFTER INSERT OR UPDATE ON social_wiring.roteiros
    FOR EACH ROW EXECUTE FUNCTION social_wiring.roteiros_registrar_evento();

CREATE OR REPLACE FUNCTION social_wiring.visitas_registrar_evento()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, social_wiring, pg_temp
AS $$
DECLARE
    novo_roteiro uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, dados, ator_id)
        VALUES (NEW.org_id, NEW.roteiro_id, NEW.id, 'visita_adicionada',
                jsonb_build_object('codigo', NEW.codigo, 'ordem', NEW.ordem), NEW.atualizado_por);
        RETURN NEW;
    END IF;

    IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, dados, ator_id)
        VALUES (NEW.org_id, NEW.roteiro_id, NEW.id, 'visita_removida',
                jsonb_build_object('codigo', NEW.codigo), NEW.atualizado_por);
    END IF;
    IF NEW.ordem IS DISTINCT FROM OLD.ordem THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.roteiro_id, NEW.id, 'visita_reordenada', OLD.ordem::text, NEW.ordem::text,
                jsonb_build_object('codigo', NEW.codigo), NEW.atualizado_por);
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.roteiro_id, NEW.id, 'visita_resultado', OLD.status, NEW.status,
                jsonb_build_object('codigo', NEW.codigo, 'cancelada_por', NEW.cancelada_por,
                                   'cancelada_motivo', NEW.cancelada_motivo),
                COALESCE(NEW.resultado_por, NEW.atualizado_por));
    END IF;
    IF NEW.horario IS DISTINCT FROM OLD.horario THEN
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.roteiro_id, NEW.id, 'visita_horario', OLD.horario::text, NEW.horario::text,
                jsonb_build_object('codigo', NEW.codigo), NEW.atualizado_por);
    END IF;
    IF NEW.reagendada_para_visita_id IS NOT NULL AND OLD.reagendada_para_visita_id IS DISTINCT FROM NEW.reagendada_para_visita_id THEN
        SELECT roteiro_id INTO novo_roteiro FROM social_wiring.visitas WHERE id = NEW.reagendada_para_visita_id;
        INSERT INTO social_wiring.roteiro_eventos (org_id, roteiro_id, visita_id, tipo, dados, ator_id)
        VALUES (NEW.org_id, NEW.roteiro_id, NEW.id, 'visita_reagendada',
                jsonb_build_object('codigo', NEW.codigo, 'nova_visita_id', NEW.reagendada_para_visita_id,
                                   'novo_roteiro_id', novo_roteiro),
                COALESCE(NEW.resultado_por, NEW.atualizado_por));
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS visitas_evento ON social_wiring.visitas;
CREATE TRIGGER visitas_evento
    AFTER INSERT OR UPDATE ON social_wiring.visitas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.visitas_registrar_evento();

-- ----------------------------------------------------------------------------
-- 6. vw_imovel_visita_contagem — the same ONE derivation (drafts excluded)
-- ----------------------------------------------------------------------------
-- consolidadas = realizada, perdidas = cancelada + nao_compareceu, neutras = reagendada + pendente. A column set
-- change cannot go through CREATE OR REPLACE, hence the DROP. `realizadas` is kept (it IS `consolidadas`);
-- `nao_realizadas` is gone with the status it counted.
DROP VIEW IF EXISTS social_wiring.vw_imovel_visita_contagem;
CREATE VIEW social_wiring.vw_imovel_visita_contagem
WITH (security_invoker = true)
AS
SELECT
    v.org_id,
    v.codigo,
    COUNT(*)                                            AS total,
    COUNT(*) FILTER (WHERE v.status = 'realizada')      AS realizadas,
    COUNT(*) FILTER (WHERE v.status = 'cancelada')      AS canceladas,
    COUNT(*) FILTER (WHERE v.status = 'nao_compareceu') AS nao_compareceu,
    COUNT(*) FILTER (WHERE v.status = 'reagendada')     AS reagendadas,
    COUNT(*) FILTER (WHERE v.status = 'pendente')       AS pendentes,
    COUNT(*) FILTER (WHERE v.status = 'realizada')      AS consolidadas,
    COUNT(*) FILTER (WHERE v.status IN ('cancelada', 'nao_compareceu')) AS perdidas,
    COUNT(*) FILTER (WHERE v.status IN ('reagendada', 'pendente'))      AS neutras,
    COUNT(DISTINCT a.cliente_id)                        AS clientes_distintos,
    MIN(v.created_at)                                   AS primeira_visita_em,
    MAX(COALESCE(v.resultado_em, v.feedback_em, v.created_at)) AS ultima_visita_em
FROM social_wiring.visitas v
JOIN social_wiring.roteiros r
      ON r.id     = v.roteiro_id
     AND r.org_id = v.org_id
JOIN social_wiring.atendimentos a
      ON a.id     = r.atendimento_id
     AND a.org_id = r.org_id
WHERE v.deleted_at IS NULL
  AND r.deleted_at IS NULL
  AND r.status = 'gerado'
GROUP BY v.org_id, v.codigo;

COMMENT ON VIEW social_wiring.vw_imovel_visita_contagem IS
    'Visit counts per imovel (gerado roteiros only), one row per (org_id, codigo) ever visited: consolidadas = '
    'realizada, perdidas = cancelada + nao_compareceu, neutras = reagendada + pendente. Keyed on the registry '
    'codigo, so a delisted imovel keeps its history. Migration 338.';

-- Index for the drafts-excluded joins and the feedback scan (gerado only).
CREATE INDEX IF NOT EXISTS idx_sw_roteiros_org_status
    ON social_wiring.roteiros (org_id, status, created_at DESC)
    WHERE deleted_at IS NULL;

NOTIFY pgrst, 'reload schema';
