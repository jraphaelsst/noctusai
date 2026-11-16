-- ============================================================================
-- Migration 351 · social_wiring: the Biblioteca de virais becomes PLATFORM-WIDE (M2, EXPAND ONLY)
-- ============================================================================
-- WHY
-- ---
-- Spec: products/social-wiring/projects/core-studio-build/specs/estruturas-contract.md sections 3.2 / 4 (EST-2, owner
-- decisions of 2026-11-15): the monitored profiles and the viral videos are one library for the whole platform. Only
-- platform admins create / edit it (through the API, service role); orgs and brands only CHOOSE which library profiles
-- they use (cs_biblioteca_referencias stays per marca / org). Ingestion runs under ONE platform org (the NoctusAI org,
-- setting corestudio_biblioteca_org_id), so no row of these tables is owned by a customer org any more.
--
--   * cs_perfis_monitorados -- org_id becomes NULLABLE (new rows are written with NULL); `monitorar` (library-only
--                              profiles -- imported, never scraped -- are false); `nome_editado` (an admin display-name
--                              override the sync must keep); UNIQUE (rede, handle) for the
--                              platform rows (NULL org). The old (org_id, rede, handle) index stays for the previous
--                              image (N-1). No browser grant, no browser policy any more: tier `platform`.
--   * cs_virais             -- org_id NULLABLE; UNIQUE (codigo) (the identity column is already globally unique);
--                              ig_shortcode (UNIQUE when present: an Instagram shortcode is global -- the admin
--                              "add by link" dedupe key), origem_inclusao ('sync' | 'link_manual'), incluido_por.
--                              No browser grant, no browser policy: tier `platform`.
--   * cs_perfil_eventos     -- NEW, append-only, content-free: who did what to a profile / video (EOA leg).
--   * cs_perfil_purgar()    -- NEW SECURITY DEFINER RPC: the ONE transaction that erases a profile (LGPD opt-out,
--                              admin delete, retention) with its virais and Estruturas (FK cascade) and writes the
--                              content-free events (cs_estrutura_eventos.excluida + cs_perfil_eventos).
--   * cs_estrutura_eventos.ator_tipo also accepts 'sistema_retencao' (the retention sweep erasing archived Estruturas).
--
-- NOT done here (contraction, owner-gated, >= 2 deploys later = M5): dropping org_id / the old unique indexes. Prod has
-- 0 rows in these tables today, but the migration is written as if rows existed: every step is metadata-only or
-- guarded, lock_timeout is bounded, and no existing row is rewritten.
-- Backward compatible with the previous image (it selects / filters on org_id, which stays). FORWARD-ONLY, IDEMPOTENT.
-- GuardProbes: _SW_351_PROBES in mcp/noctusai/tools/noctus/dev/verify_db_guards.py.
-- Requires 229 (library tables), 320 (video_url), 350 (cs_estruturas + cs_estrutura_evento helper).
-- ============================================================================

SET search_path = social_wiring, public;
SET lock_timeout = '5s';

DO $guard$
BEGIN
  IF to_regclass('social_wiring.cs_perfis_monitorados') IS NULL OR to_regclass('social_wiring.cs_virais') IS NULL THEN
    RAISE EXCEPTION 'Migration 351 requires the cs_* library tables of migration 229 -- apply 229 first';
  END IF;
  IF to_regclass('social_wiring.cs_estruturas') IS NULL OR to_regclass('social_wiring.cs_estrutura_eventos') IS NULL THEN
    RAISE EXCEPTION 'Migration 351 requires migration 350 (cs_estruturas) -- apply 350 first';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. cs_perfis_monitorados -> platform rows
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_perfis_monitorados ALTER COLUMN org_id DROP NOT NULL;
ALTER TABLE social_wiring.cs_perfis_monitorados ADD COLUMN IF NOT EXISTS monitorar BOOLEAN NOT NULL DEFAULT true;
-- nome_editado: an admin overrode the display name; the sync must not overwrite it with the source's name.
ALTER TABLE social_wiring.cs_perfis_monitorados ADD COLUMN IF NOT EXISTS nome_editado BOOLEAN NOT NULL DEFAULT false;
COMMENT ON COLUMN social_wiring.cs_perfis_monitorados.monitorar IS
    'Migration 351 - true = the daily sync scrapes this profile; false = library-only (imported / added by link). org_id IS NULL = platform row.';
