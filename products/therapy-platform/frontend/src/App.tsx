import { lazy } from "react";
import { createProductApp } from "@noctusai/seed";
import { resolveSSORoles } from "@noctusai/lib";
import { AdminLayout, ClinicLayout, TherapistLayout, PatientLayout } from "@/layouts";
import { supabase } from "@/integrations/supabase/client";
import { useAuthStore } from "@/store/authStore";

// ── Lazy-loaded pages ───────────────────────────────────────

// Public
const Landing = lazy(() => import("./pages/Landing"));
const Register = lazy(() => import("./pages/Register"));
const Messages = lazy(() => import("./pages/Messages"));
const TermsOfUse = lazy(() => import("./pages/TermsOfUse"));
const PrivacyPolicy = lazy(() => import("./pages/PrivacyPolicy"));

// Admin
const AdminDashboard = lazy(() => import("./pages/admin/Dashboard"));
const AdminFinancials = lazy(() => import("./pages/admin/Financials"));
const AdminRefunds = lazy(() => import("./pages/admin/Refunds"));
const AdminTherapists = lazy(() => import("./pages/admin/Therapists"));
const AdminTherapistDetail = lazy(() => import("./pages/admin/TherapistDetail"));
const AdminClinics = lazy(() => import("./pages/admin/Clinics"));
const AdminClinicDetail = lazy(() => import("./pages/admin/ClinicDetail"));
const AdminPatients = lazy(() => import("./pages/admin/Patients"));
const AdminPatientDetail = lazy(() => import("./pages/admin/PatientDetail"));
const AdminAppointments = lazy(() => import("./pages/admin/Appointments"));
const AdminSettings = lazy(() => import("./pages/admin/Settings"));
const AdminAIPrompts = lazy(() => import("./pages/admin/AIPrompts"));
const AdminSupport = lazy(() => import("./pages/admin/Support"));
const AdminModeration = lazy(() => import("./pages/admin/Moderation"));
const AdminReviews = lazy(() => import("./pages/admin/Reviews"));
const AdminCrisisAlerts = lazy(() => import("./pages/therapist/CrisisAlerts"));

// Clinic
const ClinicDashboard = lazy(() => import("./pages/clinic/Dashboard"));
const ClinicFinancials = lazy(() => import("./pages/clinic/Financials"));
const ClinicTherapists = lazy(() => import("./pages/clinic/Therapists"));
const ClinicPatients = lazy(() => import("./pages/clinic/Patients"));
const ClinicSettings = lazy(() => import("./pages/clinic/Settings"));

// Therapist
const TherapistDashboard = lazy(() => import("./pages/therapist/Dashboard"));
const TherapistCalendar = lazy(() => import("./pages/therapist/Calendar"));
const TherapistAvailabilitySettings = lazy(() => import("./pages/therapist/AvailabilitySettings"));
const TherapistRecurringSchedules = lazy(() => import("./pages/therapist/RecurringSchedules"));
const TherapistSessionDetail = lazy(() => import("./pages/therapist/SessionDetail"));
const TherapistPatientProfile = lazy(() => import("./pages/therapist/PatientProfile"));
const TherapistFinancials = lazy(() => import("./pages/therapist/Financials"));
const TherapistPatients = lazy(() => import("./pages/therapist/Patients"));
const TherapistReviews = lazy(() => import("./pages/therapist/Reviews"));
const TherapistSettings = lazy(() => import("./pages/therapist/Settings"));
const TherapistClinicalRecords = lazy(() => import("./pages/therapist/ClinicalRecords"));
const TherapistHomeworkManager = lazy(() => import("./pages/therapist/HomeworkManager"));
const TherapistBiDashboard = lazy(() => import("./pages/therapist/BiDashboard"));
const TherapistCrisisAlerts = lazy(() => import("./pages/therapist/CrisisAlerts"));

// Patient
const PatientDashboard = lazy(() => import("./pages/patient/Dashboard"));
const PatientCalendar = lazy(() => import("./pages/patient/Calendar"));
const PatientRecurringSchedules = lazy(() => import("./pages/patient/RecurringSchedules"));
const PatientSessionHistory = lazy(() => import("./pages/patient/SessionHistory"));
const PatientSessionDetail = lazy(() => import("./pages/patient/SessionDetail"));
const PatientJourney = lazy(() => import("./pages/patient/Journey"));
const PatientWallet = lazy(() => import("./pages/patient/Wallet"));
const PatientPaymentMethods = lazy(() => import("./pages/patient/PaymentMethods"));
const PatientReviews = lazy(() => import("./pages/patient/Reviews"));
const PatientSettings = lazy(() => import("./pages/patient/Settings"));
const PatientMoodTracker = lazy(() => import("./pages/patient/MoodTracker"));
const PatientDiary = lazy(() => import("./pages/patient/Diary"));
const PatientHomework = lazy(() => import("./pages/patient/Homework"));
const PatientInvoices = lazy(() => import("./pages/patient/Invoices"));

// Session (full-screen — no layout)
const Session = lazy(() => import("./pages/Session"));

// Directory (any user — public + authenticated)
const TherapistDirectory = lazy(() => import("./pages/TherapistDirectory"));
const TherapistProfile = lazy(() => import("./pages/TherapistProfile"));
const ClinicDirectory = lazy(() => import("./pages/ClinicDirectory"));
const ClinicProfile = lazy(() => import("./pages/ClinicProfile"));

