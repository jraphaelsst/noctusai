-- =====================================================================
-- Therapy Platform — Consolidated Schema Migration
-- All therapy objects live in the `therapy` schema.
-- Core platform tables stay in `public`.
-- Run this once on a fresh Supabase project (after core migration).
-- =====================================================================

-- -----------------------------------------------------------------
-- 0. SCHEMA + PERMISSIONS
-- -----------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS therapy;

GRANT USAGE ON SCHEMA therapy TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA therapy TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA therapy TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon, authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA therapy TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT USAGE ON SEQUENCES TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA therapy TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA therapy GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- -----------------------------------------------------------------
-- 1. HELPER FUNCTIONS
-- -----------------------------------------------------------------

-- Generic updated_at trigger
CREATE OR REPLACE FUNCTION therapy.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = therapy, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

-- Role helper: returns the current user's role from JWT claims
CREATE OR REPLACE FUNCTION therapy.current_user_role()
  RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = therapy, public
AS $$ SELECT COALESCE((SELECT current_setting('request.jwt.claims', true))::json->'user_metadata'->>'role', 'patient'); $$;

-- Clinic helper: returns the current user's clinic_id from JWT claims
CREATE OR REPLACE FUNCTION therapy.current_clinic_id()
  RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = therapy, public
AS $$ SELECT ((SELECT current_setting('request.jwt.claims', true))::json->'user_metadata'->>'clinic_id')::uuid; $$;

-- -----------------------------------------------------------------
-- 2. TABLES (39 total)
-- -----------------------------------------------------------------

-- ======================== Identity (3) ========================

CREATE TABLE IF NOT EXISTS therapy.clinics (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    cnpj TEXT,
    responsible_person TEXT,
    contact_email TEXT,
    phone TEXT,
    logo_url TEXT,
    description TEXT,
    tagline TEXT,
    specialties_offered TEXT[],
    is_approved BOOLEAN DEFAULT false,
    approved_at TIMESTAMPTZ,
    approved_by UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS therapy.therapist_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    clinic_id UUID REFERENCES therapy.clinics(id),
    crp TEXT NOT NULL,
    bio TEXT,
    specialties TEXT[],
    approaches TEXT[],
    photo_url TEXT,
    default_session_price DECIMAL(10,2),
    session_duration_minutes INT DEFAULT 50,
    is_approved BOOLEAN DEFAULT false,
    approved_at TIMESTAMPTZ,
    approved_by UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS therapy.patient_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id),
    current_therapist_id UUID,
    origin TEXT NOT NULL DEFAULT 'platform' CHECK (origin IN ('platform', 'platform_assigned', 'clinic', 'therapist')),
    clinic_id UUID REFERENCES therapy.clinics(id),
    assigned_by_admin_id UUID,
    assigned_at TIMESTAMPTZ,
    phone TEXT,
    photo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_active BOOLEAN DEFAULT true
);

-- ======================== Clinic Config (3) ========================

CREATE TABLE IF NOT EXISTS therapy.clinic_settings (
    clinic_id UUID PRIMARY KEY REFERENCES therapy.clinics(id),
    bank_name TEXT,
    bank_agency TEXT,
    bank_account TEXT,
    pix_key TEXT,
    notification_email_to TEXT,
    default_commission_pct_clinic_sourced DECIMAL(5,2) DEFAULT 30.00,
    default_commission_pct_therapist_sourced DECIMAL(5,2) DEFAULT 10.00
);

CREATE TABLE IF NOT EXISTS therapy.clinic_therapist_config (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id),
    therapist_id UUID NOT NULL,
    pricing_policy TEXT NOT NULL DEFAULT 'therapist_controls' CHECK (pricing_policy IN ('clinic_controls', 'therapist_controls')),
    commission_override_clinic_sourced DECIMAL(5,2),
    commission_override_therapist_sourced DECIMAL(5,2),
    clinic_set_default_price DECIMAL(10,2),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(clinic_id, therapist_id)
);

CREATE TABLE IF NOT EXISTS therapy.clinic_branding (
    clinic_id UUID PRIMARY KEY REFERENCES therapy.clinics(id),
    primary_color TEXT DEFAULT '#8b5cf6',
    secondary_color TEXT DEFAULT '#6d28d9',
    logo_url TEXT,
    favicon_url TEXT
);

-- ======================== Commission + Pricing (2) ========================

CREATE TABLE IF NOT EXISTS therapy.platform_commission_overrides (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('clinic', 'therapist')),
    target_id UUID NOT NULL,
    custom_commission_pct DECIMAL(5,2) NOT NULL,
    set_by_admin_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(target_type, target_id)
);