CREATE UNIQUE INDEX IF NOT EXISTS cs_perfis_monitorados_plataforma_handle_uq
    ON social_wiring.cs_perfis_monitorados (rede, handle) WHERE org_id IS NULL;

-- ----------------------------------------------------------------------------
-- 2. cs_virais -> platform rows + "add by link"
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cs_virais ALTER COLUMN org_id DROP NOT NULL;
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS ig_shortcode TEXT;
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS origem_inclusao TEXT NOT NULL DEFAULT 'sync';
ALTER TABLE social_wiring.cs_virais ADD COLUMN IF NOT EXISTS incluido_por UUID;
DO $chk$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cs_virais_origem_inclusao_valida'
                   AND conrelid = 'social_wiring.cs_virais'::regclass) THEN
    ALTER TABLE social_wiring.cs_virais ADD CONSTRAINT cs_virais_origem_inclusao_valida
        CHECK (origem_inclusao IN ('sync', 'link_manual'));
  END IF;
END
$chk$;
COMMENT ON COLUMN social_wiring.cs_virais.ig_shortcode IS
    'Migration 351 - the Instagram shortcode of the post (globally unique): the dedupe key of the admin add-by-link. NULL on rows written before 351.';
COMMENT ON COLUMN social_wiring.cs_virais.origem_inclusao IS
    'Migration 351 - sync (scraped through a monitored profile) | link_manual (an admin pasted the post link).';
CREATE UNIQUE INDEX IF NOT EXISTS cs_virais_codigo_uq ON social_wiring.cs_virais (codigo);
CREATE UNIQUE INDEX IF NOT EXISTS cs_virais_ig_shortcode_uq
    ON social_wiring.cs_virais (ig_shortcode) WHERE ig_shortcode IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. cs_perfil_eventos (append-only, content-free)
-- ----------------------------------------------------------------------------
-- transition-log-ok: cs_perfil_eventos is a who/when/what ledger of admin writes on two entities (profile, video), not the history of one status column
CREATE TABLE IF NOT EXISTS social_wiring.cs_perfil_eventos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- NO FK on purpose: the history outlives the profile / video it describes (an opt-out purge deletes them)
    perfil_id   UUID NOT NULL,
    viral_id    UUID,
    handle      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN (
        'criado', 'editado', 'pausado', 'retomado', 'sincronizacao_solicitada', 'monitorar_ligado',
        'monitorar_desligado', 'excluido', 'optout_purgado', 'importado', 'video_adicionado_por_link',
        'pos_classificacao_falhou')),
    ator_id     UUID,
    ator_tipo   TEXT NOT NULL CHECK (ator_tipo IN ('admin', 'sistema', 'sistema_import')),
    -- the Estruturas load run that created / merged the profile (cs_estrutura_importacoes.id; no FK: history outlives it)
    importacao_id UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cs_perfil_eventos_perfil_idx ON social_wiring.cs_perfil_eventos (perfil_id, created_at);
CREATE INDEX IF NOT EXISTS cs_perfil_eventos_tipo_idx ON social_wiring.cs_perfil_eventos (tipo, created_at);
COMMENT ON TABLE social_wiring.cs_perfil_eventos IS
    'Migration 351 - append-only, content-free history of admin writes on library profiles and videos (who/when/what). tier:platform';

CREATE OR REPLACE FUNCTION social_wiring.cs_perfil_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'cs_perfil_eventos_imutavel: cs_perfil_eventos is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
DROP TRIGGER IF EXISTS cs_perfil_eventos_imutavel ON social_wiring.cs_perfil_eventos;
CREATE TRIGGER cs_perfil_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_perfil_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_perfil_eventos_imutavel();

