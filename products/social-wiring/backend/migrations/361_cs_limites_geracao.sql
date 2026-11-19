-- ============================================================================
-- Migration 361 · social_wiring: per-org daily generation limits, editable in Configurações (geracao-contract §9.4.1)
-- ============================================================================
-- WHY
-- ---
-- Owner ask 2026-11-18: the six daily caps of the generation module (headlines, sugestões, roteiros, legendas,
-- chat per person, chat per org) were fixed in app/config.py. Each org may now override them, within a platform
-- ceiling, from Configurações -> Limites diários.
--
--   * The override VALUE lives where every other per-org setting already lives: the seed chain
--     public.org_settings -> public.platform_settings -> env (noctusai_lib.config.credentials.resolve_credential).
--     No new settings table.
--   * cs_limite_geracao_eventos  -- append-only ledger: who changed which limit, from what, to what, when.
--   * cs_limite_geracao_definir  -- THE write: locks the org's org_settings row, upserts (or deletes on reset) it and
--                                   appends the event in the SAME transaction. service_role only.
--
-- The ceiling (10 x the code default) is enforced by the API (422 before any write); the SQL enforces the floor
-- (>= 1, never "unlimited", never 0) and the closed key list as the backstop.
--
-- Records -> metrics (measurement-by-design): overrides per org and key; raise ratio (valor_novo / default); time
-- from a 429 limite_* refusal to a raise; how often a raised limit is later restored.
--
-- Backward compatible with the previous image (N-1): additive only; the N-1 image never calls the function and
-- keeps reading its env defaults. FORWARD-ONLY, IDEMPOTENT. NOT applied by the author.
-- ============================================================================

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regclass('public.org_settings') IS NULL OR to_regclass('public.organizations') IS NULL THEN
    RAISE EXCEPTION 'Migration 361 requires public.org_settings / public.organizations (core 002)';
  END IF;
END
$guard$;

