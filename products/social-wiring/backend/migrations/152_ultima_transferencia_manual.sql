-- ============================================================================
-- Migration 152 · social_wiring: manual override for [Q9]'s previous-owner
-- rule — "a última transferência de propriedade"
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- `contrato_gerador.derivacao.exige_antigo_proprietario` (the contract
-- readiness gate's LAST remaining LIVE `faltando`, found 2026-09-22 on
-- RODRIGO MORASCHI ENRIQUEZ / EUROVILLE-535) reads `imovel.
-- ultima_transferencia_em` and refuses to generate the contract until it
-- resolves. Until now the ONLY source for it was `titulo_service.
-- antigos_proprietarios`'s search for a `compra_e_venda` act in the
-- matrícula extraction — a matrícula whose last transfer is recorded as a
-- PERMUTA (or a dação/arrematação) could never satisfy the gate, and there
-- was no human input anywhere to answer it either. The office's standing
-- rule: every field the contract needs is either extracted from a document
-- or has a human input — this field had neither for that case.
--
-- 1. `imovel_dados` GAINS THE MANUAL OVERRIDE
-- --------------------------------------------------------------------------
-- Mirrors `titulo_aquisitivo_texto`/`onus_credor`'s (migration 115) single-
-- stamp confirmation shape (`*_confirmado_por` / `*_confirmado_em`), not
-- `endereco_registro_texto`'s (139) — this override has THREE parts (date,
-- an optional nature, and an explicit "no transfer at all" statement), so
-- it needs its own tri-state contract rather than the single "clear iff
-- null" shape a lone text column carries. `ultima_transferencia_manual_
-- sem_registro` is the important addition: `data IS NULL` alone already
-- means "unknown" everywhere else in this table (`endereco_registro_texto`,
-- `onus_credor`, ...), and this feature specifically needs an ANSWER that
-- means "there genuinely is none" — the gate must stop asking once a human
-- has said so, not keep treating silence and a deliberate "none" the same.
--
-- `ultima_transferencia_manual_natureza` is restricted to the same 4
-- natures `titulo_service.NATUREZAS_ULTIMA_TRANSFERENCIA` recognises as an
-- ownership-transferring act FOR THIS RULE — a strict subset of the seed's
-- broader `NATUREZAS_TRANSFERENCIA` (which also counts `doacao`/`partilha`):
-- `test_the_confirmed_nature_decides_what_a_sale_is` already established
-- that re-classifying an act as `doacao` is how an operator tells this
-- feature "this did not transfer for consideration, do not treat it as the
-- sale" — a donation or an inheritance partition must not silently
-- substitute for the manual override either.
--
-- Code changes (`titulo_service.antigos_proprietarios`/
-- `.confirmar_ultima_transferencia_manual`, `dados_service.
-- gravar_ultima_transferencia_manual`, the router, `contrato_gerador.
-- dados.Imovel.ultima_transferencia_sem_registro_confirmado`,
-- `derivacao.exige_antigo_proprietario`) ship alongside this file in the
-- same change.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead + user consent. See
-- `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS ultima_transferencia_manual_data           DATE,
    ADD COLUMN IF NOT EXISTS ultima_transferencia_manual_natureza       TEXT,
    ADD COLUMN IF NOT EXISTS ultima_transferencia_manual_sem_registro   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ultima_transferencia_manual_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS ultima_transferencia_manual_confirmado_em  TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.ultima_transferencia_manual_data IS
    'Manual override (migration 152) for [Q9]''s "última transferência de '
    'propriedade" when the matrícula''s acts do not already answer it — a '
    'human-typed registration date, always available on the property page. '
    'Wins ONLY when the acts-based derivation (titulo_service.'
    'antigos_proprietarios) finds nothing; never overrides a found act.';
COMMENT ON COLUMN social_wiring.imovel_dados.ultima_transferencia_manual_sem_registro IS
    'An explicit "não consta transferência registrada" statement — the '
    'human''s ANSWER that there is no registered transfer, not the absence '
    'of one. Resolves contrato_gerador.derivacao.exige_antigo_proprietario '
    'to False instead of leaving it faltando. Mutually exclusive with '
    '_data (see the _exclusiva constraint below).';
COMMENT ON COLUMN social_wiring.imovel_dados.ultima_transferencia_manual_confirmado_por IS
    'Who set the CURRENT override (a date+nature, or sem_registro) — one '
    'stamp for the whole override, mirroring titulo_aquisitivo_texto''s '
    '(115) shape.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_ultima_transferencia_manual_natureza_check;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_ultima_transferencia_manual_natureza_check
    CHECK (ultima_transferencia_manual_natureza IS NULL OR ultima_transferencia_manual_natureza IN (
        'compra_e_venda', 'permuta', 'dacao', 'arrematacao'
    ));

-- A nature only means something alongside a date — it must never survive on
-- its own (e.g. after `_data` is cleared but `_natureza` was left behind).
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_ultima_transferencia_manual_natureza_requer_data;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_ultima_transferencia_manual_natureza_requer_data
    CHECK (ultima_transferencia_manual_natureza IS NULL OR ultima_transferencia_manual_data IS NOT NULL);

-- A date AND "não consta" set together is a contradiction, not a richer
-- answer — the write path refuses it too (titulo_service.
-- confirmar_ultima_transferencia_manual), this is the backstop.
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_ultima_transferencia_manual_exclusiva;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_ultima_transferencia_manual_exclusiva
    CHECK (NOT (ultima_transferencia_manual_data IS NOT NULL AND ultima_transferencia_manual_sem_registro));

-- A confirmation is a stamp: an override (either shape) without WHEN is a
-- claim (mirrors migration 115's `imovel_dados_titulo_aquisitivo_texto_
-- confirmado` / `imovel_dados_onus_credor_confirmado`).
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_ultima_transferencia_manual_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_ultima_transferencia_manual_confirmado
    CHECK (
        (ultima_transferencia_manual_data IS NOT NULL OR ultima_transferencia_manual_sem_registro)
        = (ultima_transferencia_manual_confirmado_em IS NOT NULL)
    );
