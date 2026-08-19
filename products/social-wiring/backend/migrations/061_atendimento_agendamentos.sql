-- Migration: atendimento_agendamentos
-- Schema: social_wiring
--
-- ============================================================================
-- WHY — "it doesnt add multiple schedules, it replaces the last one"
-- ============================================================================
-- The card could hold exactly ONE appointment, because "the appointment" was
-- three columns on `clientes` (`data_inicio`, `data_entrega`,
-- `lembrete_minutos_antes`). Saving a second one overwrote the first. That is
-- a data-model limit, not a UI bug, and the user named it precisely: the
-- single slot "works fine but it's not functional to the use i imagine to it".
--
-- Appointments now get their own table, one row each.
--
-- WHOSE APPOINTMENT IS IT? — the ATENDIMENTO's, by the user's ruling.
-- Not the person's. D17 says a person accumulates negotiations over time and
-- closed ones stay as history, so a visit booked for a 2024 purchase and a
-- visit booked for a live negotiation are different things that must not pile
-- onto one list. Hanging them off `atendimentos` keeps them separated by the
-- deal they belong to, and the card (which IS the person) simply shows all of
-- them across that person's atendimentos.
--
-- Measured before choosing: all 1 015 clientes with an atendimento have
-- EXACTLY ONE open one (max = 1), so today the distinction is invisible. It
-- will not stay invisible — that is the whole point of D17 — and modelling it
-- correctly now costs one FK, whereas retrofitting it later costs a migration
-- of live appointments.
--
-- FIELDS — `quando` + `tipo` + `nota` + `lembrete_minutos_antes`, and nothing
-- else. The user was explicit: "when + reminder + note + type. It doesnt need
-- an assignee, only those." No `assignee`, and no `concluido` either — neither
-- was asked for, and a status field nobody requested is a field the UI must
-- then explain.
--
-- THE OLD COLUMNS stay on `clientes` and are NOT dropped here. Dropping a
-- column is the one migration that cannot be reversed by re-running anything,
-- and their values are backfilled below rather than abandoned. They are marked
-- deprecated in `migrations/APPLIED.md`; the code stops reading them in the
-- same commit, which is what makes this a cutover and not a fork.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_agendamentos
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_agendamentos (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    -- ON DELETE CASCADE: an appointment for a deal that no longer exists is
    -- not history, it is a dangling row that would surface on no card and be
    -- swept by nothing.
    atendimento_id          UUID NOT NULL
        REFERENCES social_wiring.atendimentos(id) ON DELETE CASCADE,

    quando                  TIMESTAMPTZ NOT NULL,
    tipo                    TEXT NOT NULL DEFAULT 'outro',
    nota                    TEXT,
    -- NULL = no reminder wanted. 0 = "at the time". The distinction matters:
    -- coalescing NULL to 0 would silently schedule a notification for every
    -- appointment ever created.
    lembrete_minutos_antes  INTEGER,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- No `updated_at`: every other card_hub table (056/057) carries `created_at`
    -- alone, and an edit is already recorded where a user looks for it — the
    -- card timeline. Adding a column plus a trigger here would introduce a
    -- convention this module does not otherwise have, for a value nothing reads.
    --
    -- Soft delete, per D3's reversibility bar (the same bar that made the
    -- negociação collapse mark `substituida_por` instead of deleting).
    deleted_at              TIMESTAMPTZ,

    CONSTRAINT atendimento_agendamentos_tipo_valido
        CHECK (tipo IN ('visita', 'ligacao', 'reuniao', 'outro')),
    CONSTRAINT atendimento_agendamentos_lembrete_nao_negativo
        CHECK (lembrete_minutos_antes IS NULL OR lembrete_minutos_antes >= 0)
);

-- The card's read is "every live appointment for these atendimentos, soonest
-- first" — partial so the index does not carry deleted rows.
CREATE INDEX IF NOT EXISTS ix_sw_agendamentos_atendimento_quando
    ON social_wiring.atendimento_agendamentos (org_id, atendimento_id, quando)
    WHERE deleted_at IS NULL;

-- The sweeper's read is "what is due next across the org".
CREATE INDEX IF NOT EXISTS ix_sw_agendamentos_org_quando
    ON social_wiring.atendimento_agendamentos (org_id, quando)
    WHERE deleted_at IS NULL;

ALTER TABLE social_wiring.atendimento_agendamentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_agendamentos_select_own_org" ON social_wiring.atendimento_agendamentos;
CREATE POLICY "atendimento_agendamentos_select_own_org" ON social_wiring.atendimento_agendamentos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_agendamentos_service_role" ON social_wiring.atendimento_agendamentos;
CREATE POLICY "atendimento_agendamentos_service_role" ON social_wiring.atendimento_agendamentos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. cliente_lembretes gains agendamento_id
-- ----------------------------------------------------------------------------
-- One appointment ↔ at most one PENDING reminder. Without this column the
-- cancel-then-reschedule logic can only find pending reminders "for this
-- person", so booking a second appointment would cancel the first one's
-- notification — the same overwrite bug one layer down.
--
-- NULLABLE on purpose: rows written before this migration belong to the old
-- single-slot model and have no agendamento to point at. Backfilled below for
-- the ones that do.
ALTER TABLE social_wiring.cliente_lembretes
    ADD COLUMN IF NOT EXISTS agendamento_id UUID
        REFERENCES social_wiring.atendimento_agendamentos(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_sw_lembretes_agendamento
    ON social_wiring.cliente_lembretes (agendamento_id)
    WHERE agendamento_id IS NOT NULL AND enviado_em IS NULL AND cancelado_em IS NULL;

-- ----------------------------------------------------------------------------
-- 3. Backfill — carry every existing date into the new model
-- ----------------------------------------------------------------------------
-- Measured on the live database at authoring time: exactly ONE cliente has any
-- date set. The loop is written for correctness, not for volume.
--
-- `data_entrega` is the appointment; `data_inicio` is not carried, because in
-- the old model it was the *start of a window* around one delivery, not a
-- second appointment — inventing a second row from it would fabricate an
-- appointment the user never booked. It stays readable on `clientes`.
DO $backfill$
DECLARE
    r RECORD;
    v_agendamento_id UUID;
BEGIN
    FOR r IN
        SELECT c.id AS cliente_id, c.org_id, c.data_entrega, c.lembrete_minutos_antes,
               a.id AS atendimento_id
        FROM social_wiring.clientes c
        JOIN LATERAL (
            SELECT id FROM social_wiring.atendimentos
            WHERE cliente_id = c.id AND substituida_por IS NULL
            ORDER BY COALESCE(arquivado, false), created_at
            LIMIT 1
        ) a ON TRUE
        WHERE c.data_entrega IS NOT NULL
    LOOP
        INSERT INTO social_wiring.atendimento_agendamentos
            (org_id, atendimento_id, quando, tipo, nota, lembrete_minutos_antes)
        VALUES
            (r.org_id, r.atendimento_id, r.data_entrega, 'outro',
             'Migrado da data de entrega anterior (migration 061).',
             r.lembrete_minutos_antes)
        RETURNING id INTO v_agendamento_id;

        -- Re-point this cliente's PENDING reminder at the appointment it is
        -- actually for, so the cancel-on-reschedule logic can find it.
        UPDATE social_wiring.cliente_lembretes
           SET agendamento_id = v_agendamento_id
         WHERE cliente_id = r.cliente_id
           AND enviado_em IS NULL
           AND cancelado_em IS NULL
           AND agendamento_id IS NULL;
    END LOOP;
END;
$backfill$;
