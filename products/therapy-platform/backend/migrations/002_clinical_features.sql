-- =====================================================================
-- 002 — Clinical Features: records, rooms, patient portal, invoicing,
--       WhatsApp, crisis detection, and therapist matching.
-- Run this AFTER 001_therapy_platform.sql on your Supabase project.
-- All objects live in the `therapy` schema.
-- =====================================================================

-- -----------------------------------------------------------------
-- 0. ENABLE pgvector EXTENSION (for therapist matching)
-- -----------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- -----------------------------------------------------------------
-- 1. TABLES — Clinical Records (4)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS therapy.anamnese (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    template_id UUID,
    queixa_principal TEXT,
    historia_pregressa TEXT,
    historico_familiar TEXT,
    medicacoes TEXT,
    observacoes TEXT,
    status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'concluida')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.treatment_plans (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    titulo TEXT NOT NULL,
    descricao TEXT,
    status TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'concluido', 'cancelado')),
    data_inicio DATE,
    data_revisao DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.treatment_plan_goals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES therapy.treatment_plans(id) ON DELETE CASCADE,
    descricao TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'em_progresso', 'concluido', 'cancelado')),
    prazo DATE,
    observacoes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.evolution_notes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    appointment_id UUID REFERENCES therapy.appointments(id),
    formato TEXT NOT NULL DEFAULT 'soap' CHECK (formato IN ('soap', 'livre')),
    subjetivo TEXT,
    objetivo TEXT,
    avaliacao TEXT,
    plano TEXT,
    conteudo_livre TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 2. TABLES — Room Management (2)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS therapy.rooms (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    clinic_id UUID NOT NULL REFERENCES therapy.clinics(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    capacidade INT DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.room_bookings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    room_id UUID NOT NULL REFERENCES therapy.rooms(id) ON DELETE CASCADE,
    appointment_id UUID NOT NULL REFERENCES therapy.appointments(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    horario_inicio TIME NOT NULL,
    horario_fim TIME NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 3. TABLES — Patient Portal (3)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS therapy.mood_entries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 10),
    emocoes TEXT[],
    nota TEXT,
    data DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.journal_entries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    titulo TEXT,
    conteudo TEXT NOT NULL,
    is_shared_with_therapist BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.homework_assignments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    titulo TEXT NOT NULL,
    descricao TEXT,
    data_limite DATE,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'em_andamento', 'concluido', 'revisado')),
    resposta_paciente TEXT,
    feedback_terapeuta TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 4. TABLES — Invoicing (1)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS therapy.invoices (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    transaction_id UUID NOT NULL REFERENCES therapy.transactions(id),
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    valor NUMERIC(12,2) NOT NULL,
    descricao TEXT,
    pdf_url TEXT,
    status TEXT NOT NULL DEFAULT 'gerada' CHECK (status IN ('gerada', 'enviada', 'cancelada')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 5. TABLES — WhatsApp (2)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS therapy.whatsapp_messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    appointment_id UUID REFERENCES therapy.appointments(id),
    destinatario_telefone TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('lembrete', 'confirmacao', 'cancelamento', 'custom')),
    conteudo TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'enviado' CHECK (status IN ('enviado', 'erro', 'entregue')),
    erro_mensagem TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS therapy.reminder_schedules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    tipo TEXT NOT NULL DEFAULT '24h_antes' CHECK (tipo IN ('24h_antes', '1h_antes', 'custom')),
    horas_antes INT DEFAULT 24,
    mensagem_template TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 6. TABLES — Crisis Detection (1)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS therapy.crisis_alerts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES therapy.patient_profiles(user_id),
    therapist_id UUID NOT NULL REFERENCES therapy.therapist_profiles(user_id),
    source_type TEXT NOT NULL CHECK (source_type IN ('evolution_note', 'journal', 'transcript')),
    source_id UUID NOT NULL,
    conteudo_flagged TEXT,
    palavras_detectadas TEXT[],
    severidade TEXT NOT NULL DEFAULT 'media' CHECK (severidade IN ('baixa', 'media', 'alta', 'critica')),
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'revisado', 'falso_positivo', 'encaminhado')),
    revisado_por UUID,
    revisado_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- 7. ALTER EXISTING TABLES
-- -----------------------------------------------------------------

-- Add room_id to appointments
ALTER TABLE therapy.appointments
    ADD COLUMN IF NOT EXISTS room_id UUID REFERENCES therapy.rooms(id);