CREATE TABLE IF NOT EXISTS therapy.patient_pricing (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    clinic_id UUID,
    custom_price DECIMAL(10,2) NOT NULL,
    set_by TEXT NOT NULL CHECK (set_by IN ('therapist', 'clinic_admin', 'platform_admin')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(therapist_id, patient_id)
);

-- ======================== Therapist Config (1) ========================

CREATE TABLE IF NOT EXISTS therapy.therapist_settings (
    therapist_id UUID PRIMARY KEY,
    bank_name TEXT,
    bank_agency TEXT,
    bank_account TEXT,
    pix_key TEXT,
    openai_api_key TEXT,
    google_connected BOOLEAN DEFAULT false,
    google_refresh_token TEXT,
    notification_email_to TEXT
);

-- ======================== Scheduling (3) ========================

CREATE TABLE IF NOT EXISTS therapy.availability_slots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    day_of_week INT CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_recurring BOOLEAN DEFAULT true,
    specific_date DATE,
    is_blocked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.recurring_schedules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    clinic_id UUID,
    frequency TEXT NOT NULL DEFAULT 'weekly' CHECK (frequency IN ('weekly', 'biweekly', 'monthly', 'custom')),
    custom_interval_weeks INT,
    day_of_week INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TIME NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 50,
    start_date DATE NOT NULL,
    end_condition TEXT NOT NULL DEFAULT 'indefinite' CHECK (end_condition IN ('indefinite', 'after_n_occurrences', 'on_date')),
    end_after_n INT,
    end_on_date DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'ended')),
    created_by_type TEXT NOT NULL CHECK (created_by_type IN ('therapist', 'clinic_admin', 'patient_request')),
    created_by_user_id UUID NOT NULL,
    approved_by_user_id UUID,
    paused_at TIMESTAMPTZ,
    resumed_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    total_completed INT DEFAULT 0,
    total_absences INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    clinic_id UUID,
    recurring_schedule_id UUID REFERENCES therapy.recurring_schedules(id),
    patient_origin TEXT NOT NULL DEFAULT 'platform' CHECK (patient_origin IN ('clinic_sourced', 'therapist_sourced', 'independent', 'platform_assigned')),
    session_price_applied DECIMAL(10,2),
    platform_fee_pct_applied DECIMAL(5,2),
    clinic_commission_pct_applied DECIMAL(5,2),
    scheduled_start TIMESTAMPTZ NOT NULL,
    scheduled_end TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'in_progress', 'paused', 'completed', 'cancelled', 'late_cancelled', 'no_show', 'payment_pending', 'payment_failed')),
    video_room_id UUID,
    meeting_link TEXT,
    google_event_id TEXT,
    payment_id TEXT,
    is_auto_generated BOOLEAN DEFAULT false,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    patient_attended BOOLEAN,
    therapist_attended BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Video / Session (5) ========================

CREATE TABLE IF NOT EXISTS therapy.video_rooms (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL UNIQUE,
    livekit_room_name TEXT,
    room_token TEXT,
    meeting_url TEXT NOT NULL,
    accessible_from TIMESTAMPTZ NOT NULL,
    accessible_until TIMESTAMPTZ NOT NULL,
    reopen_until TIMESTAMPTZ,
    reopen_count INT DEFAULT 0,
    reopen_button_visible_until TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'waiting', 'active', 'paused', 'closed', 'auto_finalized', 'reopened')),
    total_pauses INT DEFAULT 0,
    therapist_joined_at TIMESTAMPTZ,
    patient_joined_at TIMESTAMPTZ,
    session_started_at TIMESTAMPTZ,
    session_ended_at TIMESTAMPTZ,
    last_paused_at TIMESTAMPTZ,
    last_resumed_at TIMESTAMPTZ,
    last_reopened_at TIMESTAMPTZ,
    auto_finalized_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.session_audio_segments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_room_id UUID NOT NULL REFERENCES therapy.video_rooms(id) ON DELETE CASCADE,
    segment_number INT NOT NULL,
    segment_type TEXT NOT NULL DEFAULT 'initial' CHECK (segment_type IN ('initial', 'resumed', 'reopened')),
    audio_file_url TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    transcription_text TEXT,
    is_transcribed BOOLEAN DEFAULT false,
    download_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.session_interruptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_room_id UUID NOT NULL REFERENCES therapy.video_rooms(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('pause', 'resume', 'disconnect', 'reconnect', 'reopen', 'end')),
    participant_type TEXT NOT NULL CHECK (participant_type IN ('therapist', 'patient', 'system')),
    participant_user_id UUID,
    reason TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    interruption_duration_seconds INT
);

CREATE TABLE IF NOT EXISTS therapy.session_records (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL UNIQUE,
    combined_transcript_text TEXT,
    therapist_notes_private TEXT,
    total_segments INT DEFAULT 1,
    ai_generated_at TIMESTAMPTZ,
    audio_deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.session_observations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
    observation_text TEXT NOT NULL,
    is_initial BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

-- ======================== Clinical / AI (5) ========================

CREATE TABLE IF NOT EXISTS therapy.session_summary_versions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
    track TEXT NOT NULL CHECK (track IN ('base', 'clinical')),
    version_number INT NOT NULL,
    summary TEXT NOT NULL,
    key_points TEXT[],
    tags TEXT[],
    source TEXT NOT NULL DEFAULT 'ai_generated' CHECK (source IN ('ai_generated', 'ai_auto_fallback', 'manual_edit')),
    observation_snapshot_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.patient_session_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_record_id UUID NOT NULL REFERENCES therapy.session_records(id) ON DELETE CASCADE,
    patient_id UUID NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.clinical_longitudinal_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    version_number INT NOT NULL,
    narrative_summary TEXT NOT NULL,
    recurring_themes TEXT[],
    progress_timeline TEXT[],
    unresolved_topics TEXT[],
    observation_insights TEXT,
    session_count_at_generation INT NOT NULL,
    clinical_summary_version_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.patient_longitudinal_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    version_number INT NOT NULL,
    narrative_summary TEXT NOT NULL,
    recurring_themes TEXT[],
    progress_reflection TEXT[],
    ongoing_topics TEXT[],
    session_count_at_generation INT NOT NULL,
    base_summary_version_ids UUID[],
    patient_note_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.patient_longitudinal_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    longitudinal_analysis_id UUID REFERENCES therapy.clinical_longitudinal_analyses(id),
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Financial (6) ========================

CREATE TABLE IF NOT EXISTS therapy.wallets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id UUID NOT NULL,
    owner_type TEXT NOT NULL CHECK (owner_type IN ('patient', 'therapist', 'clinic')),
    balance DECIMAL(14,2) NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT now(),
    UNIQUE(owner_id, owner_type)
);