-- Row triggers never fire on TRUNCATE: reuse the statement-level refusal of migration 350.
DROP TRIGGER IF EXISTS cs_perfil_eventos_no_truncate ON social_wiring.cs_perfil_eventos;
CREATE TRIGGER cs_perfil_eventos_no_truncate BEFORE TRUNCATE ON social_wiring.cs_perfil_eventos
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.cs_estruturas_recusa_truncate();

-- ----------------------------------------------------------------------------
-- 4. cs_estrutura_eventos.ator_tipo + 'sistema_retencao' (retention erases archived Estruturas of an unused profile)
-- ----------------------------------------------------------------------------
DO $ator$
DECLARE
  v_name text;
BEGIN
  SELECT c.conname INTO v_name
    FROM pg_constraint c
   WHERE c.conrelid = 'social_wiring.cs_estrutura_eventos'::regclass AND c.contype = 'c'
     AND pg_get_constraintdef(c.oid) LIKE '%ator_tipo%' AND pg_get_constraintdef(c.oid) NOT LIKE '%sistema_retencao%'
   LIMIT 1;
  IF v_name IS NOT NULL THEN
    EXECUTE format('ALTER TABLE social_wiring.cs_estrutura_eventos DROP CONSTRAINT %I', v_name);
    ALTER TABLE social_wiring.cs_estrutura_eventos ADD CONSTRAINT cs_estrutura_eventos_ator_tipo_valido
        CHECK (ator_tipo IN ('admin', 'sistema_import', 'sistema_ia', 'sistema_retencao'));
  END IF;
END
$ator$;

-- ----------------------------------------------------------------------------
-- 5. cs_perfil_purgar: ONE transaction for every profile erasure
-- ----------------------------------------------------------------------------
-- p_tipo: 'excluido' (admin delete / retention) | 'optout_purgado' (LGPD opt-out). A profile that still owns
-- Estruturas is refused (perfil_com_estruturas, count in DETAIL) unless p_apagar_estruturas -- the opt-out purge
-- always passes true. Every erased Estrutura leaves a content-free `excluida` event (it has no FK, so it outlives the
-- row); the profile's virais / Estruturas / blocks / references / uses go with it through the FK cascades.
CREATE OR REPLACE FUNCTION social_wiring.cs_perfil_purgar(
    p_perfil UUID, p_ator UUID, p_ator_tipo TEXT, p_tipo TEXT, p_apagar_estruturas BOOLEAN)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    p social_wiring.cs_perfis_monitorados;
    e record;
    v_ator_est TEXT;
    v_est INTEGER := 0;
    v_virais INTEGER := 0;