-- Add matching columns to therapist_profiles
ALTER TABLE therapy.therapist_profiles
    ADD COLUMN IF NOT EXISTS matching_text TEXT,
    ADD COLUMN IF NOT EXISTS matching_embedding extensions.vector(1536);

-- Add matching and preference columns to patient_profiles
ALTER TABLE therapy.patient_profiles
    ADD COLUMN IF NOT EXISTS matching_text TEXT,
    ADD COLUMN IF NOT EXISTS matching_embedding extensions.vector(1536),
    ADD COLUMN IF NOT EXISTS therapy_needs TEXT[],
    ADD COLUMN IF NOT EXISTS preferred_approaches TEXT[];

-- -----------------------------------------------------------------
-- 8. INDEXES
-- -----------------------------------------------------------------

-- Clinical Records
CREATE INDEX IF NOT EXISTS idx_anamnese_patient ON therapy.anamnese(patient_id);
CREATE INDEX IF NOT EXISTS idx_anamnese_therapist ON therapy.anamnese(therapist_id);
CREATE INDEX IF NOT EXISTS idx_anamnese_status ON therapy.anamnese(status);
CREATE INDEX IF NOT EXISTS idx_treatment_plans_patient_status ON therapy.treatment_plans(patient_id, status);
CREATE INDEX IF NOT EXISTS idx_treatment_plans_therapist ON therapy.treatment_plans(therapist_id);
CREATE INDEX IF NOT EXISTS idx_treatment_plan_goals_plan ON therapy.treatment_plan_goals(plan_id);
CREATE INDEX IF NOT EXISTS idx_treatment_plan_goals_status ON therapy.treatment_plan_goals(status);
CREATE INDEX IF NOT EXISTS idx_evolution_notes_patient_therapist ON therapy.evolution_notes(patient_id, therapist_id);
CREATE INDEX IF NOT EXISTS idx_evolution_notes_appointment ON therapy.evolution_notes(appointment_id);

-- Room Management
CREATE INDEX IF NOT EXISTS idx_rooms_clinic ON therapy.rooms(clinic_id);
CREATE INDEX IF NOT EXISTS idx_rooms_is_active ON therapy.rooms(is_active);
CREATE INDEX IF NOT EXISTS idx_room_bookings_room ON therapy.room_bookings(room_id);
CREATE INDEX IF NOT EXISTS idx_room_bookings_appointment ON therapy.room_bookings(appointment_id);
CREATE INDEX IF NOT EXISTS idx_room_bookings_data ON therapy.room_bookings(data);

-- Patient Portal
CREATE INDEX IF NOT EXISTS idx_mood_entries_patient_data ON therapy.mood_entries(patient_id, data);
CREATE INDEX IF NOT EXISTS idx_journal_entries_patient_created ON therapy.journal_entries(patient_id, created_at);
CREATE INDEX IF NOT EXISTS idx_homework_assignments_patient_status ON therapy.homework_assignments(patient_id, status);
CREATE INDEX IF NOT EXISTS idx_homework_assignments_therapist_status ON therapy.homework_assignments(therapist_id, status);