CREATE TABLE IF NOT EXISTS therapy.wallet_movements (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    wallet_id UUID NOT NULL REFERENCES therapy.wallets(id),
    type TEXT NOT NULL CHECK (type IN ('credit', 'debit')),
    amount DECIMAL(10,2) NOT NULL,
    reference_type TEXT NOT NULL CHECK (reference_type IN ('session_commission', 'voluntary_transfer', 'withdrawal', 'refund', 'top_up', 'no_show_fee')),
    reference_id UUID,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    patient_origin TEXT NOT NULL,
    gross_amount DECIMAL(10,2) NOT NULL,
    platform_fee_pct DECIMAL(5,2) NOT NULL,
    platform_fee_amount DECIMAL(10,2) NOT NULL,
    clinic_commission_pct DECIMAL(5,2),
    clinic_share_amount DECIMAL(10,2),
    therapist_share_amount DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pre_authorized' CHECK (status IN ('pre_authorized', 'captured', 'refunded', 'failed', 'released')),
    gateway_ref TEXT,
    pre_authorized_at TIMESTAMPTZ,
    captured_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.clinic_transfers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id),
    therapist_id UUID NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    reason TEXT NOT NULL,
    initiated_by_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.payouts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    recipient_id UUID NOT NULL,
    recipient_type TEXT NOT NULL CHECK (recipient_type IN ('patient', 'therapist', 'clinic')),
    amount DECIMAL(10,2) NOT NULL,
    fee_pct DECIMAL(5,2) NOT NULL DEFAULT 2.00,
    fee_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    bank_details_snapshot JSONB,
    requested_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.refund_requests (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    transaction_id UUID NOT NULL REFERENCES therapy.transactions(id),
    appointment_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    reviewed_by_admin_id UUID,
    review_response TEXT,
    refund_amount DECIMAL(10,2) NOT NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Reviews (3) ========================

CREATE TABLE IF NOT EXISTS therapy.reviews (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    therapist_id UUID NOT NULL,
    clinic_id UUID,
    star_rating INT NOT NULL CHECK (star_rating BETWEEN 1 AND 5),
    review_text TEXT,
    tags TEXT[],
    is_flagged BOOLEAN DEFAULT false,
    flagged_by_therapist_id UUID,
    flagged_reason TEXT,
    is_hidden BOOLEAN DEFAULT false,
    hidden_by_admin_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(patient_id, therapist_id)
);

CREATE TABLE IF NOT EXISTS therapy.clinic_reviews (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id),
    star_rating INT NOT NULL CHECK (star_rating BETWEEN 1 AND 5),
    review_text TEXT,
    tags TEXT[],
    is_flagged BOOLEAN DEFAULT false,
    flagged_by_clinic_admin_id UUID,
    flagged_reason TEXT,
    is_hidden BOOLEAN DEFAULT false,
    hidden_by_admin_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(patient_id, clinic_id)
);

CREATE TABLE IF NOT EXISTS therapy.review_responses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    review_id UUID REFERENCES therapy.reviews(id),
    clinic_review_id UUID REFERENCES therapy.clinic_reviews(id),
    responder_id UUID NOT NULL,
    response_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CHECK (review_id IS NOT NULL OR clinic_review_id IS NOT NULL)
);

-- ======================== Messaging (5) ========================

CREATE TABLE IF NOT EXISTS therapy.conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'human' CHECK (mode IN ('human', 'ai_managed', 'hybrid')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_message_at TIMESTAMPTZ,
    is_archived BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS therapy.conversation_participants (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES therapy.conversations(id) ON DELETE CASCADE,
    participant_type TEXT NOT NULL CHECK (participant_type IN ('user', 'clinic', 'platform_support')),
    participant_id UUID,
    clinic_id UUID,
    last_read_message_id UUID,
    is_muted BOOLEAN DEFAULT false,
    is_deleted BOOLEAN DEFAULT false,
    is_blocked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(conversation_id, participant_id, participant_type)
);

CREATE TABLE IF NOT EXISTS therapy.messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES therapy.conversations(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL CHECK (sender_type IN ('user', 'clinic_entity', 'platform_support', 'ai_agent')),
    sender_user_id UUID,
    sender_clinic_id UUID,
    message_type TEXT NOT NULL DEFAULT 'text' CHECK (message_type IN ('text', 'system', 'ai', 'image', 'audio')),
    content TEXT,
    file_url TEXT,
    file_type TEXT,
    file_size INT,
    ai_processed_content TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.message_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES therapy.conversations(id),
    message_id UUID REFERENCES therapy.messages(id),
    reported_by_user_id UUID NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'resolved')),
    reviewed_by_admin_id UUID,
    resolution TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS therapy.user_blocks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    blocker_user_id UUID NOT NULL,
    blocked_user_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(blocker_user_id, blocked_user_id)
);