-- ----------------------------------------------------------------------------
-- 1. cs_limite_geracao_eventos (append-only)
-- ----------------------------------------------------------------------------
-- transition-log-ok: cs_limite_geracao_eventos a config-change ledger whose state row is the core-owned key/value public.org_settings (created and deleted, not transitioned), outside this schema
CREATE TABLE IF NOT EXISTS social_wiring.cs_limite_geracao_eventos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
    chave          TEXT NOT NULL CONSTRAINT cs_limite_geracao_eventos_chave_check CHECK (chave IN (
        'headline_lotes_dia_usuario', 'headlines_sugeridas_por_dia_marca', 'roteiros_dia_usuario',
        'legendas_dia_usuario', 'chat_mensagens_dia_usuario', 'chat_mensagens_dia_org')),
    evento         TEXT NOT NULL CONSTRAINT cs_limite_geracao_eventos_evento_check
        CHECK (evento IN ('limite_definido', 'limite_restaurado')),
    -- NULL = the org had no override (the default applied)
    valor_anterior INTEGER,
    -- NULL = restored to the default
    valor_novo     INTEGER CONSTRAINT cs_limite_geracao_eventos_valor_novo_check CHECK (valor_novo IS NULL OR valor_novo >= 1),
    -- NULL = the system acted
    ator_id        UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_limite_geracao_eventos_forma_check CHECK (
        (evento = 'limite_definido' AND valor_novo IS NOT NULL)
        OR (evento = 'limite_restaurado' AND valor_novo IS NULL AND valor_anterior IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS cs_limite_geracao_eventos_org_idx
    ON social_wiring.cs_limite_geracao_eventos (org_id, chave, created_at);

ALTER TABLE social_wiring.cs_limite_geracao_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.cs_limite_geracao_eventos;
CREATE POLICY "service_role_bypass" ON social_wiring.cs_limite_geracao_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON social_wiring.cs_limite_geracao_eventos FROM PUBLIC, anon, authenticated;
GRANT ALL ON social_wiring.cs_limite_geracao_eventos TO service_role;
COMMENT ON TABLE social_wiring.cs_limite_geracao_eventos IS 'tier:org';

-- append-only: UPDATE/DELETE refused for everybody; only a DB-driven ON DELETE CASCADE (org erase, depth > 1) may
-- remove a row (the carve-out cs_fluxo_eventos has).
CREATE OR REPLACE FUNCTION social_wiring.cs_limite_geracao_eventos_imutavel()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'cs_limite_geracao_eventos_imutavel: cs_limite_geracao_eventos is append-only (% refused)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_limite_geracao_eventos_imutavel() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS cs_limite_geracao_eventos_imutavel ON social_wiring.cs_limite_geracao_eventos;
CREATE TRIGGER cs_limite_geracao_eventos_imutavel
    BEFORE UPDATE OR DELETE ON social_wiring.cs_limite_geracao_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.cs_limite_geracao_eventos_imutavel();

CREATE OR REPLACE FUNCTION social_wiring.cs_limite_geracao_recusa_truncate()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION 'cs_limite_geracao_recusa_truncate: % is append-only (TRUNCATE refused)', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_limite_geracao_recusa_truncate() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS cs_limite_geracao_eventos_no_truncate ON social_wiring.cs_limite_geracao_eventos;
CREATE TRIGGER cs_limite_geracao_eventos_no_truncate BEFORE TRUNCATE ON social_wiring.cs_limite_geracao_eventos
    FOR EACH STATEMENT EXECUTE FUNCTION social_wiring.cs_limite_geracao_recusa_truncate();

-- ----------------------------------------------------------------------------
-- 2. cs_limite_geracao_definir: the one write (override + event, one transaction)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.cs_limite_geracao_definir(
    p_org UUID, p_chave TEXT, p_valor INTEGER, p_ator UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    v_texto    TEXT;
    v_anterior INTEGER;
BEGIN
    IF p_org IS NULL THEN
        RAISE EXCEPTION 'cs_limite_geracao_definir: org obrigatoria' USING ERRCODE = '22023';
    END IF;
    IF p_chave IS NULL OR p_chave NOT IN (
        'headline_lotes_dia_usuario', 'headlines_sugeridas_por_dia_marca', 'roteiros_dia_usuario',
        'legendas_dia_usuario', 'chat_mensagens_dia_usuario', 'chat_mensagens_dia_org') THEN
        RAISE EXCEPTION 'cs_limite_geracao_definir: chave desconhecida' USING ERRCODE = '22023';
    END IF;
    IF p_valor IS NOT NULL AND p_valor < 1 THEN
        RAISE EXCEPTION 'cs_limite_geracao_definir: valor deve ser >= 1' USING ERRCODE = '22023';
    END IF;

    -- Serialize concurrent writers of this (org, key) even when no row exists yet.
    PERFORM pg_advisory_xact_lock(hashtextextended('cs_limite_geracao:' || p_org::text || ':' || p_chave, 0));

    SELECT value INTO v_texto FROM public.org_settings
     WHERE org_id = p_org AND key = p_chave
     FOR UPDATE;
    -- A stored value that is not a sane integer counts as "no override" (the resolver skips it too).
    v_anterior := CASE WHEN v_texto ~ '^[0-9]{1,9}$' AND v_texto::INTEGER >= 1 THEN v_texto::INTEGER END;

    IF p_valor IS NULL THEN
        DELETE FROM public.org_settings WHERE org_id = p_org AND key = p_chave;
    ELSE
        INSERT INTO public.org_settings (org_id, key, value, is_secret, updated_at)
        VALUES (p_org, p_chave, p_valor::TEXT, false, now())
        ON CONFLICT (org_id, key) DO UPDATE SET value = EXCLUDED.value, is_secret = false, updated_at = now();
    END IF;

    IF v_anterior IS DISTINCT FROM p_valor THEN
        INSERT INTO social_wiring.cs_limite_geracao_eventos (org_id, chave, evento, valor_anterior, valor_novo, ator_id)
        VALUES (p_org, p_chave, CASE WHEN p_valor IS NULL THEN 'limite_restaurado' ELSE 'limite_definido' END,
                v_anterior, p_valor, p_ator);
    END IF;

    RETURN jsonb_build_object('anterior', v_anterior, 'novo', p_valor, 'mudou', v_anterior IS DISTINCT FROM p_valor);
END;
$fn$;
REVOKE ALL ON FUNCTION social_wiring.cs_limite_geracao_definir(UUID, TEXT, INTEGER, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_limite_geracao_definir(UUID, TEXT, INTEGER, UUID) TO service_role;
COMMENT ON FUNCTION social_wiring.cs_limite_geracao_definir(UUID, TEXT, INTEGER, UUID) IS
    'tier:org - service_role only. Sets (p_valor) or restores (NULL) one daily generation limit of an org and '
    'appends cs_limite_geracao_eventos in the same transaction (geracao-contract 9.4.1).';
