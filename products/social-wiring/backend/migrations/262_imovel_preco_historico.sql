-- 262 -- imovel_preco_historico (append-only asking-price history) +
--        atendimentos.motivo_perda.
--
-- WHY: Vista exposes no price history and no sold data (probed 2026-10-14),
-- and the daily sync upserts `imoveis` on (org_id, codigo), OVERWRITING
-- valor_venda / valor_locacao -- every asking-price change was lost. The
-- owner's price evaluator needs that series, so we start recording now.
--
-- CAPTURE: a DB trigger, not service code. It sees every write path (sync,
-- backfills, manual edits), costs no extra round-trip per row, and survives
-- any future rewrite of ImovelSyncService. An UPDATE row is written only when
-- a price is IS DISTINCT FROM its old value, so the nightly re-upsert of an
-- unchanged catalog writes nothing.
--
-- KEY: `codigo_canonical` (= imoveis.codigo_norm = upper(btrim(codigo))), the
-- column imovel_registry / imovel_captacao join on (migrations 062/063/226) --
-- the mirror's own `codigo` is case-unstable and the mirror is disposable.
--
-- Also: `atendimentos.motivo_perda` -- PerderRequest.motivo was accepted by
-- POST /atendimentos-venda/{id}/perder and silently dropped.
--
-- Forward-only + idempotent. PREREQUISITES: 040, 062, 063, 226; core 070.

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_preco_historico (
    id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID          NOT NULL,
    codigo_canonical       TEXT          NOT NULL,
    valor_venda_anterior   NUMERIC(14, 2),
    valor_venda_novo       NUMERIC(14, 2),
    valor_locacao_anterior NUMERIC(14, 2),
    valor_locacao_novo     NUMERIC(14, 2),
    -- 'primeira_observacao' = the first ask we ever saw for this imóvel
    -- (INSERT, or the migration-time baseline); 'alteracao' = a later change.
    evento                 TEXT          NOT NULL DEFAULT 'alteracao',
    -- Where the write came from: 'vista_sync' (mirror) | 'manual'
    -- (imovel_captacao) | 'baseline' (this migration's backfill).
    fonte                  TEXT          NOT NULL,
    observado_em           TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_preco_hist_org_codigo_obs
    ON social_wiring.imovel_preco_historico (org_id, codigo_canonical, observado_em DESC);

ALTER TABLE social_wiring.imovel_preco_historico ENABLE ROW LEVEL SECURITY;

-- Org members READ; there is deliberately no authenticated write policy --
-- rows come only from the SECURITY DEFINER trigger functions below.
DROP POLICY IF EXISTS "imovel_preco_historico_select_own_org" ON social_wiring.imovel_preco_historico;
CREATE POLICY "imovel_preco_historico_select_own_org"
    ON social_wiring.imovel_preco_historico
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_preco_historico_service_role" ON social_wiring.imovel_preco_historico;
CREATE POLICY "imovel_preco_historico_service_role"
    ON social_wiring.imovel_preco_historico
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.imovel_preco_historico FROM anon, authenticated;

COMMENT ON TABLE social_wiring.imovel_preco_historico IS
    'Append-only asking-price history per imóvel (Vista exposes none). Written '
    'only by the trg_*_preco_historico triggers on imoveis / imovel_captacao.';

-- ── Trigger function: Vista mirror (imoveis) ────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.registrar_preco_historico_imoveis()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.valor_venda IS NULL AND NEW.valor_locacao IS NULL THEN
            RETURN NEW;
        END IF;
        INSERT INTO social_wiring.imovel_preco_historico (
            org_id, codigo_canonical, valor_venda_novo, valor_locacao_novo,
            evento, fonte
        ) VALUES (
            NEW.org_id, NEW.codigo_norm, NEW.valor_venda, NEW.valor_locacao,
            'primeira_observacao', 'vista_sync'
        );
    ELSE
        INSERT INTO social_wiring.imovel_preco_historico (
            org_id, codigo_canonical,
            valor_venda_anterior, valor_venda_novo,
            valor_locacao_anterior, valor_locacao_novo,
            evento, fonte
        ) VALUES (
            NEW.org_id, NEW.codigo_norm,
            OLD.valor_venda, NEW.valor_venda,
            OLD.valor_locacao, NEW.valor_locacao,
            'alteracao', 'vista_sync'
        );
    END IF;
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION social_wiring.registrar_preco_historico_imoveis() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_imoveis_preco_historico_ins ON social_wiring.imoveis;
CREATE TRIGGER trg_imoveis_preco_historico_ins
    AFTER INSERT ON social_wiring.imoveis
    FOR EACH ROW EXECUTE FUNCTION social_wiring.registrar_preco_historico_imoveis();

DROP TRIGGER IF EXISTS trg_imoveis_preco_historico_upd ON social_wiring.imoveis;
CREATE TRIGGER trg_imoveis_preco_historico_upd
    AFTER UPDATE OF valor_venda, valor_locacao ON social_wiring.imoveis
    FOR EACH ROW
    WHEN (OLD.valor_venda   IS DISTINCT FROM NEW.valor_venda
       OR OLD.valor_locacao IS DISTINCT FROM NEW.valor_locacao)
    EXECUTE FUNCTION social_wiring.registrar_preco_historico_imoveis();

-- ── Trigger function: manual imóveis (imovel_captacao) ──────────────────
CREATE OR REPLACE FUNCTION social_wiring.registrar_preco_historico_captacao()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.valor_venda IS NULL AND NEW.valor_locacao IS NULL THEN
            RETURN NEW;
        END IF;
        INSERT INTO social_wiring.imovel_preco_historico (
            org_id, codigo_canonical, valor_venda_novo, valor_locacao_novo,
            evento, fonte
        ) VALUES (
            NEW.org_id, NEW.codigo_canonical, NEW.valor_venda, NEW.valor_locacao,
            'primeira_observacao', 'manual'
        );
    ELSE
        INSERT INTO social_wiring.imovel_preco_historico (
            org_id, codigo_canonical,
            valor_venda_anterior, valor_venda_novo,
            valor_locacao_anterior, valor_locacao_novo,
            evento, fonte
        ) VALUES (
            NEW.org_id, NEW.codigo_canonical,
            OLD.valor_venda, NEW.valor_venda,
            OLD.valor_locacao, NEW.valor_locacao,
            'alteracao', 'manual'
        );
    END IF;
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION social_wiring.registrar_preco_historico_captacao() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_captacao_preco_historico_ins ON social_wiring.imovel_captacao;
CREATE TRIGGER trg_captacao_preco_historico_ins
    AFTER INSERT ON social_wiring.imovel_captacao
    FOR EACH ROW EXECUTE FUNCTION social_wiring.registrar_preco_historico_captacao();

DROP TRIGGER IF EXISTS trg_captacao_preco_historico_upd ON social_wiring.imovel_captacao;
CREATE TRIGGER trg_captacao_preco_historico_upd
    AFTER UPDATE OF valor_venda, valor_locacao ON social_wiring.imovel_captacao
    FOR EACH ROW
    WHEN (OLD.valor_venda   IS DISTINCT FROM NEW.valor_venda
       OR OLD.valor_locacao IS DISTINCT FROM NEW.valor_locacao)
    EXECUTE FUNCTION social_wiring.registrar_preco_historico_captacao();

-- ── Backfill: one baseline row per existing priced imóvel ───────────────
-- Guarded so a re-run does not duplicate the baseline.
INSERT INTO social_wiring.imovel_preco_historico (
    org_id, codigo_canonical, valor_venda_novo, valor_locacao_novo,
    evento, fonte
)
SELECT i.org_id, i.codigo_norm, i.valor_venda, i.valor_locacao,
       'primeira_observacao', 'baseline'
  FROM social_wiring.imoveis i
 WHERE (i.valor_venda IS NOT NULL OR i.valor_locacao IS NOT NULL)
   AND NOT EXISTS (
       SELECT 1 FROM social_wiring.imovel_preco_historico h
        WHERE h.org_id = i.org_id AND h.codigo_canonical = i.codigo_norm
   );

INSERT INTO social_wiring.imovel_preco_historico (
    org_id, codigo_canonical, valor_venda_novo, valor_locacao_novo,
    evento, fonte
)
SELECT c.org_id, c.codigo_canonical, c.valor_venda, c.valor_locacao,
       'primeira_observacao', 'baseline'
  FROM social_wiring.imovel_captacao c
 WHERE (c.valor_venda IS NOT NULL OR c.valor_locacao IS NOT NULL)
   AND NOT EXISTS (
       SELECT 1 FROM social_wiring.imovel_preco_historico h
        WHERE h.org_id = c.org_id AND h.codigo_canonical = c.codigo_canonical
   );

-- ── atendimentos.motivo_perda ───────────────────────────────────────────
ALTER TABLE social_wiring.atendimentos
    ADD COLUMN IF NOT EXISTS motivo_perda TEXT;

COMMENT ON COLUMN social_wiring.atendimentos.motivo_perda IS
    'Free-text reason given when the atendimento is marked perdida '
    '(POST /atendimentos-venda/{id}/perder). NULL when none was given.';