-- ======================== Config (2) ========================

CREATE TABLE IF NOT EXISTS therapy.platform_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.platform_settings_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    setting_key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT NOT NULL,
    changed_by_admin_id UUID NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT now()
);

-- ======================== Action Log (1) ========================

CREATE TABLE IF NOT EXISTS therapy.action_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL,
    tipo_acao TEXT NOT NULL,
    tipo_entidade TEXT NOT NULL,
    entidade_id TEXT,
    descricao TEXT,
    detalhes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 3. INDEXES
-- -----------------------------------------------------------------

-- Identity
CREATE INDEX IF NOT EXISTS idx_therapist_profiles_clinic_id ON therapy.therapist_profiles(clinic_id);
CREATE INDEX IF NOT EXISTS idx_therapist_profiles_is_approved ON therapy.therapist_profiles(is_approved);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_current_therapist ON therapy.patient_profiles(current_therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_clinic_id ON therapy.patient_profiles(clinic_id);
CREATE INDEX IF NOT EXISTS idx_patient_profiles_origin ON therapy.patient_profiles(origin);

-- Clinic Config
CREATE INDEX IF NOT EXISTS idx_clinic_therapist_config_clinic ON therapy.clinic_therapist_config(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_therapist_config_therapist ON therapy.clinic_therapist_config(therapist_id);

-- Commission + Pricing
CREATE INDEX IF NOT EXISTS idx_platform_commission_target ON therapy.platform_commission_overrides(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_patient_pricing_therapist ON therapy.patient_pricing(therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_pricing_patient ON therapy.patient_pricing(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_pricing_clinic ON therapy.patient_pricing(clinic_id);

-- Scheduling
CREATE INDEX IF NOT EXISTS idx_availability_therapist ON therapy.availability_slots(therapist_id);
CREATE INDEX IF NOT EXISTS idx_availability_clinic ON therapy.availability_slots(clinic_id);
CREATE INDEX IF NOT EXISTS idx_availability_day ON therapy.availability_slots(day_of_week);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_therapist_status ON therapy.recurring_schedules(therapist_id, status);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_patient ON therapy.recurring_schedules(patient_id);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_clinic ON therapy.recurring_schedules(clinic_id);
CREATE INDEX IF NOT EXISTS idx_appointments_therapist_start ON therapy.appointments(therapist_id, scheduled_start);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON therapy.appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_clinic ON therapy.appointments(clinic_id);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON therapy.appointments(status);
CREATE INDEX IF NOT EXISTS idx_appointments_recurring ON therapy.appointments(recurring_schedule_id);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled_start ON therapy.appointments(scheduled_start);

-- Video / Session
CREATE INDEX IF NOT EXISTS idx_video_rooms_appointment ON therapy.video_rooms(appointment_id);
CREATE INDEX IF NOT EXISTS idx_video_rooms_status ON therapy.video_rooms(status);
CREATE INDEX IF NOT EXISTS idx_session_audio_segments_room ON therapy.session_audio_segments(video_room_id);
CREATE INDEX IF NOT EXISTS idx_session_interruptions_room ON therapy.session_interruptions(video_room_id);
CREATE INDEX IF NOT EXISTS idx_session_records_appointment ON therapy.session_records(appointment_id);
CREATE INDEX IF NOT EXISTS idx_session_observations_record ON therapy.session_observations(session_record_id);

-- Clinical / AI
CREATE INDEX IF NOT EXISTS idx_session_summary_versions_record_track ON therapy.session_summary_versions(session_record_id, track);
CREATE INDEX IF NOT EXISTS idx_patient_session_notes_record ON therapy.patient_session_notes(session_record_id);
CREATE INDEX IF NOT EXISTS idx_patient_session_notes_patient ON therapy.patient_session_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_clinical_longitudinal_patient ON therapy.clinical_longitudinal_analyses(patient_id);
CREATE INDEX IF NOT EXISTS idx_clinical_longitudinal_therapist ON therapy.clinical_longitudinal_analyses(therapist_id);
CREATE INDEX IF NOT EXISTS idx_clinical_longitudinal_clinic ON therapy.clinical_longitudinal_analyses(clinic_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_patient ON therapy.patient_longitudinal_analyses(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_therapist ON therapy.patient_longitudinal_analyses(therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_notes_patient ON therapy.patient_longitudinal_notes(patient_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_notes_therapist ON therapy.patient_longitudinal_notes(therapist_id);
CREATE INDEX IF NOT EXISTS idx_patient_longitudinal_notes_analysis ON therapy.patient_longitudinal_notes(longitudinal_analysis_id);

-- Financial
CREATE INDEX IF NOT EXISTS idx_wallets_owner ON therapy.wallets(owner_id, owner_type);
CREATE INDEX IF NOT EXISTS idx_wallet_movements_wallet_created ON therapy.wallet_movements(wallet_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wallet_movements_reference ON therapy.wallet_movements(reference_type, reference_id);
CREATE INDEX IF NOT EXISTS idx_transactions_appointment ON therapy.transactions(appointment_id);
CREATE INDEX IF NOT EXISTS idx_transactions_patient ON therapy.transactions(patient_id);
CREATE INDEX IF NOT EXISTS idx_transactions_therapist ON therapy.transactions(therapist_id);
CREATE INDEX IF NOT EXISTS idx_transactions_clinic ON therapy.transactions(clinic_id);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON therapy.transactions(status);
CREATE INDEX IF NOT EXISTS idx_clinic_transfers_clinic ON therapy.clinic_transfers(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_transfers_therapist ON therapy.clinic_transfers(therapist_id);
CREATE INDEX IF NOT EXISTS idx_payouts_recipient ON therapy.payouts(recipient_id, recipient_type);
CREATE INDEX IF NOT EXISTS idx_payouts_status ON therapy.payouts(status);
CREATE INDEX IF NOT EXISTS idx_refund_requests_transaction ON therapy.refund_requests(transaction_id);
CREATE INDEX IF NOT EXISTS idx_refund_requests_patient ON therapy.refund_requests(patient_id);
CREATE INDEX IF NOT EXISTS idx_refund_requests_status ON therapy.refund_requests(status);

-- Reviews
CREATE INDEX IF NOT EXISTS idx_reviews_therapist ON therapy.reviews(therapist_id);
CREATE INDEX IF NOT EXISTS idx_reviews_patient ON therapy.reviews(patient_id);
CREATE INDEX IF NOT EXISTS idx_reviews_clinic ON therapy.reviews(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_reviews_clinic ON therapy.clinic_reviews(clinic_id);
CREATE INDEX IF NOT EXISTS idx_clinic_reviews_patient ON therapy.clinic_reviews(patient_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_review ON therapy.review_responses(review_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_clinic_review ON therapy.review_responses(clinic_review_id);

-- Messaging
CREATE INDEX IF NOT EXISTS idx_conversation_participants_conversation ON therapy.conversation_participants(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_user ON therapy.conversation_participants(participant_id);
CREATE INDEX IF NOT EXISTS idx_conversation_participants_clinic ON therapy.conversation_participants(clinic_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON therapy.messages(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON therapy.messages(sender_user_id);
CREATE INDEX IF NOT EXISTS idx_message_reports_conversation ON therapy.message_reports(conversation_id);
CREATE INDEX IF NOT EXISTS idx_message_reports_status ON therapy.message_reports(status);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker ON therapy.user_blocks(blocker_user_id);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON therapy.user_blocks(blocked_user_id);

-- Config
CREATE INDEX IF NOT EXISTS idx_platform_settings_history_key ON therapy.platform_settings_history(setting_key);

-- Action Log
CREATE INDEX IF NOT EXISTS idx_action_log_user ON therapy.action_log(user_id);
CREATE INDEX IF NOT EXISTS idx_action_log_entidade ON therapy.action_log(tipo_entidade, entidade_id);
CREATE INDEX IF NOT EXISTS idx_action_log_created ON therapy.action_log(created_at DESC);

-- -----------------------------------------------------------------
-- 4. UPDATED_AT TRIGGERS
-- -----------------------------------------------------------------

-- clinics
CREATE OR REPLACE TRIGGER set_updated_at_clinics
    BEFORE UPDATE ON therapy.clinics
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- therapist_profiles
CREATE OR REPLACE TRIGGER set_updated_at_therapist_profiles
    BEFORE UPDATE ON therapy.therapist_profiles
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_profiles
CREATE OR REPLACE TRIGGER set_updated_at_patient_profiles
    BEFORE UPDATE ON therapy.patient_profiles
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- clinic_therapist_config
CREATE OR REPLACE TRIGGER set_updated_at_clinic_therapist_config
    BEFORE UPDATE ON therapy.clinic_therapist_config
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- platform_commission_overrides
CREATE OR REPLACE TRIGGER set_updated_at_platform_commission_overrides
    BEFORE UPDATE ON therapy.platform_commission_overrides
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_pricing
CREATE OR REPLACE TRIGGER set_updated_at_patient_pricing
    BEFORE UPDATE ON therapy.patient_pricing
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- recurring_schedules
CREATE OR REPLACE TRIGGER set_updated_at_recurring_schedules
    BEFORE UPDATE ON therapy.recurring_schedules
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- appointments
CREATE OR REPLACE TRIGGER set_updated_at_appointments
    BEFORE UPDATE ON therapy.appointments
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- session_observations
CREATE OR REPLACE TRIGGER set_updated_at_session_observations
    BEFORE UPDATE ON therapy.session_observations
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_session_notes
CREATE OR REPLACE TRIGGER set_updated_at_patient_session_notes
    BEFORE UPDATE ON therapy.patient_session_notes
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- patient_longitudinal_notes
CREATE OR REPLACE TRIGGER set_updated_at_patient_longitudinal_notes
    BEFORE UPDATE ON therapy.patient_longitudinal_notes
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- refund_requests
CREATE OR REPLACE TRIGGER set_updated_at_refund_requests
    BEFORE UPDATE ON therapy.refund_requests
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- reviews
CREATE OR REPLACE TRIGGER set_updated_at_reviews
    BEFORE UPDATE ON therapy.reviews
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- clinic_reviews
CREATE OR REPLACE TRIGGER set_updated_at_clinic_reviews
    BEFORE UPDATE ON therapy.clinic_reviews
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- review_responses
CREATE OR REPLACE TRIGGER set_updated_at_review_responses
    BEFORE UPDATE ON therapy.review_responses
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- conversations
CREATE OR REPLACE TRIGGER set_updated_at_conversations
    BEFORE UPDATE ON therapy.conversations
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- messages
CREATE OR REPLACE TRIGGER set_updated_at_messages
    BEFORE UPDATE ON therapy.messages
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- platform_settings
CREATE OR REPLACE TRIGGER set_updated_at_platform_settings
    BEFORE UPDATE ON therapy.platform_settings
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- -----------------------------------------------------------------
-- 5. ROW LEVEL SECURITY
-- -----------------------------------------------------------------

-- Enable RLS on all tables
ALTER TABLE therapy.clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.therapist_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_therapist_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_branding ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.platform_commission_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_pricing ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.therapist_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.availability_slots ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.recurring_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.video_rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_audio_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_interruptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.session_summary_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_session_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinical_longitudinal_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_longitudinal_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.patient_longitudinal_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.wallet_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_transfers ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.refund_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.clinic_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.review_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.conversation_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.message_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.user_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.platform_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.platform_settings_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.action_log ENABLE ROW LEVEL SECURITY;

-- Service role bypass on all tables (backend handles authorization in Python)
CREATE POLICY "service_role_bypass" ON therapy.clinics FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.therapist_profiles FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_profiles FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_therapist_config FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_branding FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.platform_commission_overrides FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_pricing FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.therapist_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.availability_slots FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.recurring_schedules FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.appointments FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.video_rooms FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_audio_segments FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_interruptions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_records FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_observations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.session_summary_versions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_session_notes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinical_longitudinal_analyses FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_longitudinal_analyses FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.patient_longitudinal_notes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.wallets FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.wallet_movements FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.transactions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_transfers FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.payouts FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.refund_requests FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.reviews FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.clinic_reviews FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.review_responses FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.conversations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.conversation_participants FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.messages FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.message_reports FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.user_blocks FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.platform_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.platform_settings_history FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.action_log FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Role-based RLS policies (replace blanket authenticated_access)
-- Helpers: (SELECT therapy.current_user_role()), (SELECT therapy.current_clinic_id()), (SELECT auth.uid())

-- ======================== clinics ========================
CREATE POLICY "clinics_select" ON therapy.clinics FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR id = (SELECT therapy.current_clinic_id())
    OR is_approved = true
);
CREATE POLICY "clinics_insert" ON therapy.clinics FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) IN ('platform_admin', 'clinic_admin')
);
CREATE POLICY "clinics_update" ON therapy.clinics FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR (id = (SELECT therapy.current_clinic_id()) AND (SELECT therapy.current_user_role()) = 'clinic_admin')
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR (id = (SELECT therapy.current_clinic_id()) AND (SELECT therapy.current_user_role()) = 'clinic_admin')
);
CREATE POLICY "clinics_delete" ON therapy.clinics FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== therapist_profiles ========================
CREATE POLICY "therapist_profiles_select" ON therapy.therapist_profiles FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
    OR clinic_id = (SELECT therapy.current_clinic_id())
    OR (is_approved = true AND is_active = true)
);
CREATE POLICY "therapist_profiles_write" ON therapy.therapist_profiles FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
);

-- ======================== patient_profiles ========================
CREATE POLICY "patient_profiles_select" ON therapy.patient_profiles FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.patient_id = patient_profiles.user_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);
CREATE POLICY "patient_profiles_write" ON therapy.patient_profiles FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
);

-- ======================== appointments ========================
CREATE POLICY "appointments_select" ON therapy.appointments FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "appointments_write" ON therapy.appointments FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "appointments_update" ON therapy.appointments FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "appointments_delete" ON therapy.appointments FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);

-- ======================== availability_slots ========================
CREATE POLICY "availability_slots_select" ON therapy.availability_slots FOR SELECT TO authenticated USING (true);
CREATE POLICY "availability_slots_write" ON therapy.availability_slots FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
);
CREATE POLICY "availability_slots_update" ON therapy.availability_slots FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
);
CREATE POLICY "availability_slots_delete" ON therapy.availability_slots FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== recurring_schedules ========================
CREATE POLICY "recurring_schedules_access" ON therapy.recurring_schedules FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);

-- ======================== video_rooms ========================
CREATE POLICY "video_rooms_access" ON therapy.video_rooms FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = video_rooms.appointment_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = video_rooms.appointment_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
);

-- ======================== session_records ========================
CREATE POLICY "session_records_access" ON therapy.session_records FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = session_records.appointment_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.appointments a
        WHERE a.id = session_records.appointment_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== session_observations ========================
CREATE POLICY "session_observations_access" ON therapy.session_observations FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_observations.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_observations.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== session_audio_segments ========================
CREATE POLICY "session_audio_segments_access" ON therapy.session_audio_segments FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.video_rooms vr
        JOIN therapy.appointments a ON a.id = vr.appointment_id
        WHERE vr.id = session_audio_segments.video_room_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.video_rooms vr
        JOIN therapy.appointments a ON a.id = vr.appointment_id
        WHERE vr.id = session_audio_segments.video_room_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== session_summary_versions ========================
CREATE POLICY "session_summary_versions_access" ON therapy.session_summary_versions FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_summary_versions.session_record_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = session_summary_versions.session_record_id
          AND (a.therapist_id = (SELECT auth.uid()) OR a.patient_id = (SELECT auth.uid()))
    )
);

-- ======================== session_interruptions ========================
CREATE POLICY "session_interruptions_access" ON therapy.session_interruptions FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_user_id = (SELECT auth.uid())
);

-- ======================== patient_session_notes ========================
CREATE POLICY "patient_session_notes_access" ON therapy.patient_session_notes FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = patient_session_notes.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.session_records sr
        JOIN therapy.appointments a ON a.id = sr.appointment_id
        WHERE sr.id = patient_session_notes.session_record_id
          AND a.therapist_id = (SELECT auth.uid())
    )
);

