-- =============================================================================
-- 007_clinical_data_privacy.sql
--
-- compliance-audit-reconciliation Phase 3 — encode the user's privacy-model
-- decisions (Q1 + Q2 answered 2026-04-22) in RLS.
--
-- Q2 decision: platform_admin EXCLUDED from clinical content. Clinic admins
-- EXCLUDED from clinical content (operational metadata only — they keep
-- appointments/video_rooms access). Therapist-of-session + patient-of-session
-- keep their access per the legal doc (`GRAVACAO_SESSOES_LEGAL.md`).
--
-- Q1 decision: patient_session_notes stays therapist-readable (via the
-- session_records → appointments chain); platform_admin dropped per Q2.
--
-- Tables touched (all clinical content):
--   session_records, session_summary_versions, session_observations,
--   session_audio_segments, session_interruptions, patient_session_notes,
--   clinical_longitudinal_analyses, patient_longitudinal_analyses
--
-- Tables NOT touched (operational metadata; platform_admin/clinic_admin
-- legitimately need access for scheduling + infra debugging):
--   appointments, video_rooms
--
-- `service_role_bypass` policies are preserved on every table — backend code
-- running with service role still has full access for operational paths.
-- Per Q2 note: service-role call sites into clinical content should be
-- narrowly audited in follow-up work (tracked in §4 Out of scope).
-- =============================================================================


-- session_records — clinical: transcripts + therapist private notes.
-- Access: therapist-of-session OR patient-of-session (added — they have
-- rights to their own session records). platform_admin dropped.
DROP POLICY IF EXISTS session_records_policy ON therapy.session_records;

CREATE POLICY session_records_policy ON therapy.session_records
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM therapy.appointments a
            WHERE a.id = session_records.appointment_id
              AND (a.therapist_id = (SELECT auth.uid())
                   OR a.patient_id = (SELECT auth.uid()))
        )
    );


-- session_summary_versions — clinical: session summaries.
-- Access: therapist-of-session OR patient-of-session (existing behavior).
-- platform_admin dropped.
DROP POLICY IF EXISTS session_summary_versions_policy ON therapy.session_summary_versions;

CREATE POLICY session_summary_versions_policy ON therapy.session_summary_versions
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM therapy.session_records sr
            JOIN therapy.appointments a ON a.id = sr.appointment_id
            WHERE sr.id = session_summary_versions.session_record_id
              AND (a.therapist_id = (SELECT auth.uid())
                   OR a.patient_id = (SELECT auth.uid()))
        )
    );


-- session_observations — clinical: therapist private clinical observations.
-- Access: therapist-of-session ONLY. Patient never sees observations
-- (this is the "therapist's private clinical notes" per the product model).
-- platform_admin dropped.
DROP POLICY IF EXISTS session_observations_policy ON therapy.session_observations;

CREATE POLICY session_observations_policy ON therapy.session_observations
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM therapy.session_records sr
            JOIN therapy.appointments a ON a.id = sr.appointment_id
            WHERE sr.id = session_observations.session_record_id
              AND a.therapist_id = (SELECT auth.uid())
        )
    );


-- session_audio_segments — clinical: raw session audio files.
-- Access: therapist-of-session ONLY. platform_admin dropped.
DROP POLICY IF EXISTS session_audio_segments_policy ON therapy.session_audio_segments;

CREATE POLICY session_audio_segments_policy ON therapy.session_audio_segments
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM therapy.video_rooms vr
            JOIN therapy.appointments a ON a.id = vr.appointment_id
            WHERE vr.id = session_audio_segments.video_room_id
              AND a.therapist_id = (SELECT auth.uid())
        )
    );


-- session_interruptions — clinical-session metadata (pauses, reasons).
-- Access: participant who generated the event. platform_admin dropped
-- (it's clinical-session data even though it looks operational).
DROP POLICY IF EXISTS session_interruptions_policy ON therapy.session_interruptions;

CREATE POLICY session_interruptions_policy ON therapy.session_interruptions
    FOR ALL
    TO authenticated
    USING (
        participant_user_id = (SELECT auth.uid())
    );


-- patient_session_notes — clinical: patient's session notes.
-- Q1 decision: stays therapist-readable. Patient reads their own; therapist-
-- of-session reads theirs. platform_admin dropped.
DROP POLICY IF EXISTS patient_session_notes_policy ON therapy.patient_session_notes;

CREATE POLICY patient_session_notes_policy ON therapy.patient_session_notes
    FOR ALL
    TO authenticated
    USING (
        patient_id = (SELECT auth.uid())
        OR EXISTS (
            SELECT 1
            FROM therapy.session_records sr
            JOIN therapy.appointments a ON a.id = sr.appointment_id
            WHERE sr.id = patient_session_notes.session_record_id
              AND a.therapist_id = (SELECT auth.uid())
        )
    );


-- clinical_longitudinal_analyses — clinical: therapist-authored patient analyses.
-- Access: therapist who authored the analysis ONLY.
-- platform_admin AND clinic_admin dropped (clinical content per Q2 —
-- clinic_admin was in the prior policy but Q2 excludes them).
DROP POLICY IF EXISTS clinical_longitudinal_policy ON therapy.clinical_longitudinal_analyses;

CREATE POLICY clinical_longitudinal_policy ON therapy.clinical_longitudinal_analyses
    FOR ALL
    TO authenticated
    USING (
        therapist_id = (SELECT auth.uid())
    );


-- patient_longitudinal_analyses — clinical: patient-facing longitudinal analyses
-- authored by therapist.
-- Access: patient OR authoring therapist. platform_admin dropped.
DROP POLICY IF EXISTS patient_longitudinal_policy ON therapy.patient_longitudinal_analyses;

CREATE POLICY patient_longitudinal_policy ON therapy.patient_longitudinal_analyses
    FOR ALL
    TO authenticated
    USING (
        patient_id = (SELECT auth.uid())
        OR therapist_id = (SELECT auth.uid())
    );


-- Comment for future auditors: appointments + video_rooms policies are UNCHANGED
-- by this migration — they carry operational metadata (scheduling, room infra)
-- that clinic_admin and platform_admin legitimately need access to.
--
-- service_role_bypass policies on every table are also UNCHANGED — backend
-- operational code (migrations, admin scripts) still works; only user-facing
-- clinical access is narrowed.
