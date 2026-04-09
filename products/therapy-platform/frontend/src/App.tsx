import { lazy, Suspense } from "react";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { useAuthStore } from "@/store/authStore";
import { PageSkeleton } from "@/components/ui/page-skeleton";

// Layouts
import { AdminLayout } from "@/components/layout/AdminLayout";
import { ClinicLayout } from "@/components/layout/ClinicLayout";
import { TherapistLayout } from "@/components/layout/TherapistLayout";
import { PatientLayout } from "@/components/layout/PatientLayout";

// ── Lazy-loaded pages ───────────────────────────────────────

// Public
const Landing = lazy(() => import("./pages/Landing"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));
const NotFound = lazy(() => import("./pages/NotFound"));
const SSOCallback = lazy(() => import("./pages/SSOCallback"));
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

// Directory (any authenticated user)
const TherapistDirectory = lazy(() => import("./pages/TherapistDirectory"));
const TherapistProfile = lazy(() => import("./pages/TherapistProfile"));
const ClinicDirectory = lazy(() => import("./pages/ClinicDirectory"));
const ClinicProfile = lazy(() => import("./pages/ClinicProfile"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 2 * 60 * 1000,
    },
  },
});

// ── Role-based route groups ─────────────────────────────────

function AdminRoutes() {
  return (
    <AdminLayout>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<AdminDashboard />} />
          <Route path="/terapeutas" element={<AdminTherapists />} />
          <Route path="/terapeutas/:id" element={<AdminTherapistDetail />} />
          <Route path="/clinicas" element={<AdminClinics />} />
          <Route path="/clinicas/:id" element={<AdminClinicDetail />} />
          <Route path="/pacientes" element={<AdminPatients />} />
          <Route path="/pacientes/:id" element={<AdminPatientDetail />} />
          <Route path="/agendamentos" element={<AdminAppointments />} />
          <Route path="/financeiro" element={<AdminFinancials />} />
          <Route path="/reembolsos" element={<AdminRefunds />} />
          <Route path="/configuracoes" element={<AdminSettings />} />
          <Route path="/prompts-ia" element={<AdminAIPrompts />} />
          <Route path="/suporte" element={<AdminSupport />} />
          <Route path="/moderacao" element={<AdminModeration />} />
          <Route path="/alertas-crise" element={<AdminCrisisAlerts />} />
          <Route path="/avaliacoes" element={<AdminReviews />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </AdminLayout>
  );
}

function ClinicRoutes() {
  return (
    <ClinicLayout>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<ClinicDashboard />} />
          <Route path="/terapeutas" element={<ClinicTherapists />} />
          <Route path="/pacientes" element={<ClinicPatients />} />
          <Route path="/agendamentos" element={<ClinicDashboard />} />
          <Route path="/financeiro" element={<ClinicFinancials />} />
          <Route path="/mensagens" element={<Messages />} />
          <Route path="/avaliacoes" element={<ClinicDashboard />} />
          <Route path="/configuracoes" element={<ClinicSettings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </ClinicLayout>
  );
}

function TherapistRoutes() {
  return (
    <TherapistLayout>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<TherapistDashboard />} />
          <Route path="/agenda" element={<TherapistCalendar />} />
          <Route path="/agenda/disponibilidade" element={<TherapistAvailabilitySettings />} />
          <Route path="/recorrentes" element={<TherapistRecurringSchedules />} />
          <Route path="/pacientes" element={<TherapistPatients />} />
          <Route path="/pacientes/:id" element={<TherapistPatientProfile />} />
          <Route path="/sessoes" element={<TherapistDashboard />} />
          <Route path="/sessoes/:id" element={<TherapistSessionDetail />} />
          <Route path="/financeiro" element={<TherapistFinancials />} />
          <Route path="/avaliacoes" element={<TherapistReviews />} />
          <Route path="/mensagens" element={<Messages />} />
          <Route path="/prontuario" element={<TherapistClinicalRecords />} />
          <Route path="/tarefas-terapeuticas" element={<TherapistHomeworkManager />} />
          <Route path="/bi" element={<TherapistBiDashboard />} />
          <Route path="/alertas-crise" element={<TherapistCrisisAlerts />} />
          <Route path="/configuracoes" element={<TherapistSettings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </TherapistLayout>
  );
}