-- ======================== clinical_longitudinal_analyses ========================
CREATE POLICY "clinical_longitudinal_analyses_access" ON therapy.clinical_longitudinal_analyses FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);

-- ======================== patient_longitudinal_analyses ========================
CREATE POLICY "patient_longitudinal_analyses_access" ON therapy.patient_longitudinal_analyses FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== patient_longitudinal_notes ========================
CREATE POLICY "patient_longitudinal_notes_access" ON therapy.patient_longitudinal_notes FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== wallets ========================
CREATE POLICY "wallets_select" ON therapy.wallets FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR owner_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND owner_type = 'clinic' AND owner_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "wallets_write" ON therapy.wallets FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "wallets_update" ON therapy.wallets FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "wallets_delete" ON therapy.wallets FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== wallet_movements ========================
CREATE POLICY "wallet_movements_select" ON therapy.wallet_movements FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.wallets w
        WHERE w.id = wallet_movements.wallet_id
          AND w.owner_id = (SELECT auth.uid())
    )
);
CREATE POLICY "wallet_movements_write" ON therapy.wallet_movements FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== transactions ========================
CREATE POLICY "transactions_select" ON therapy.transactions FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "transactions_write" ON therapy.transactions FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "transactions_update" ON therapy.transactions FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_transfers ========================
CREATE POLICY "clinic_transfers_access" ON therapy.clinic_transfers FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== payouts ========================
CREATE POLICY "payouts_access" ON therapy.payouts FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR recipient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR recipient_id = (SELECT auth.uid())
);

