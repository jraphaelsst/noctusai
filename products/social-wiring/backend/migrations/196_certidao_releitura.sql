-- ============================================================================
-- 196 — certidão RE-READ state + its access-log action (B2, 2026-10-03)
--
-- "Reler" re-extracts a certidão's STORED PDF with the current reader (the
-- CENPROT reader improved after many rows were read). Two facts it needs to
-- keep that no column held:
--
-- 1. `certidao_resultados.releitura` (jsonb, NULL = never re-read) — the
--    last re-read's state, written by `certidoes.service`:
--      {"estado": "em_andamento" | "concluida",
--       "iniciada_em": iso, "concluida_em": iso | null,
--       "divergencias": [{"campo", "valor_atual", "valor_lido"}]}
--    `estado='em_andamento'` is the in-flight marker for a LIVE emission's
--    re-read (its `status` stays `sucesso` — a live row is never flipped to
--    `processando`, which the stale sweep would treat as a manual upload).
--    `divergencias` is the human-facing aviso: a re-read NEVER overwrites a
--    human-entered/confirmed value (D1) nor a registry (InfoSimples) value —
--    where the new reading differs, the difference lands here and the card
--    offers "Aplicar valores lidos" (a human PATCH, which clears it).
--
-- 2. `certidao_resultado_acessos.acao` gains 'releitura' — a re-read reads
--    the document's content server-side, so it is logged in the same LGPD
--    content-read log as a view/download, with the actor.
--
-- Forward-only, idempotent, no data touched.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS releitura jsonb;

COMMENT ON COLUMN social_wiring.certidao_resultados.releitura IS
    'Last re-read of the stored PDF (estado, iniciada_em, concluida_em, divergencias = values read but not written because a human or registry value was kept).';

-- 107 declared the CHECK inline, so Postgres named it <table>_<column>_check.
ALTER TABLE social_wiring.certidao_resultado_acessos
    DROP CONSTRAINT IF EXISTS certidao_resultado_acessos_acao_check;
ALTER TABLE social_wiring.certidao_resultado_acessos
    ADD CONSTRAINT certidao_resultado_acessos_acao_check
    CHECK (acao IN ('view', 'download', 'delete', 'releitura'));
