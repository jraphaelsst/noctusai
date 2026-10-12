-- ============================================================================
-- Migration 249 — certidao_resultados.resultado_origem gains 'texto'.
--
-- WHY: P6 deterministic extractors. A certidão's verdict is now read from the
-- issuer's own printed sentence ("…CERTIFICADO QUE NÃO CONSTAM DÉBITOS…",
-- "…VERIFICOU NADA CONSTAR COMO RÉU…") by `noctusai_lib.integrations.
-- documents.certidao_resultado`, ahead of the LLM. `resultado_origem` TRACKS
-- THE VERDICT (migration 107's header): recording a printed reading as 'ia'
-- would say a model decided what the document itself states, and as 'api'
-- would say a source returned it. 'texto' is the honest answer.
--
--   api    — the source's API returned the verdict
--   texto  — read from the issuer's printed sentence (deterministic)
--   ia     — a model's structured read decided it
--   manual — a human set/confirmed it (locks the row)
--
-- Additive (a wider CHECK), idempotent (DROP IF EXISTS + ADD), replay-safe.
-- ============================================================================

ALTER TABLE social_wiring.certidao_resultados
    DROP CONSTRAINT IF EXISTS certidao_resultados_resultado_origem_check;
ALTER TABLE social_wiring.certidao_resultados
    ADD CONSTRAINT certidao_resultados_resultado_origem_check
    CHECK (resultado_origem IS NULL OR resultado_origem IN ('api', 'texto', 'ia', 'manual'));

COMMENT ON COLUMN social_wiring.certidao_resultados.resultado_origem IS
    'Who decided `resultado`: api (source API) | texto (issuer''s printed '
    'sentence, deterministic — migration 249) | ia (model read) | manual '
    '(a human; locks the row). Tracks the VERDICT, not every field.';