-- ======================== refund_requests ========================
CREATE POLICY "refund_requests_access" ON therapy.refund_requests FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== reviews ========================
CREATE POLICY "reviews_select" ON therapy.reviews FOR SELECT TO authenticated USING (true);
CREATE POLICY "reviews_write" ON therapy.reviews FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "reviews_update" ON therapy.reviews FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "reviews_delete" ON therapy.reviews FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_reviews ========================
CREATE POLICY "clinic_reviews_select" ON therapy.clinic_reviews FOR SELECT TO authenticated USING (true);
CREATE POLICY "clinic_reviews_write" ON therapy.clinic_reviews FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "clinic_reviews_update" ON therapy.clinic_reviews FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR patient_id = (SELECT auth.uid())
);
CREATE POLICY "clinic_reviews_delete" ON therapy.clinic_reviews FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== review_responses ========================
CREATE POLICY "review_responses_access" ON therapy.review_responses FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR responder_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR responder_id = (SELECT auth.uid())
);

-- ======================== conversations ========================
CREATE POLICY "conversations_access" ON therapy.conversations FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = conversations.id
          AND cp.participant_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = conversations.id
          AND cp.participant_id = (SELECT auth.uid())
    )
);

-- ======================== messages ========================
CREATE POLICY "messages_access" ON therapy.messages FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = messages.conversation_id
          AND cp.participant_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp
        WHERE cp.conversation_id = messages.conversation_id
          AND cp.participant_id = (SELECT auth.uid())
    )
);

