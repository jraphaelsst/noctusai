-- ============================================================================
-- Migration 310 -- social_wiring.permuta_matches: WHY a broker rejected a match
--
-- WHAT THIS IS
-- ------------
-- The swap scorer (`noctusai_lib.domain.real_estate.permuta`) is tuned from
-- in-house data. A rejection with no reason is useless as a label, and the 28
-- legacy rejected rows carry none. From now on rejecting records:
--
--   motivo_rejeicao          closed vocabulary (CHECKed; mirrored once in
--                            `app/modules/permutas/service.py` MOTIVOS_REJEICAO,
--                            parity pinned by test_motivo_rejeicao.py);
--   motivo_rejeicao_detalhe  free text, required by the API when motivo = 'outro';
--   motivo_lado              which owner said no: origem | destino | ambos.
--
-- NOT NULL is deliberately NOT required on etapa = 'rejeitado' here: the
-- legacy rows would violate it. The API enforces "rejecting needs a reason";
-- the table only enforces "a reason only lives on a rejected row".
--
-- FORWARD-ONLY, IDEMPOTENT (every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.permuta_matches
    ADD COLUMN IF NOT EXISTS motivo_rejeicao TEXT,
    ADD COLUMN IF NOT EXISTS motivo_rejeicao_detalhe TEXT,
    ADD COLUMN IF NOT EXISTS motivo_lado TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'permuta_matches_motivo_rejeicao_check'
          AND conrelid = 'social_wiring.permuta_matches'::regclass
    ) THEN
        ALTER TABLE social_wiring.permuta_matches
            ADD CONSTRAINT permuta_matches_motivo_rejeicao_check
            CHECK (motivo_rejeicao IN (
                'valor', 'tipo', 'localizacao', 'caracteristicas',
                'proprietario_sem_interesse', 'indisponivel', 'documentacao',
                'duplicado', 'outro'
            ));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'permuta_matches_motivo_lado_check'
          AND conrelid = 'social_wiring.permuta_matches'::regclass
    ) THEN
        ALTER TABLE social_wiring.permuta_matches
            ADD CONSTRAINT permuta_matches_motivo_lado_check
            CHECK (motivo_lado IN ('origem', 'destino', 'ambos'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'permuta_matches_motivo_so_em_rejeitado_check'
          AND conrelid = 'social_wiring.permuta_matches'::regclass
    ) THEN
        ALTER TABLE social_wiring.permuta_matches
            ADD CONSTRAINT permuta_matches_motivo_so_em_rejeitado_check
            CHECK (motivo_rejeicao IS NULL OR etapa = 'rejeitado');
    END IF;
END $$;

COMMENT ON COLUMN social_wiring.permuta_matches.motivo_rejeicao IS
    'Why a broker rejected this match (closed vocabulary). These are the '
    'tuning LABELS for the swap scorer (domain/real_estate/permuta.py). NULL '
    'on non-rejected rows and on the legacy rejections that predate it.';

COMMENT ON COLUMN social_wiring.permuta_matches.motivo_rejeicao_detalhe IS
    'Free-text elaboration of motivo_rejeicao; required by the API when the '
    'motivo is ''outro''. Tuning label context for the swap scorer.';

COMMENT ON COLUMN social_wiring.permuta_matches.motivo_lado IS
    'Which owner declined: origem | destino | ambos. Tuning label for the '
    'swap scorer (a one-sided no says which direction scored wrongly).';

NOTIFY pgrst, 'reload schema';
