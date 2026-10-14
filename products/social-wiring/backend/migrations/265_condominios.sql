-- 265 -- condominios (master list) + condominio_aliases + condominio_eventos
--        + condominio_imoveis (resolution view) + status_pagina 'condominios'.
--
-- WHY: the price evaluator needs LOCATION, and in Granja Viana which
-- condomínio an imóvel sits in is the #1 price driver. No master list exists;
-- `imoveis.empreendimento` is free text from Vista (428 distinct upper(btrim)
-- spellings over ~1,900 rows, with variants/duplicates). Owner decision: build
-- the list FROM that data (POST /api/condominios/sugerir), let the owner refine
-- and VALIDATE it in the "Condominios" page -- which then IS the source of truth.
--
-- SHAPE
--   condominios         one row per real-world condomínio. `status_validacao`:
--                       sugerido (machine) | validado (owner) | descartado
--                       (not a condomínio / merged away). A re-suggest run never
--                       touches a validado row.
--   condominio_aliases  every raw empreendimento SPELLING -> one condomínio.
--                       `alias_normalizado` = upper(btrim()) with whitespace
--                       collapsed (the SAME key the view and condominios/
--                       normalizacao.py compute). Merging = re-pointing aliases.
--   condominio_eventos  append-only audit (trigger refuses UPDATE/DELETE).
--   condominio_imoveis  VIEW: imóvel -> condomínio. Reads imovel_dados.
--                       empreendimento_manual (manual wins, migration 158) over
--                       the Vista mirror's imoveis.empreendimento. READ-ONLY on
--                       the mirror; nothing here writes imoveis.
--
-- VISIBILITY: status_pagina 'producao'. Writes are gated in the API (admin for
-- merge/validate/discard/rename/alias changes/suggest), not by showing/hiding
-- the page. See KB PATTERNS/frontend/status-pagina-dev-visibility.md.
--
-- Forward-only + idempotent. PREREQUISITES: 040, 075/158 (imovel_dados), 036;
-- core 070 (current_org_id_for).

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.condominios (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID        NOT NULL,
    nome             TEXT        NOT NULL,
    -- Matching key (accents/prefixes stripped). Unique per org AND cidade: two
    -- cities may each have a "Vila Verde".
    nome_normalizado TEXT        NOT NULL,
    cidade           TEXT,
    bairro           TEXT,
    tipo             TEXT,
    status_validacao TEXT        NOT NULL DEFAULT 'sugerido',
    -- Centroid of the member imoveis that carry lat/long. Nullable.
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    -- Typed attribute set (first cut -- add columns as the evaluator asks).
    seguranca_nivel  SMALLINT,
    portaria_24h     BOOLEAN,
    area_lazer       TEXT,
    distancia_raposo_km NUMERIC(6, 2),
    acesso_principal TEXT,
    observacoes      TEXT,
    -- Set when this row was merged into another (reversible: the merge event
    -- lists the aliases that moved).
    fundido_em_id    UUID        REFERENCES social_wiring.condominios (id),
    validado_por     UUID,
    validado_em      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT condominios_tipo_check
        CHECK (tipo IS NULL OR tipo IN ('horizontal', 'vertical', 'loteamento', 'misto')),
    CONSTRAINT condominios_status_check
        CHECK (status_validacao IN ('sugerido', 'validado', 'descartado')),
    CONSTRAINT condominios_seguranca_check
        CHECK (seguranca_nivel IS NULL OR seguranca_nivel BETWEEN 1 AND 5),
    CONSTRAINT condominios_distancia_check
        CHECK (distancia_raposo_km IS NULL OR distancia_raposo_km >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_condominios_org_nome_cidade
    ON social_wiring.condominios (org_id, nome_normalizado, COALESCE(cidade, ''));
CREATE INDEX IF NOT EXISTS idx_sw_condominios_org_status
    ON social_wiring.condominios (org_id, status_validacao);

CREATE TABLE IF NOT EXISTS social_wiring.condominio_aliases (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID        NOT NULL,
    condominio_id    UUID        NOT NULL REFERENCES social_wiring.condominios (id) ON DELETE CASCADE,
    -- The raw spelling as first seen / typed.
    alias            TEXT        NOT NULL,
    -- upper(btrim(alias)) with runs of whitespace collapsed. THE join key.
    alias_normalizado TEXT       NOT NULL,
    origem           TEXT        NOT NULL DEFAULT 'sugestao',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT condominio_aliases_origem_check
        CHECK (origem IN ('sugestao', 'manual', 'fusao')),
    CONSTRAINT condominio_aliases_unico UNIQUE (org_id, alias_normalizado)
);

CREATE INDEX IF NOT EXISTS idx_sw_condominio_aliases_condominio
    ON social_wiring.condominio_aliases (condominio_id);

CREATE TABLE IF NOT EXISTS social_wiring.condominio_eventos (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID        NOT NULL,
    condominio_id    UUID        NOT NULL REFERENCES social_wiring.condominios (id),
    tipo             TEXT        NOT NULL,
    ator             UUID,
    detalhes         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT condominio_eventos_tipo_check
        CHECK (tipo IN ('sugerido', 'merge', 'desfazer_merge', 'rename', 'validate',
                        'discard', 'reabrir', 'update', 'alias_add', 'alias_remove'))
);

CREATE INDEX IF NOT EXISTS idx_sw_condominio_eventos_condominio
    ON social_wiring.condominio_eventos (condominio_id, created_at DESC);

-- Append-only: the audit trail is the point of the merge/validate actions.
CREATE OR REPLACE FUNCTION social_wiring.condominio_eventos_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    RAISE EXCEPTION 'condominio_eventos is append-only (% refused)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_condominio_eventos_append_only ON social_wiring.condominio_eventos;
CREATE TRIGGER trg_condominio_eventos_append_only
    BEFORE UPDATE OR DELETE ON social_wiring.condominio_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.condominio_eventos_append_only();

CREATE OR REPLACE FUNCTION social_wiring.touch_condominios_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_condominios_updated_at ON social_wiring.condominios;
CREATE TRIGGER trg_condominios_updated_at
    BEFORE UPDATE ON social_wiring.condominios
    FOR EACH ROW EXECUTE FUNCTION social_wiring.touch_condominios_updated_at();

-- ── RLS: org members READ; every write goes through the API (admin client)
ALTER TABLE social_wiring.condominios ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.condominio_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.condominio_eventos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "condominios_select_own_org" ON social_wiring.condominios;
CREATE POLICY "condominios_select_own_org" ON social_wiring.condominios
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "condominios_service_role" ON social_wiring.condominios;
CREATE POLICY "condominios_service_role" ON social_wiring.condominios
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "condominio_aliases_select_own_org" ON social_wiring.condominio_aliases;
CREATE POLICY "condominio_aliases_select_own_org" ON social_wiring.condominio_aliases
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "condominio_aliases_service_role" ON social_wiring.condominio_aliases;
CREATE POLICY "condominio_aliases_service_role" ON social_wiring.condominio_aliases
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "condominio_eventos_select_own_org" ON social_wiring.condominio_eventos;
CREATE POLICY "condominio_eventos_select_own_org" ON social_wiring.condominio_eventos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));
DROP POLICY IF EXISTS "condominio_eventos_service_role" ON social_wiring.condominio_eventos;
CREATE POLICY "condominio_eventos_service_role" ON social_wiring.condominio_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.condominios FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.condominio_aliases FROM anon, authenticated;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.condominio_eventos FROM anon, authenticated;