-- ======================== conversation_participants ========================
CREATE POLICY "conversation_participants_access" ON therapy.conversation_participants FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp2
        WHERE cp2.conversation_id = conversation_participants.conversation_id
          AND cp2.participant_id = (SELECT auth.uid())
    )
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR participant_id = (SELECT auth.uid())
    OR EXISTS (
        SELECT 1 FROM therapy.conversation_participants cp2
        WHERE cp2.conversation_id = conversation_participants.conversation_id
          AND cp2.participant_id = (SELECT auth.uid())
    )
);

-- ======================== message_reports ========================
CREATE POLICY "message_reports_access" ON therapy.message_reports FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR reported_by_user_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR reported_by_user_id = (SELECT auth.uid())
);

-- ======================== user_blocks ========================
CREATE POLICY "user_blocks_access" ON therapy.user_blocks FOR ALL TO authenticated USING (
    blocker_user_id = (SELECT auth.uid())
) WITH CHECK (
    blocker_user_id = (SELECT auth.uid())
);

-- ======================== clinic_settings ========================
CREATE POLICY "clinic_settings_select" ON therapy.clinic_settings FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR clinic_id = (SELECT therapy.current_clinic_id())
);
CREATE POLICY "clinic_settings_write" ON therapy.clinic_settings FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_settings_update" ON therapy.clinic_settings FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_settings_delete" ON therapy.clinic_settings FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_branding ========================
CREATE POLICY "clinic_branding_select" ON therapy.clinic_branding FOR SELECT TO authenticated USING (true);
CREATE POLICY "clinic_branding_write" ON therapy.clinic_branding FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_branding_update" ON therapy.clinic_branding FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
);
CREATE POLICY "clinic_branding_delete" ON therapy.clinic_branding FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== clinic_therapist_config ========================
CREATE POLICY "clinic_therapist_config_access" ON therapy.clinic_therapist_config FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR ((SELECT therapy.current_user_role()) = 'clinic_admin' AND clinic_id = (SELECT therapy.current_clinic_id()))
    OR therapist_id = (SELECT auth.uid())
);

