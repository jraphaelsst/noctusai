-- ============================================================================
-- Migration 116 · social_wiring: situação cadastral + homônimos (certidões)
--
-- WHAT THIS IS
-- ------------
-- Two additions the contract-automation office's answers on certidões
-- surfaced, both widening migration 107's structured fields rather than
-- introducing a new table:
--
--   1. `negativa_com_homonimos` — a fifth `resultado` value. A negativa
--      certidão can say so ONLY WITH A CAVEAT: no record found for this
--      exact identity, but the source flags OTHER records under the same
--      name/CPF it could not rule out (a homônimo). That is materially
--      different due-diligence information from a clean `negativa` — a
--      contract generated off the wrong bucket would assert a clean history
--      the certidão itself does not — so it gets its own value rather than
--      collapsing into `negativa` or `positiva_com_efeito_de_negativa`
--      (which means something else: a DIFFERENT debt exists but is
--      discharged, not "this document might not be about the right
--      person").
--
--   2. `certidao_consultas.situacao_cadastral` / `data_situacao` /
--      `situacao_origem` — the CNPJ/CPF's registration state (ativa |
--      baixada | inapta | suspensa | nula) and when it was last known. The
--      office's answer requires company certidões when the CNPJ is ativa,
--      inapta, or baixada under 5 years — a rule this migration cannot
--      enforce (no gate is written; see 099's header for why a gate ahead
--      of a stated policy is worked around) but that at least needs
--      somewhere to record the fact it depends on.
--
-- 🔴 WHY ON THE CONSULTA, NOT A RESULTADO — SAME REASONING AS 099
-- ------------------------------------------------------------------
-- The registration state is a fact about the DOCUMENT under investigation
-- (the CPF/CNPJ), not about any one certificate type — a CNPJ is exactly as
-- "ativa" or "baixada" regardless of which of the ten certidões you read.
-- Putting it on `certidao_resultados` would mean asking "according to
-- WHICH certificate" for a question that has one honest answer per
-- consulta, and would need it repeated (or reconciled) across up to
-- thirteen rows for no gain — `imovel_dados.situacao_onus` (099) makes the
-- identical call for the identical reason, one level up.
--
-- 🔴 `situacao_origem` FOLLOWS `resultado_origem`'S SHAPE — WITH A KNOWN GAP
-- -----------------------------------------------------------------------
-- `api` | `ia` | `manual`, same vocabulary as 107's `resultado_origem`, for
-- the same reason: "who last wrote this" has to be answerable independent
-- of the value itself. The gap, stated plainly rather than silently
-- deferred: at the time of this migration, NEITHER `api` NOR `ia` writes
-- this field. The existing API/IA payloads this module already receives
-- were inspected specifically for this (`registry._parse_resultado_padrao`,
-- the `_analyze_estrutura_with_ai` JSON extraction, and this product's own
-- fixtures) and none carry a distinguishable company-registration-status
-- signal — the one `situacao` field these responses DO sometimes carry
-- (e.g. `"situacao": "Regular"` on a CND Federal fixture) describes DEBT
-- regularity, the same concept `resultado` already captures, not whether
-- the CNPJ itself is active or baixada. So today `situacao_origem` is only
-- ever written `'manual'`, via `PATCH /api/certidoes/consultas/{id}/
-- situacao-cadastral` (`routers/certidoes.py::atualizar_situacao_cadastral_
-- route`). `api`/`ia` are kept in the vocabulary rather than dropped to two
-- values, because the moment a source IS found to carry this signal, the
-- column should not need a THIRD migration to accept the value that proves
-- it.
--
-- `nula` (situação inexistente/cancelada — an inscrição CNPJ that never
-- completed, or one struck down) is in the vocabulary alongside `ativa` /
-- `baixada` / `inapta` / `suspensa` because it is one of the states
-- `situacao_cadastral` genuinely takes at the Receita Federal, not a
-- speculative addition.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. certidao_resultados.resultado — add negativa_com_homonimos
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_resultados
    DROP CONSTRAINT IF EXISTS certidao_resultados_resultado_check;
ALTER TABLE social_wiring.certidao_resultados
    ADD CONSTRAINT certidao_resultados_resultado_check
    CHECK (resultado IS NULL OR resultado IN (
        'negativa', 'positiva', 'positiva_com_efeito_de_negativa', 'nao_emitida',
        'negativa_com_homonimos'
    ));

COMMENT ON COLUMN social_wiring.certidao_resultados.resultado IS
    'negativa | positiva | positiva_com_efeito_de_negativa | nao_emitida | '
    'negativa_com_homonimos (migration 116 — nada consta PARA ESTA identidade, '
    'mas o documento menciona homônimos/multiplicidade de registros sob o '
    'mesmo nome/CPF que impedem confirmar a identidade com plena certeza). '
    'NULL means not yet determined — see migration 107''s header for why '
    'that is the honest default rather than a guess. CHECK constraint above '
    'is the vocabulary; kept in sync with app/modules/certidoes/schemas.py''s '
    'ResultadoPatch Literal and registry.RESULTADO_VALUES.';

-- ----------------------------------------------------------------------------
-- 2. certidao_consultas — CNPJ/CPF registration status
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_consultas
    ADD COLUMN IF NOT EXISTS situacao_cadastral TEXT,
    ADD COLUMN IF NOT EXISTS data_situacao      DATE,
    ADD COLUMN IF NOT EXISTS situacao_origem    TEXT;

COMMENT ON COLUMN social_wiring.certidao_consultas.situacao_cadastral IS
    'ativa | baixada | inapta | suspensa | nula — the CPF/CNPJ''s own '
    'registration status at the source (Receita Federal), independent of '
    'any one certificate''s debt verdict. NULL means unknown. See this '
    'migration''s header for why it lives here and not on a resultado.';
COMMENT ON COLUMN social_wiring.certidao_consultas.data_situacao IS
    'When situacao_cadastral was last known to be true — the date printed '
    'on/behind the source that stated it, not this row''s updated_at.';
COMMENT ON COLUMN social_wiring.certidao_consultas.situacao_origem IS
    'api | ia | manual — who last wrote situacao_cadastral/data_situacao, '
    'same shape as certidao_resultados.resultado_origem (107). See this '
    'migration''s header for the known gap: only ''manual'' is written today.';

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_situacao_cadastral_check;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_situacao_cadastral_check
    CHECK (situacao_cadastral IS NULL OR situacao_cadastral IN (
        'ativa', 'baixada', 'inapta', 'suspensa', 'nula'
    ));

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_situacao_origem_check;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_situacao_origem_check
    CHECK (situacao_origem IS NULL OR situacao_origem IN ('api', 'ia', 'manual'));