COMMENT ON TABLE social_wiring.condominios IS
    'Condomínio master list (migration 265): suggested from Vista empreendimento '
    'spellings, validated by the owner. The permanent source of truth for the '
    'price evaluator''s location driver.';

-- ── Resolution view: imóvel -> condomínio via alias ──────────────────────
-- Same key as the app: upper(btrim) + collapsed whitespace; manual wins.
-- security_invoker so the caller's RLS applies to every table it reads.
CREATE OR REPLACE VIEW social_wiring.condominio_imoveis
WITH (security_invoker = true) AS
SELECT i.org_id,
       i.codigo_norm AS codigo_canonical,
       a.condominio_id,
       a.alias_normalizado
  FROM social_wiring.imoveis i
  LEFT JOIN social_wiring.imovel_dados d
         ON d.org_id = i.org_id AND d.codigo = i.codigo
  JOIN social_wiring.condominio_aliases a
         ON a.org_id = i.org_id
        AND a.alias_normalizado = upper(regexp_replace(btrim(
                COALESCE(NULLIF(btrim(d.empreendimento_manual), ''), i.empreendimento)
            ), '\s+', ' ', 'g'));

-- ── Nav gating ────────────────────────────────────────────────────────────
-- 'producao' so the owner (who must validate the list) sees it; see the header.
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('condominios', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