-- Invoicing
CREATE INDEX IF NOT EXISTS idx_invoices_transaction ON therapy.invoices(transaction_id);
CREATE INDEX IF NOT EXISTS idx_invoices_therapist_status ON therapy.invoices(therapist_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_patient ON therapy.invoices(patient_id);

-- WhatsApp
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_appointment ON therapy.whatsapp_messages(appointment_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_status ON therapy.whatsapp_messages(status);
CREATE INDEX IF NOT EXISTS idx_reminder_schedules_therapist ON therapy.reminder_schedules(therapist_id);

-- Crisis Detection
CREATE INDEX IF NOT EXISTS idx_crisis_alerts_patient ON therapy.crisis_alerts(patient_id);
CREATE INDEX IF NOT EXISTS idx_crisis_alerts_therapist_status ON therapy.crisis_alerts(therapist_id, status);
CREATE INDEX IF NOT EXISTS idx_crisis_alerts_severidade ON therapy.crisis_alerts(severidade);
CREATE INDEX IF NOT EXISTS idx_crisis_alerts_source ON therapy.crisis_alerts(source_type, source_id);

-- Appointments room_id
CREATE INDEX IF NOT EXISTS idx_appointments_room ON therapy.appointments(room_id);

-- Embedding indexes (IVFFlat for fast approximate nearest-neighbor)
CREATE INDEX IF NOT EXISTS idx_therapist_profiles_embedding
    ON therapy.therapist_profiles
    USING ivfflat (matching_embedding extensions.vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_patient_profiles_embedding
    ON therapy.patient_profiles
    USING ivfflat (matching_embedding extensions.vector_cosine_ops)
    WITH (lists = 100);

-- -----------------------------------------------------------------
-- 9. UPDATED_AT TRIGGERS
-- -----------------------------------------------------------------

CREATE OR REPLACE TRIGGER set_updated_at_anamnese
    BEFORE UPDATE ON therapy.anamnese
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_treatment_plans
    BEFORE UPDATE ON therapy.treatment_plans
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_treatment_plan_goals
    BEFORE UPDATE ON therapy.treatment_plan_goals
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_evolution_notes
    BEFORE UPDATE ON therapy.evolution_notes
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_rooms
    BEFORE UPDATE ON therapy.rooms
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_mood_entries
    BEFORE UPDATE ON therapy.mood_entries
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_journal_entries
    BEFORE UPDATE ON therapy.journal_entries
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_homework_assignments
    BEFORE UPDATE ON therapy.homework_assignments
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_invoices
    BEFORE UPDATE ON therapy.invoices
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_reminder_schedules
    BEFORE UPDATE ON therapy.reminder_schedules
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_crisis_alerts
    BEFORE UPDATE ON therapy.crisis_alerts
    FOR EACH ROW EXECUTE FUNCTION therapy.set_updated_at();

-- -----------------------------------------------------------------
-- 10. ROW LEVEL SECURITY
-- -----------------------------------------------------------------

-- Enable RLS on all new tables
ALTER TABLE therapy.anamnese ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.treatment_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.treatment_plan_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.evolution_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.room_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.mood_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.homework_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.whatsapp_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.reminder_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE therapy.crisis_alerts ENABLE ROW LEVEL SECURITY;

-- Service role bypass on all new tables (backend handles authorization in Python)
CREATE POLICY "service_role_bypass" ON therapy.anamnese FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.treatment_plans FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.treatment_plan_goals FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.evolution_notes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.rooms FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.room_bookings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.mood_entries FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.journal_entries FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.homework_assignments FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.invoices FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.whatsapp_messages FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.reminder_schedules FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_bypass" ON therapy.crisis_alerts FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Authenticated basic access on all new tables (fine-grained auth enforced in Python)
CREATE POLICY "authenticated_access" ON therapy.anamnese FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.treatment_plans FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.treatment_plan_goals FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.evolution_notes FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.rooms FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.room_bookings FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.mood_entries FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.journal_entries FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.homework_assignments FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.invoices FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.whatsapp_messages FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.reminder_schedules FOR ALL TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "authenticated_access" ON therapy.crisis_alerts FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- -----------------------------------------------------------------
-- 11. MATCHING FUNCTION — Therapist Similarity Search
-- -----------------------------------------------------------------
-- Returns the top N most similar therapists to a given embedding vector.
-- Called from the backend: db.rpc("match_therapists", { ... })

CREATE OR REPLACE FUNCTION therapy.match_therapists(
    query_embedding extensions.vector(1536),
    match_threshold FLOAT DEFAULT 0.3,
    match_count INT DEFAULT 20
)
RETURNS TABLE (
    user_id UUID,
    similarity FLOAT
)
LANGUAGE sql STABLE
SET search_path = therapy, public, extensions
AS $$
    SELECT
        tp.user_id,
        1 - (tp.matching_embedding OPERATOR(extensions.<=>) query_embedding) AS similarity
    FROM therapy.therapist_profiles tp
    WHERE tp.matching_embedding IS NOT NULL
        AND tp.is_active = true
        AND tp.is_approved = true
        AND 1 - (tp.matching_embedding OPERATOR(extensions.<=>) query_embedding) > match_threshold
    ORDER BY tp.matching_embedding OPERATOR(extensions.<=>) query_embedding
    LIMIT match_count;
$$;

-- -----------------------------------------------------------------
-- 12. FINAL GRANTS (ensure all new objects have correct permissions)
-- -----------------------------------------------------------------

GRANT ALL ON ALL TABLES IN SCHEMA therapy TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA therapy TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA therapy TO anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA therapy TO anon, authenticated, service_role;

-- -----------------------------------------------------------------
-- DONE. Clinical features migration complete.
-- 13 new tables, 3 altered tables, 1 matching function, pgvector enabled.
-- -----------------------------------------------------------------