// ── Role resolver ──────────────────────────────────────────

function resolveTherapyRole(user: any): string {
  const meta = user?.user_metadata;
  if (!meta) return "paciente";
  // Shared SSO role resolution (org owner/admin or NoctusAI admin)
  const { isProductAdmin } = resolveSSORoles(meta);
  if (isProductAdmin) return "admin";
  // Direct registration (therapy-native users)
  return (meta.role as string) || "paciente";
}

// ── App via seed framework ─────────────────────────────────

export default createProductApp({
  supabase,
  useAuthStore,
  resolveRole: resolveTherapyRole,

  roleRoutes: {
    admin: {
      pathPrefix: "/admin",
      Layout: AdminLayout,
      routes: [
        { path: "/", component: AdminDashboard },
        { path: "/terapeutas", component: AdminTherapists },
        { path: "/terapeutas/:id", component: AdminTherapistDetail },
        { path: "/clinicas", component: AdminClinics },
        { path: "/clinicas/:id", component: AdminClinicDetail },
        { path: "/pacientes", component: AdminPatients },
        { path: "/pacientes/:id", component: AdminPatientDetail },
        { path: "/agendamentos", component: AdminAppointments },
        { path: "/financeiro", component: AdminFinancials },
        { path: "/reembolsos", component: AdminRefunds },
        { path: "/configuracoes", component: AdminSettings },
        { path: "/prompts-ia", component: AdminAIPrompts },
        { path: "/suporte", component: AdminSupport },
        { path: "/moderacao", component: AdminModeration },
        { path: "/alertas-crise", component: AdminCrisisAlerts },
        { path: "/avaliacoes", component: AdminReviews },
      ],
    },
    clinica: {
      pathPrefix: "/clinic",
      Layout: ClinicLayout,
      routes: [
        { path: "/", component: ClinicDashboard },
        { path: "/terapeutas", component: ClinicTherapists },
        { path: "/pacientes", component: ClinicPatients },
        { path: "/agendamentos", component: ClinicDashboard },
        { path: "/financeiro", component: ClinicFinancials },
        { path: "/mensagens", component: Messages },
        { path: "/avaliacoes", component: ClinicDashboard },
        { path: "/configuracoes", component: ClinicSettings },
      ],
    },
    terapeuta: {
      pathPrefix: "/therapist",
      Layout: TherapistLayout,
      routes: [
        { path: "/", component: TherapistDashboard },
        { path: "/agenda", component: TherapistCalendar },
        { path: "/agenda/disponibilidade", component: TherapistAvailabilitySettings },
        { path: "/recorrentes", component: TherapistRecurringSchedules },
        { path: "/pacientes", component: TherapistPatients },
        { path: "/pacientes/:id", component: TherapistPatientProfile },
        { path: "/sessoes", component: TherapistDashboard },
        { path: "/sessoes/:id", component: TherapistSessionDetail },
        { path: "/financeiro", component: TherapistFinancials },
        { path: "/avaliacoes", component: TherapistReviews },
        { path: "/mensagens", component: Messages },
        { path: "/prontuario", component: TherapistClinicalRecords },
        { path: "/tarefas-terapeuticas", component: TherapistHomeworkManager },
        { path: "/bi", component: TherapistBiDashboard },
        { path: "/alertas-crise", component: TherapistCrisisAlerts },
        { path: "/configuracoes", component: TherapistSettings },
      ],
    },
    paciente: {
      pathPrefix: "/patient",
      Layout: PatientLayout,
      routes: [
        { path: "/", component: PatientDashboard },
        { path: "/agenda", component: PatientCalendar },
        { path: "/recorrentes", component: PatientRecurringSchedules },
        { path: "/sessoes", component: PatientSessionHistory },
        { path: "/sessoes/:id", component: PatientSessionDetail },
        { path: "/jornada", component: PatientJourney },
        { path: "/carteira", component: PatientWallet },
        { path: "/configuracoes/pagamentos", component: PatientPaymentMethods },
        { path: "/mensagens", component: Messages },
        { path: "/avaliacoes", component: PatientReviews },
        { path: "/humor", component: PatientMoodTracker },
        { path: "/diario", component: PatientDiary },
        { path: "/tarefas", component: PatientHomework },
        { path: "/recibos", component: PatientInvoices },
        { path: "/configuracoes", component: PatientSettings },
      ],
    },
  },

  unwrappedRoutes: [
    { path: "/session/:appointmentId", component: Session },
  ],

  publicRoutes: [
    { path: "/register", component: Register },
    { path: "/therapists", component: TherapistDirectory },
    { path: "/therapists/:id", component: TherapistProfile },
    { path: "/clinics", component: ClinicDirectory },
    { path: "/clinics/:id", component: ClinicProfile },
    { path: "/termos", component: TermsOfUse },
    { path: "/privacidade", component: PrivacyPolicy },
  ],

  Landing,
  Login: lazy(() => import("./pages/Login")),
  AcceptInvite: lazy(() => import("./pages/AcceptInvite")),
  ForgotPassword: lazy(() => import("./pages/ForgotPassword")),
  NotFound: lazy(() => import("./pages/NotFound")),
});