-- ======================== therapist_settings ========================
CREATE POLICY "therapist_settings_access" ON therapy.therapist_settings FOR ALL TO authenticated USING (
    therapist_id = (SELECT auth.uid())
) WITH CHECK (
    therapist_id = (SELECT auth.uid())
);

-- ======================== patient_pricing ========================
CREATE POLICY "patient_pricing_access" ON therapy.patient_pricing FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR therapist_id = (SELECT auth.uid())
    OR patient_id = (SELECT auth.uid())
);

-- ======================== platform_commission_overrides ========================
CREATE POLICY "platform_commission_overrides_access" ON therapy.platform_commission_overrides FOR ALL TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== platform_settings ========================
CREATE POLICY "platform_settings_select" ON therapy.platform_settings FOR SELECT TO authenticated USING (true);
CREATE POLICY "platform_settings_write" ON therapy.platform_settings FOR INSERT TO authenticated WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "platform_settings_update" ON therapy.platform_settings FOR UPDATE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
) WITH CHECK (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);
CREATE POLICY "platform_settings_delete" ON therapy.platform_settings FOR DELETE TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== platform_settings_history ========================
CREATE POLICY "platform_settings_history_select" ON therapy.platform_settings_history FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
);

-- ======================== action_log ========================
CREATE POLICY "action_log_select" ON therapy.action_log FOR SELECT TO authenticated USING (
    (SELECT therapy.current_user_role()) = 'platform_admin'
    OR user_id = (SELECT auth.uid())
);
CREATE POLICY "action_log_insert" ON therapy.action_log FOR INSERT TO authenticated WITH CHECK (
    user_id = (SELECT auth.uid())
);

-- -----------------------------------------------------------------
-- 6. SEED DATA — Platform Settings
-- -----------------------------------------------------------------

INSERT INTO therapy.platform_settings (key, value) VALUES
    ('app_name', 'Therapy Platform'),
    ('global_commission_rate', '10.00'),
    ('session_pre_access_minutes', '15'),
    ('session_post_access_minutes', '45'),
    ('session_reopen_duration_minutes', '50'),
    ('session_reopen_button_visibility_minutes', '60'),
    ('refund_enabled', 'false'),
    ('refund_window_days', '7'),
    ('cancellation_cutoff_hours', '24'),
    ('withdrawal_min_amount', '10.00'),
    ('withdrawal_fee_pct', '2.00'),
    ('audio_retention_hours', '24'),
    ('longitudinal_min_sessions', '4'),
    ('message_notification_delay_minutes', '5'),
    ('no_show_charge_pct', '50.00'),
    ('ai_prompt_transcription_instructions', 'Transcreva o audio da sessao de terapia em portugues brasileiro. Identifique os falantes como Terapeuta e Paciente.'),
    ('ai_prompt_base_summary', 'Voce e um assistente que resume sessoes de terapia para o paciente. Gere um resumo conciso e factual da sessao baseado apenas na transcricao. Nao inclua interpretacoes clinicas. Use um tom acolhedor e acessivel em portugues brasileiro.'),
    ('ai_prompt_clinical_summary', 'Voce e um assistente clinico para terapeutas. Gere um resumo clinico da sessao baseado na transcricao e nas observacoes do terapeuta. Inclua insights clinicos, padroes observados e pontos de atencao. Use linguagem tecnica apropriada em portugues brasileiro.'),
    ('ai_prompt_longitudinal_clinical', 'Voce e um assistente clinico. Sintetize todos os resumos clinicos e observacoes em uma analise longitudinal abrangente do caso. Identifique temas recorrentes, progresso, topicos nao resolvidos e insights clinicos. Use linguagem tecnica em portugues brasileiro.'),
    ('ai_prompt_longitudinal_patient', 'Voce e um assistente pessoal de jornada terapeutica. Sintetize os resumos das sessoes e as anotacoes pessoais do paciente em uma visao geral da jornada terapeutica. Use a segunda pessoa (voce) e um tom acolhedor e reflexivo. Ajude o paciente a perceber seus padroes e evolucao. Em portugues brasileiro.'),
    ('ai_prompt_tag_generation', 'Gere tags tematicas relevantes para esta sessao de terapia baseado no conteudo. Retorne como uma lista JSON de strings. Maximo 8 tags. Em portugues.')
ON CONFLICT (key) DO NOTHING;

-- -----------------------------------------------------------------
-- 7. PRODUCT SEED
-- -----------------------------------------------------------------

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Plataforma de Terapia',
    'therapy-platform',
    'Plataforma online de terapia: video, agendamento, prontuario digital e gestao financeira',
    '🧠',
    'http://localhost:8095',
    '#8b5cf6',
    true
) ON CONFLICT (slug) DO NOTHING;

-- -----------------------------------------------------------------
-- 8. FINAL GRANTS (ensure all objects have correct permissions)
-- -----------------------------------------------------------------

GRANT ALL ON ALL TABLES IN SCHEMA therapy TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA therapy TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA therapy TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA therapy TO anon, authenticated, service_role;

-- -----------------------------------------------------------------
-- DONE. Therapy platform schema is fully set up.
-- -----------------------------------------------------------------
