-- =============================================================================
-- 008_consent_retention.sql
--
-- compliance-audit-reconciliation Phase 5 — model consent as an auditable
-- record per Q5 (§2): separate scopes, each revocable independently.
--
-- Q5 decision (locked 2026-04-22): "separate consent scopes — recording,
-- transcription, AI summary, longitudinal analysis — each revocable
-- independently. Recording cannot start without at minimum the `recording`
-- scope consent." This replaces the ephemeral `consent_given: bool` flag
-- on SessionStartRequest (which LGPD Art. 8 does not accept as an auditable
-- consent record).
--
-- Schema shape:
--   * one row per (appointment, scope) pair
--   * `granted_at` = when the consent was initially granted (never NULL)
--   * `revoked_at` = when it was revoked (NULL = active)
--   * `policy_version` + `purpose_text` = the specific version and purpose
--     the patient consented to; LGPD requires retention of the exact text
--     the user agreed to at the time of agreement.
--   * `actor_user_id` = who recorded the consent (normally the patient;
--     therapist-of-session may attest when the patient has verbally
--     consented in-room — actor_user_id lets audits identify that case).
--
-- RLS: therapist-of-session + patient-of-session can read/write consents
-- on their appointments; platform_admin EXCLUDED per Phase 3 / Q2 pattern
-- (consent metadata is part of the clinical audit trail). service_role
-- keeps full access.
-- =============================================================================


CREATE TABLE IF NOT EXISTS therapy.consent_records (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL REFERENCES therapy.appointments(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    scope TEXT NOT NULL CHECK (scope IN ('recording', 'transcription', 'ai_summary', 'longitudinal')),
    policy_version TEXT NOT NULL,
    purpose_text TEXT NOT NULL,
    actor_user_id UUID NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(appointment_id, scope)
);

CREATE INDEX IF NOT EXISTS idx_consent_records_appointment ON therapy.consent_records(appointment_id);
CREATE INDEX IF NOT EXISTS idx_consent_records_patient ON therapy.consent_records(patient_id);
CREATE INDEX IF NOT EXISTS idx_consent_records_therapist ON therapy.consent_records(therapist_id);
CREATE INDEX IF NOT EXISTS idx_consent_records_active ON therapy.consent_records(appointment_id, scope) WHERE revoked_at IS NULL;

DROP TRIGGER IF EXISTS consent_records_updated_at ON therapy.consent_records;
CREATE TRIGGER consent_records_updated_at
    BEFORE UPDATE ON therapy.consent_records
    FOR EACH ROW
    EXECUTE FUNCTION therapy.set_updated_at();


ALTER TABLE therapy.consent_records ENABLE ROW LEVEL SECURITY;


-- Access: therapist-of-session OR patient-of-session. platform_admin /
-- clinic_admin EXCLUDED (clinical audit-trail data per Q2).
DROP POLICY IF EXISTS consent_records_policy ON therapy.consent_records;

CREATE POLICY consent_records_policy ON therapy.consent_records
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM therapy.appointments a
            WHERE a.id = consent_records.appointment_id
              AND (a.therapist_id = (SELECT auth.uid())
                   OR a.patient_id = (SELECT auth.uid()))
        )
    );


DROP POLICY IF EXISTS "service_role_bypass" ON therapy.consent_records;
CREATE POLICY "service_role_bypass" ON therapy.consent_records
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