function PatientRoutes() {
  return (
    <PatientLayout>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<PatientDashboard />} />
          <Route path="/agenda" element={<PatientCalendar />} />
          <Route path="/recorrentes" element={<PatientRecurringSchedules />} />
          <Route path="/sessoes" element={<PatientSessionHistory />} />
          <Route path="/sessoes/:id" element={<PatientSessionDetail />} />
          <Route path="/jornada" element={<PatientJourney />} />
          <Route path="/carteira" element={<PatientWallet />} />
          <Route path="/configuracoes/pagamentos" element={<PatientPaymentMethods />} />
          <Route path="/mensagens" element={<Messages />} />
          <Route path="/avaliacoes" element={<PatientReviews />} />
          <Route path="/humor" element={<PatientMoodTracker />} />
          <Route path="/diario" element={<PatientDiary />} />
          <Route path="/tarefas" element={<PatientHomework />} />
          <Route path="/recibos" element={<PatientInvoices />} />
          <Route path="/configuracoes" element={<PatientSettings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </PatientLayout>
  );
}

// Directory pages wrapped in the user's own layout
function DirectoryWithLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const role = user?.user_metadata?.role as string | undefined;

  if (role === "admin") return <AdminLayout>{children}</AdminLayout>;
  if (role === "clinica") return <ClinicLayout>{children}</ClinicLayout>;
  if (role === "terapeuta") return <TherapistLayout>{children}</TherapistLayout>;
  return <PatientLayout>{children}</PatientLayout>;
}

// ── Authenticated routing ───────────────────────────────────

function AuthenticatedRoutes() {
  const { user } = useAuthStore();
  const role = user?.user_metadata?.role as string | undefined;

  // Determine the default dashboard path based on role
  const dashboardPath =
    role === "admin" ? "/admin" :
    role === "clinica" ? "/clinic" :
    role === "terapeuta" ? "/therapist" :
    "/patient";

  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        {/* Root redirects to role-specific dashboard */}
        <Route path="/" element={<Navigate to={dashboardPath} replace />} />

        {/* Full-screen session page — no layout wrapper */}
        <Route path="/session/:appointmentId" element={<Session />} />

        {/* Role-scoped layouts */}
        <Route path="/admin/*" element={<AdminRoutes />} />
        <Route path="/clinic/*" element={<ClinicRoutes />} />
        <Route path="/therapist/*" element={<TherapistRoutes />} />
        <Route path="/patient/*" element={<PatientRoutes />} />

        {/* Directory pages — accessible by any authenticated user */}
        <Route
          path="/therapists"
          element={
            <DirectoryWithLayout>
              <TherapistDirectory />
            </DirectoryWithLayout>
          }
        />
        <Route
          path="/therapists/:id"
          element={
            <DirectoryWithLayout>
              <TherapistProfile />
            </DirectoryWithLayout>
          }
        />
        <Route
          path="/clinics"
          element={
            <DirectoryWithLayout>
              <ClinicDirectory />
            </DirectoryWithLayout>
          }
        />
        <Route
          path="/clinics/:id"
          element={
            <DirectoryWithLayout>
              <ClinicProfile />
            </DirectoryWithLayout>
          }
        />

        {/* Legal pages — accessible when authenticated too */}
        <Route path="/termos" element={<TermsOfUse />} />
        <Route path="/privacidade" element={<PrivacyPolicy />} />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}

// ── App content — auth gate ─────────────────────────────────

function AppContent() {
  const { user, isInitialized } = useAuthStore();

  if (!isInitialized) {
    return <PageSkeleton />;
  }

  // Unauthenticated users see public routes
  if (!user) {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/sso" element={<SSOCallback />} />
          {/* Public directory access */}
          <Route path="/therapists" element={<TherapistDirectory />} />
          <Route path="/therapists/:id" element={<TherapistProfile />} />
          <Route path="/clinics" element={<ClinicDirectory />} />
          <Route path="/clinics/:id" element={<ClinicProfile />} />
          {/* Legal pages */}
          <Route path="/termos" element={<TermsOfUse />} />
          <Route path="/privacidade" element={<PrivacyPolicy />} />
          {/* Redirect everything else to login */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return <AuthenticatedRoutes />;
}

// ── Root App ────────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppContent />
            <Toaster richColors position="top-right" />
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
