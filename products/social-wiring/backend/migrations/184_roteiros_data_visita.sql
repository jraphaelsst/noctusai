-- ============================================================================
-- 184 — roteiros.data_visita: the day the visit route is planned for
-- ============================================================================
-- DATE (no time). NULLABLE in the schema because legacy roteiros (082) have no
-- date and must not be invented one; REQUIRED on create at the service layer
-- (BE-roteiro rejects a create without it). The roteiro PDF prints it.
--
-- Forward-only, idempotent. Touches no existing row.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.roteiros
    ADD COLUMN IF NOT EXISTS data_visita DATE;

COMMENT ON COLUMN social_wiring.roteiros.data_visita IS
    'Planned visit day (date only). NULL only for legacy rows; the create '
    'endpoint requires it. Migration 184.';

CREATE INDEX IF NOT EXISTS idx_sw_roteiros_org_data_visita
    ON social_wiring.roteiros (org_id, data_visita DESC)
    WHERE deleted_at IS NULL AND data_visita IS NOT NULL;

NOTIFY pgrst, 'reload schema';
