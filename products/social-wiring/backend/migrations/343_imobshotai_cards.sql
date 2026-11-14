-- ============================================================================
-- Migration 343 · social_wiring: ImobShotAI cards (one per imóvel), their append-only event ledger,
-- the lote -> card link and the four page-visibility rows.
-- ============================================================================
-- CONTRACT products/social-wiring/IMOBSHOTAI-CONTRACT.md §1-§8 (owner "go" 2026-11-14).
--
--   * imobshot_cards: ONE row per (org_id, imovel_codigo). `etapa` is a PROJECTION of the card's lotes and photos
--     (contract §6), never set by hand: only imobshot_aplicar_etapa() writes it.
--   * imobshot_eventos: APPEND-ONLY ledger (card_criado | lote_vinculado | etapa_mudou | card_arquivado). The state
--     change and its event are ONE function call = ONE transaction, so no code path can change a card without the event.
--   * fotos_lotes.card_id: nullable FK + index. A lote with a card_id is an ImobShotAI lote (decisions admin-only, D6).
--   * three SERVICE-ONLY functions (REVOKE browser roles): obter_ou_criar_card, vincular_lote, aplicar_etapa.
--   * the 4 status_pagina rows (contract §8).
--
-- Backward compatible with the previous image: only ADDS objects and one nullable column.
-- FORWARD-ONLY, IDEMPOTENT. NOT applied by the author.
-- ============================================================================

SET search_path = social_wiring, public;
SET lock_timeout = '5s';

-- ----------------------------------------------------------------------------
-- 1. imobshot_cards
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.imobshot_cards (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    imovel_codigo       TEXT NOT NULL,
    etapa               TEXT NOT NULL DEFAULT 'fotos_enviadas' CHECK (etapa IN (
        'fotos_enviadas', 'fotos_em_edicao', 'fotos_em_revisao', 'fotos_aprovadas',
        'video_em_montagem', 'video_renderizando', 'video_em_revisao', 'concluido', 'arquivado')),
    etapa_desde         TIMESTAMPTZ NOT NULL DEFAULT now(),
    fotos_concluidas_at TIMESTAMPTZ,
    capa_foto_id        UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_imobshot_cards_org_codigo UNIQUE (org_id, imovel_codigo)
);

CREATE INDEX IF NOT EXISTS ix_imobshot_cards_org_etapa ON social_wiring.imobshot_cards (org_id, etapa);
CREATE INDEX IF NOT EXISTS ix_imobshot_cards_org_updated ON social_wiring.imobshot_cards (org_id, updated_at DESC);

CREATE OR REPLACE FUNCTION social_wiring.imobshot_cards_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_updated_at_imobshot_cards ON social_wiring.imobshot_cards;
CREATE TRIGGER set_updated_at_imobshot_cards
    BEFORE UPDATE ON social_wiring.imobshot_cards
    FOR EACH ROW EXECUTE FUNCTION social_wiring.imobshot_cards_touch_updated_at();

