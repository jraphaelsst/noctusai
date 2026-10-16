-- 282 -- imovel_transacoes: record every SW-won deal as it closes, not only once.
--
-- WHY: migration 266 inserted the SW-native won deals with a one-shot BACKFILL,
-- and nothing else in the codebase writes fonte='sw_negociacao'. So a deal won
-- after 266 was applied (2026-10-15) never reached the evaluator's ground-truth
-- table. This file moves the 266 rule into ONE function and fires it from the
-- two places a won deal's data changes:
--   * atendimentos         -- the deal becomes won (status='aceita' + closed_at,
--                             set by pipeline/aceite.py, the system's own
--                             definition of a sale; see 081).
--   * atendimento_negociacao -- the price / code / payment flags are typed or
--                             corrected after the deal was won.
-- An open negociação with a value is a forecast, not a sale, and stays out --
-- exactly as in 266 and 081.
--
-- RULE (same as the 266 backfill): one row per won deal, keyed
-- (org_id, 'sw_negociacao', atendimento_id). A deal that carries its imóvel code
-- is born 'confirmado'; without one it stays 'pendente' for an admin to link.
--
-- NEVER OVERWRITES A HUMAN DECISION. A later change refreshes the row only while
-- no person has decided it: 'pendente', or the machine-set 'confirmado'
-- (confirmado_por IS NULL). A row an admin confirmed or rejected is left alone.
-- A price cleared after the sale does not delete the row (the SELECT finds no
-- priced deal, so nothing is written).
--
-- SECURITY: writes to imovel_transacoes are service-side only (266 revokes them
-- from authenticated), and the accept route may run on a user-JWT client -- so
-- the functions are SECURITY DEFINER with a pinned search_path and EXECUTE
-- revoked, the same posture as the 262 price-history triggers.
--
-- Forward-only + idempotent. PREREQUISITES: 266.

SET search_path = social_wiring, public;

-- ── The one rule ───────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.sincronizar_transacao_sw(p_atendimento_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    INSERT INTO social_wiring.imovel_transacoes AS t (
        org_id, codigo_canonical, tipo, valor_transacao, data_transacao,
        financiamento, fgts, fonte, fonte_ref, vinculo_status, confirmado_em
    )
    SELECT n.org_id,
           n.imovel_codigo,
           'venda',
           n.valor_negociado,
           (a.closed_at AT TIME ZONE 'America/Sao_Paulo')::date,
           n.financiamento,
           n.fgts,
           'sw_negociacao',
           n.atendimento_id::text,
           CASE WHEN n.imovel_codigo IS NULL THEN 'pendente' ELSE 'confirmado' END,
           CASE WHEN n.imovel_codigo IS NULL THEN NULL ELSE now() END
      FROM social_wiring.atendimento_negociacao n
      JOIN social_wiring.atendimentos a ON a.id = n.atendimento_id
     WHERE n.atendimento_id = p_atendimento_id
       AND a.status = 'aceita'
       AND a.closed_at IS NOT NULL
       AND n.valor_negociado IS NOT NULL
       AND n.valor_negociado > 0
    ON CONFLICT (org_id, fonte, fonte_ref) DO UPDATE
       SET codigo_canonical = EXCLUDED.codigo_canonical,
           valor_transacao  = EXCLUDED.valor_transacao,
           data_transacao   = EXCLUDED.data_transacao,
           financiamento    = EXCLUDED.financiamento,
           fgts             = EXCLUDED.fgts,
           vinculo_status   = EXCLUDED.vinculo_status,
           confirmado_em    = CASE WHEN EXCLUDED.codigo_canonical IS NULL THEN NULL
                                   ELSE COALESCE(t.confirmado_em, now()) END
     WHERE t.confirmado_por IS NULL
       AND t.vinculo_status IN ('pendente', 'confirmado');
END;
$$;

REVOKE EXECUTE ON FUNCTION social_wiring.sincronizar_transacao_sw(UUID) FROM PUBLIC, anon, authenticated;

-- ── Trigger: the deal is won ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.registrar_transacao_sw_atendimento()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    PERFORM social_wiring.sincronizar_transacao_sw(NEW.id);
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION social_wiring.registrar_transacao_sw_atendimento() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_atendimentos_transacao_sw ON social_wiring.atendimentos;
CREATE TRIGGER trg_atendimentos_transacao_sw
    AFTER UPDATE OF status, closed_at ON social_wiring.atendimentos
    FOR EACH ROW
    WHEN (NEW.status = 'aceita' AND NEW.closed_at IS NOT NULL
      AND (OLD.status    IS DISTINCT FROM NEW.status
        OR OLD.closed_at IS DISTINCT FROM NEW.closed_at))
    EXECUTE FUNCTION social_wiring.registrar_transacao_sw_atendimento();

-- ── Trigger: a won deal's data is typed or corrected ────────────────────────
-- The function itself refuses an open deal, so these fire on every negociação.
CREATE OR REPLACE FUNCTION social_wiring.registrar_transacao_sw_negociacao()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    PERFORM social_wiring.sincronizar_transacao_sw(NEW.atendimento_id);
    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION social_wiring.registrar_transacao_sw_negociacao() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_negociacao_transacao_sw_ins ON social_wiring.atendimento_negociacao;
CREATE TRIGGER trg_negociacao_transacao_sw_ins
    AFTER INSERT ON social_wiring.atendimento_negociacao
    FOR EACH ROW EXECUTE FUNCTION social_wiring.registrar_transacao_sw_negociacao();

DROP TRIGGER IF EXISTS trg_negociacao_transacao_sw_upd ON social_wiring.atendimento_negociacao;
CREATE TRIGGER trg_negociacao_transacao_sw_upd
    AFTER UPDATE OF valor_negociado, imovel_codigo, financiamento, fgts
    ON social_wiring.atendimento_negociacao
    FOR EACH ROW
    WHEN (OLD.valor_negociado IS DISTINCT FROM NEW.valor_negociado
       OR OLD.imovel_codigo   IS DISTINCT FROM NEW.imovel_codigo
       OR OLD.financiamento   IS DISTINCT FROM NEW.financiamento
       OR OLD.fgts            IS DISTINCT FROM NEW.fgts)
    EXECUTE FUNCTION social_wiring.registrar_transacao_sw_negociacao();

-- ── Catch-up: deals won between 266 and this file ───────────────────────────
-- Re-running the rule over every won deal is idempotent (the conflict branch
-- only refreshes undecided rows with the same values).
SELECT social_wiring.sincronizar_transacao_sw(a.id)
  FROM social_wiring.atendimentos a
 WHERE a.status = 'aceita'
   AND a.closed_at IS NOT NULL;

NOTIFY pgrst, 'reload schema';