BEGIN
    IF p_tipo NOT IN ('excluido', 'optout_purgado') THEN
        RAISE EXCEPTION 'tipo_invalido';
    END IF;
    IF p_ator_tipo NOT IN ('admin', 'sistema') THEN
        RAISE EXCEPTION 'tipo_invalido';
    END IF;
    SELECT * INTO p FROM social_wiring.cs_perfis_monitorados WHERE id = p_perfil FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('perfil', false, 'estruturas', 0, 'virais', 0);
    END IF;
    SELECT count(*) INTO v_est FROM social_wiring.cs_estruturas WHERE perfil_id = p_perfil;
    IF v_est > 0 AND NOT COALESCE(p_apagar_estruturas, false) THEN
        RAISE EXCEPTION 'perfil_com_estruturas' USING DETAIL = v_est::text;
    END IF;
    v_ator_est := CASE WHEN p_ator_tipo = 'admin' THEN 'admin' ELSE 'sistema_retencao' END;
    FOR e IN SELECT id, versao FROM social_wiring.cs_estruturas WHERE perfil_id = p_perfil ORDER BY id LOOP
        PERFORM social_wiring.cs_estrutura_evento(e.id, p_perfil, 'excluida', NULL, NULL, NULL, p_ator, v_ator_est, NULL, e.versao);
    END LOOP;
    SELECT count(*) INTO v_virais FROM social_wiring.cs_virais WHERE perfil_id = p_perfil;
    INSERT INTO social_wiring.cs_perfil_eventos (perfil_id, handle, tipo, ator_id, ator_tipo)
    VALUES (p_perfil, p.handle, p_tipo, p_ator, p_ator_tipo);
    DELETE FROM social_wiring.cs_perfis_monitorados WHERE id = p_perfil;
    RETURN jsonb_build_object('perfil', true, 'estruturas', v_est, 'virais', v_virais);
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_perfil_purgar(UUID, UUID, TEXT, TEXT, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_perfil_purgar(UUID, UUID, TEXT, TEXT, BOOLEAN) TO service_role;
REVOKE ALL ON FUNCTION social_wiring.cs_perfil_eventos_imutavel() FROM PUBLIC, anon, authenticated;

-- ----------------------------------------------------------------------------
-- 5b. cs_perfil_plataforma_criar: the library profile the Estruturas LOAD (EST-3) creates, mutation + events in ONE call
-- ----------------------------------------------------------------------------
-- Idempotent on the normalised handle (platform row, org_id NULL): an existing profile is returned untouched
-- (`criado=false`, no event). A new one is library-only (monitorar=false, status 'aguardando') and gets `criado`
-- (+ `importado` when p_origem = 'import'), both carrying the load run id. The caller (the load) has already refused
-- opted-out handles. Handle shape is the table CHECK's.
CREATE OR REPLACE FUNCTION social_wiring.cs_perfil_plataforma_criar(
    p_handle TEXT, p_nome TEXT, p_origem TEXT, p_ator_tipo TEXT, p_ator UUID, p_importacao UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
DECLARE
    v_id UUID;
BEGIN
    IF p_origem NOT IN ('import', 'manual') OR p_ator_tipo NOT IN ('admin', 'sistema_import') THEN
        RAISE EXCEPTION 'tipo_invalido';
    END IF;
    SELECT id INTO v_id FROM social_wiring.cs_perfis_monitorados
     WHERE org_id IS NULL AND rede = 'instagram' AND handle = p_handle;
    IF FOUND THEN
        RETURN jsonb_build_object('id', v_id, 'handle', p_handle, 'criado', false);
    END IF;
    INSERT INTO social_wiring.cs_perfis_monitorados (org_id, rede, handle, nome, status, monitorar, created_by)
    VALUES (NULL, 'instagram', p_handle, NULLIF(btrim(p_nome), ''), 'aguardando', false, p_ator)
    RETURNING id INTO v_id;
    INSERT INTO social_wiring.cs_perfil_eventos (perfil_id, handle, tipo, ator_id, ator_tipo, importacao_id)
    VALUES (v_id, p_handle, 'criado', p_ator, p_ator_tipo, p_importacao);
    IF p_origem = 'import' THEN
        INSERT INTO social_wiring.cs_perfil_eventos (perfil_id, handle, tipo, ator_id, ator_tipo, importacao_id)
        VALUES (v_id, p_handle, 'importado', p_ator, p_ator_tipo, p_importacao);
    END IF;
    RETURN jsonb_build_object('id', v_id, 'handle', p_handle, 'criado', true);
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_perfil_plataforma_criar(TEXT, TEXT, TEXT, TEXT, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_perfil_plataforma_criar(TEXT, TEXT, TEXT, TEXT, UUID, UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- 6. Tiers, grants, policies: the library tables have NO browser grant and NO browser policy (service role only)
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS "cs_perfis_monitorados_select_own_org" ON social_wiring.cs_perfis_monitorados;
DROP POLICY IF EXISTS "cs_virais_select_own_org" ON social_wiring.cs_virais;
REVOKE ALL ON TABLE social_wiring.cs_perfis_monitorados FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE social_wiring.cs_virais FROM PUBLIC, anon, authenticated;

ALTER TABLE social_wiring.cs_perfil_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_perfil_eventos_service_role" ON social_wiring.cs_perfil_eventos;
CREATE POLICY "cs_perfil_eventos_service_role" ON social_wiring.cs_perfil_eventos FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_perfil_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.cs_perfil_eventos TO service_role;

COMMENT ON TABLE social_wiring.cs_perfis_monitorados IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_virais IS 'tier:platform';
COMMENT ON TABLE social_wiring.cs_perfil_eventos IS 'tier:platform';