-- ----------------------------------------------------------------------------
-- 1b. fotos_lotes.card_id (before the cards policy below, which reads it)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.fotos_lotes
    ADD COLUMN IF NOT EXISTS card_id UUID REFERENCES social_wiring.imobshot_cards (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_fotos_lotes_card ON social_wiring.fotos_lotes (card_id) WHERE card_id IS NOT NULL;

COMMENT ON COLUMN social_wiring.fotos_lotes.card_id IS
    'ImobShotAI card this lote belongs to (NULL = plain Edição de Imagem lote). Photo decisions on a card lote are admin-only (D6). Migration 343.';

ALTER TABLE social_wiring.imobshot_cards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imobshot_cards_select_visivel" ON social_wiring.imobshot_cards;
CREATE POLICY "imobshot_cards_select_visivel" ON social_wiring.imobshot_cards
    FOR SELECT TO authenticated
    USING (
        org_id = (SELECT public.current_org_id_for('social_wiring'))
        AND (
            public.is_platform_admin()
            OR public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager'])
            OR EXISTS (
                SELECT 1 FROM social_wiring.fotos_lotes l
                WHERE l.card_id = imobshot_cards.id AND l.criado_por = (SELECT auth.uid())
            )
        )
    );

DROP POLICY IF EXISTS "service_role_bypass" ON social_wiring.imobshot_cards;
CREATE POLICY "service_role_bypass" ON social_wiring.imobshot_cards
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Browser: read only (RLS above); every write goes through the service-only functions below.
REVOKE ALL ON TABLE social_wiring.imobshot_cards FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE social_wiring.imobshot_cards TO authenticated;
GRANT ALL ON TABLE social_wiring.imobshot_cards TO service_role;

COMMENT ON TABLE social_wiring.imobshot_cards IS 'tier:org';
COMMENT ON COLUMN social_wiring.imobshot_cards.etapa IS
    'Projection of the card''s lotes/photos (contract §6). Written ONLY by imobshot_aplicar_etapa(). Migration 343.';
COMMENT ON COLUMN social_wiring.imobshot_cards.fotos_concluidas_at IS
    'When the card last entered fotos_aprovadas (time-to-approval metric). Migration 343.';

-- ----------------------------------------------------------------------------
-- 2. imobshot_eventos -- append-only
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.imobshot_eventos (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL,
    card_id    UUID NOT NULL REFERENCES social_wiring.imobshot_cards (id) ON DELETE CASCADE,
    tipo       TEXT NOT NULL CHECK (tipo IN ('card_criado', 'lote_vinculado', 'etapa_mudou', 'card_arquivado')),
    etapa_de   TEXT,
    etapa_para TEXT,
    actor_id   UUID,
    at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    detalhe    JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_imobshot_eventos_card ON social_wiring.imobshot_eventos (card_id, at DESC);
CREATE INDEX IF NOT EXISTS ix_imobshot_eventos_org_tipo ON social_wiring.imobshot_eventos (org_id, tipo, at);

CREATE OR REPLACE FUNCTION social_wiring.imobshot_eventos_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'imobshot_eventos is append-only (% refused)', TG_OP USING ERRCODE = '42501';
END;
$$;

CREATE OR REPLACE TRIGGER imobshot_eventos_no_update
    BEFORE UPDATE OR DELETE ON social_wiring.imobshot_eventos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.imobshot_eventos_append_only();

ALTER TABLE social_wiring.imobshot_eventos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "imobshot_eventos_service_role" ON social_wiring.imobshot_eventos;
CREATE POLICY "imobshot_eventos_service_role" ON social_wiring.imobshot_eventos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.imobshot_eventos FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.imobshot_eventos TO service_role;

COMMENT ON TABLE social_wiring.imobshot_eventos IS 'tier:org';

-- ----------------------------------------------------------------------------
-- 4. The three atomic writes (SERVICE-ONLY)
-- ----------------------------------------------------------------------------

-- Get-or-create the card of an imóvel; the event rides the same transaction. Returns {id, criado}.
CREATE OR REPLACE FUNCTION social_wiring.imobshot_obter_ou_criar_card(p_org UUID, p_codigo TEXT, p_ator UUID)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO social_wiring.imobshot_cards (org_id, imovel_codigo)
    VALUES (p_org, p_codigo)
    ON CONFLICT (org_id, imovel_codigo) DO NOTHING
    RETURNING id INTO v_id;

    IF v_id IS NOT NULL THEN
        INSERT INTO social_wiring.imobshot_eventos (org_id, card_id, tipo, etapa_para, actor_id)
        VALUES (p_org, v_id, 'card_criado', 'fotos_enviadas', p_ator);
        RETURN jsonb_build_object('id', v_id, 'criado', true);
    END IF;

    SELECT id INTO v_id FROM social_wiring.imobshot_cards WHERE org_id = p_org AND imovel_codigo = p_codigo;
    RETURN jsonb_build_object('id', v_id, 'criado', false);
END;
$$;

-- Link a lote to a card (same org only) + the lote_vinculado event. Returns whether the link was written.
CREATE OR REPLACE FUNCTION social_wiring.imobshot_vincular_lote(p_card UUID, p_lote UUID, p_ator UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $$
DECLARE
    v_org UUID;
    v_n   INTEGER;
BEGIN
    SELECT org_id INTO v_org FROM social_wiring.imobshot_cards WHERE id = p_card;
    IF v_org IS NULL THEN
        RETURN false;
    END IF;
    UPDATE social_wiring.fotos_lotes SET card_id = p_card, updated_at = now()
     WHERE id = p_lote AND org_id = v_org AND card_id IS DISTINCT FROM p_card;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n = 0 THEN
        RETURN false;
    END IF;
    INSERT INTO social_wiring.imobshot_eventos (org_id, card_id, tipo, actor_id, detalhe)
    VALUES (v_org, p_card, 'lote_vinculado', p_ator, jsonb_build_object('lote_id', p_lote));
    RETURN true;
END;
$$;

-- Apply a recomputed etapa (+ the cover). Writes ONLY when it changed, and then the etapa_mudou event in the same
-- transaction. The row is locked, so two concurrent syncs cannot both write the same transition. Returns whether it changed.
CREATE OR REPLACE FUNCTION social_wiring.imobshot_aplicar_etapa(p_card UUID, p_etapa TEXT, p_capa UUID, p_ator UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SET search_path = social_wiring, public
AS $$
DECLARE
    v_org   UUID;
    v_atual TEXT;
BEGIN
    SELECT org_id, etapa INTO v_org, v_atual
      FROM social_wiring.imobshot_cards WHERE id = p_card FOR UPDATE;
    IF v_org IS NULL THEN
        RETURN false;
    END IF;

    UPDATE social_wiring.imobshot_cards SET capa_foto_id = p_capa
     WHERE id = p_card AND capa_foto_id IS DISTINCT FROM p_capa;

    IF v_atual = p_etapa THEN
        RETURN false;
    END IF;

    UPDATE social_wiring.imobshot_cards
       SET etapa = p_etapa,
           etapa_desde = now(),
           fotos_concluidas_at = CASE WHEN p_etapa = 'fotos_aprovadas' THEN now() ELSE fotos_concluidas_at END
     WHERE id = p_card;
    INSERT INTO social_wiring.imobshot_eventos (org_id, card_id, tipo, etapa_de, etapa_para, actor_id)
    VALUES (v_org, p_card, 'etapa_mudou', v_atual, p_etapa, p_ator);
    RETURN true;
END;
$$;

REVOKE EXECUTE ON FUNCTION social_wiring.imobshot_obter_ou_criar_card(UUID, TEXT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION social_wiring.imobshot_vincular_lote(UUID, UUID, UUID) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION social_wiring.imobshot_aplicar_etapa(UUID, TEXT, UUID, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.imobshot_obter_ou_criar_card(UUID, TEXT, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.imobshot_vincular_lote(UUID, UUID, UUID) TO service_role;
GRANT EXECUTE ON FUNCTION social_wiring.imobshot_aplicar_etapa(UUID, TEXT, UUID, UUID) TO service_role;

-- ----------------------------------------------------------------------------
-- 5. Page visibility (contract §8)
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('imobshotai',             'producao'),
    ('imobshotai-fotos-novo',  'producao'),
    ('imobshotai-card',        'producao'),
    ('imobshotai-video-novo',  'desenvolvimento')
ON CONFLICT (nome_pagina) DO UPDATE SET status = EXCLUDED.status;
