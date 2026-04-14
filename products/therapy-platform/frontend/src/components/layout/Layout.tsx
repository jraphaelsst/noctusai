/**
 * Therapy Platform — Unified Layout
 *
 * Follows THE NoctusAI product layout pattern:
 * - Single Layout.tsx per product
 * - Nav data defined as static constants, switched by user role
 * - SharedHeader + SharedSidebar via AppShell from design system
 * - useTheme + useActivityRefresh from shared hooks
 * - Products use logoutBehavior="signout" (therapy has its own auth, not SSO)
 *
 * Role-based nav: platform_admin, clinic_admin, therapist, patient
 */
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import {
  AppShell,
  Sidebar,
  Header as SharedHeader,
  useTheme,
  useActivityRefresh,
} from "@noctusai/shared/design-system";
import type { NavGroup, NavItem } from "@noctusai/shared/design-system";
import { NotificationBell } from "@/components/NotificationBell";
import {
  resolveSSOContext, isTrial, subscriptionDaysRemaining, licenseDaysRemaining,
  usePageStatus, filterNavByPageStatus,
} from "@noctusai/shared";
import type { NavGroupWithRoute, NavItemWithRoute } from "@noctusai/shared";
import { toast } from "sonner";
import {
  LayoutDashboard, CalendarDays, Users, ClipboardList, UserCircle,
  DollarSign, Star, Settings, MessageSquare, Brain, Heart,
  CheckSquare, BarChart3, AlertTriangle, Building2, Search,
  TrendingUp, Wallet, Smile, BookOpen, Receipt, HeadphonesIcon,
  ShieldCheck, ReceiptText, ChevronLeft,
} from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

// ── Role labels ──────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrador",
  clinica: "Administrador de Clinica",
  terapeuta: "Terapeuta",
  paciente: "Paciente",
};

// ── Nav data per role ────────────────────────────────────────

const ADMIN_NAV: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: LayoutDashboard,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/admin", icon: LayoutDashboard, route: "admin-dashboard" },
      { name: "Terapeutas", href: "/admin/terapeutas", icon: Users, route: "admin-terapeutas" },
      { name: "Clinicas", href: "/admin/clinicas", icon: Building2, route: "admin-clinicas" },
      { name: "Pacientes", href: "/admin/pacientes", icon: UserCircle, route: "admin-pacientes" },
    ],
  },
  {
    key: "operacional",
    label: "Operacional",
    icon: CalendarDays,
    defaultOpen: true,
    items: [
      { name: "Agendamentos", href: "/admin/agendamentos", icon: CalendarDays, route: "admin-agendamentos" },
      { name: "Financeiro", href: "/admin/financeiro", icon: DollarSign, route: "admin-financeiro" },
      { name: "Reembolsos", href: "/admin/reembolsos", icon: ReceiptText, route: "admin-reembolsos" },
    ],
  },
  {
    key: "sistema",
    label: "Sistema",
    icon: Settings,
    defaultOpen: false,
    items: [
      { name: "Configuracoes", href: "/admin/configuracoes", icon: Settings, route: "admin-configuracoes" },
      { name: "Prompts IA", href: "/admin/prompts-ia", icon: Brain, route: "admin-prompts-ia" },
      { name: "Suporte", href: "/admin/suporte", icon: HeadphonesIcon, route: "admin-suporte" },
      { name: "Moderacao", href: "/admin/moderacao", icon: ShieldCheck, route: "admin-moderacao" },
      { name: "Alertas de Crise", href: "/admin/alertas-crise", icon: AlertTriangle, route: "admin-alertas-crise" },
      { name: "Avaliacoes", href: "/admin/avaliacoes", icon: Star, route: "admin-avaliacoes" },
    ],
  },
];

const CLINIC_NAV: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: LayoutDashboard,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/clinic", icon: LayoutDashboard, route: "clinic-dashboard" },
      { name: "Terapeutas", href: "/clinic/terapeutas", icon: Users, route: "clinic-terapeutas" },
      { name: "Pacientes", href: "/clinic/pacientes", icon: UserCircle, route: "clinic-pacientes" },
      { name: "Agendamentos", href: "/clinic/agendamentos", icon: CalendarDays, route: "clinic-agendamentos" },
    ],
  },
  {
    key: "gestao",
    label: "Gestao",
    icon: DollarSign,
    defaultOpen: true,
    items: [
      { name: "Financeiro", href: "/clinic/financeiro", icon: DollarSign, route: "clinic-financeiro" },
      { name: "Mensagens", href: "/clinic/mensagens", icon: MessageSquare, route: "clinic-mensagens" },
      { name: "Avaliacoes", href: "/clinic/avaliacoes", icon: Star, route: "clinic-avaliacoes" },
    ],
  },
];
const CLINIC_STANDALONE: NavItemWithRoute[] = [
  { name: "Configuracoes", href: "/clinic/configuracoes", icon: Settings, route: "clinic-configuracoes" },
];

const THERAPIST_NAV: NavGroupWithRoute[] = [
  {
    key: "consultorio",
    label: "Consultorio",
    icon: Brain,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/therapist", icon: LayoutDashboard, route: "therapist-dashboard" },
      { name: "Agenda", href: "/therapist/agenda", icon: CalendarDays, route: "therapist-agenda" },
      { name: "Pacientes", href: "/therapist/pacientes", icon: Users, route: "therapist-pacientes" },
      { name: "Sessoes", href: "/therapist/sessoes", icon: ClipboardList, route: "therapist-sessoes" },
      { name: "Prontuario", href: "/therapist/prontuario", icon: ClipboardList, route: "therapist-prontuario" },
    ],
  },
  {
    key: "gestao",
    label: "Gestao",
    icon: DollarSign,
    defaultOpen: true,
    items: [
      { name: "Financeiro", href: "/therapist/financeiro", icon: DollarSign, route: "therapist-financeiro" },
      { name: "Tarefas", href: "/therapist/tarefas-terapeuticas", icon: CheckSquare, route: "therapist-tarefas" },
      { name: "Dashboard", href: "/therapist/bi", icon: BarChart3, route: "therapist-bi" },
      { name: "Alertas", href: "/therapist/alertas-crise", icon: AlertTriangle, route: "therapist-alertas-crise" },
      { name: "Avaliacoes", href: "/therapist/avaliacoes", icon: Star, route: "therapist-avaliacoes" },
      { name: "Mensagens", href: "/therapist/mensagens", icon: MessageSquare, route: "therapist-mensagens" },
    ],
  },
];
const THERAPIST_STANDALONE: NavItemWithRoute[] = [
  { name: "Configuracoes", href: "/therapist/configuracoes", icon: Settings, route: "therapist-configuracoes" },
];

const PATIENT_NAV: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Heart,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/patient", icon: LayoutDashboard, route: "patient-dashboard" },
      { name: "Encontrar Terapeuta", href: "/therapists", icon: Search, route: "patient-encontrar-terapeuta" },
      { name: "Explorar Clinicas", href: "/clinics", icon: Building2, route: "patient-explorar-clinicas" },
    ],
  },
  {
    key: "minha-terapia",
    label: "Minha Terapia",
    icon: ClipboardList,
    defaultOpen: true,
    items: [
      { name: "Minha Agenda", href: "/patient/agenda", icon: CalendarDays, route: "patient-agenda" },
      { name: "Minhas Sessoes", href: "/patient/sessoes", icon: ClipboardList, route: "patient-sessoes" },
      { name: "Minha Jornada", href: "/patient/jornada", icon: TrendingUp, route: "patient-jornada" },
      { name: "Humor", href: "/patient/humor", icon: Smile, route: "patient-humor" },
      { name: "Diario", href: "/patient/diario", icon: BookOpen, route: "patient-diario" },
      { name: "Tarefas", href: "/patient/tarefas", icon: CheckSquare, route: "patient-tarefas" },
    ],
  },
  {
    key: "conta",
    label: "Conta",
    icon: Wallet,
    defaultOpen: false,
    items: [
      { name: "Minha Carteira", href: "/patient/carteira", icon: Wallet, route: "patient-carteira" },
      { name: "Recibos", href: "/patient/recibos", icon: Receipt, route: "patient-recibos" },
      { name: "Avaliacoes", href: "/patient/avaliacoes", icon: Star, route: "patient-avaliacoes" },
      { name: "Mensagens", href: "/patient/mensagens", icon: MessageSquare, route: "patient-mensagens" },
    ],
  },
];
const PATIENT_STANDALONE: NavItemWithRoute[] = [
  { name: "Configuracoes", href: "/patient/configuracoes", icon: Settings, route: "patient-configuracoes" },
];

// ── Brand info per role ──────────────────────────────────────

const BRAND_CONFIG: Record<string, { title: string; subtitle: string }> = {
  admin: { title: "NoctusAI", subtitle: "Painel Administrativo" },
  clinica: { title: "Clinica", subtitle: "Gestao de Clinica" },
  terapeuta: { title: "Terapeuta", subtitle: "Meu Consultorio" },
  paciente: { title: "NoctusAI", subtitle: "Plataforma de Terapia" },
};

// ── Nav resolver ─────────────────────────────────────────────

function getNavForRole(role: string): { groups: NavGroupWithRoute[]; standalone: NavItemWithRoute[] } {
  switch (role) {
    case "admin": return { groups: ADMIN_NAV, standalone: [] };
    case "clinica": return { groups: CLINIC_NAV, standalone: CLINIC_STANDALONE };
    case "terapeuta": return { groups: THERAPIST_NAV, standalone: THERAPIST_STANDALONE };
    default: return { groups: PATIENT_NAV, standalone: PATIENT_STANDALONE };
  }
}

/** Strip route fields from nav data for fallback when status_pagina table doesn't exist */
function stripRoutes(groups: NavGroupWithRoute[]): NavGroup[] {
  return groups.map((g) => ({ ...g, items: g.items.map(({ route: _r, ...rest }) => rest) })) as NavGroup[];
}
function stripRouteFromItems(items: NavItemWithRoute[]): NavItem[] {
  return items.map(({ route: _r, ...rest }) => rest) as NavItem[];
}

// ── Back to NoctusAI (shown for SSO users) ─────────────────

const BackToCore = (
  <a
    href={CORE_URL}
    className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
  >
    <ChevronLeft className="h-4 w-4 shrink-0" />
    Voltar ao NoctusAI
  </a>
);

// ── Layout ───────────────────────────────────────────────────

export function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { theme, toggleTheme } = useTheme();

  useActivityRefresh({
    onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
  });

  const meta = user?.user_metadata;
  const ssoCtx = resolveSSOContext(meta);
  const { isSSO, isProductAdmin } = ssoCtx;
  const userRole: string =
    isProductAdmin ? "admin" :
    (meta?.role as string) || "paciente";
  const { groups: rawGroups, standalone: rawStandalone } = getNavForRole(userRole);
  const brand = BRAND_CONFIG[userRole] || BRAND_CONFIG.paciente;
  const trialDays = isTrial(ssoCtx) ? subscriptionDaysRemaining(ssoCtx) : null;
  const licenseDays = licenseDaysRemaining(ssoCtx);

  // Page status filtering — gracefully falls back if table doesn't exist
  const { data: statusPaginas } = usePageStatus(supabase, !!user);
  const groups = statusPaginas?.length
    ? filterNavByPageStatus(rawGroups, statusPaginas, user?.user_metadata?.org_role) as NavGroup[]
    : stripRoutes(rawGroups);
  const standalone = statusPaginas?.length
    ? filterNavByPageStatus(
        [{ key: "_standalone", label: "", items: rawStandalone }],
        statusPaginas,
        user?.user_metadata?.org_role,
      ).flatMap((g) => g.items) as NavItem[]
    : stripRouteFromItems(rawStandalone);

  const handleLogout = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) {
      toast.error("Erro ao sair da conta");
      return;
    }
    // SSO users go back to NoctusAI core; direct users go to login
    if (isSSO) {
      window.location.href = CORE_URL;
    } else {
      toast.success("Logout realizado com sucesso");
      navigate("/login");
    }
  };

  const handleUpdateProfile = async (data: { name: string; email: string; phone: string }) => {
    const { error } = await supabase.auth.updateUser({
      data: { full_name: data.name, phone: data.phone },
    });
    if (error) throw error;
    toast.success("Perfil atualizado com sucesso!");
  };

  const handleUpdatePassword = async (newPassword: string) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
    toast.success("Senha atualizada com sucesso!");
  };

  const userName = user?.user_metadata?.full_name
    || user?.user_metadata?.name
    || user?.email?.split("@")[0]
    || "Usuario";

  return (
    <AppShell
      sidebar={
        <Sidebar
          brandIcon={Heart}
          brandTitle={brand.title}
          brandSubtitle={ssoCtx.org.name || brand.subtitle}
          navGroups={groups}
          standaloneItems={standalone}
          footerContent={isSSO ? BackToCore : undefined}
        />
      }
      header={({ onMenuToggle }) => (
        <SharedHeader
          user={{
            name: userName,
            email: user?.email || "",
            phone: user?.user_metadata?.phone || user?.phone || "",
            role: ROLE_LABELS[userRole] || "Paciente",
          }}
          onMenuToggle={onMenuToggle}
          onLogout={handleLogout}
          theme={theme}
          onThemeToggle={toggleTheme}
          actions={<NotificationBell />}
          onUpdateProfile={handleUpdateProfile}
          onUpdatePassword={handleUpdatePassword}
        />
      )}
    >
      <div className="p-4 sm:p-6 lg:p-8">
        {trialDays !== null && trialDays <= 7 && (
          <div className="mb-4 rounded-lg border border-warning bg-warning/10 px-4 py-3 text-sm text-warning-foreground">
            {trialDays > 0
              ? `Periodo de teste expira em ${trialDays} dia${trialDays !== 1 ? "s" : ""}.`
              : "Periodo de teste expirado."}
          </div>
        )}
        {licenseDays !== null && licenseDays <= 7 && (
          <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {licenseDays > 0
              ? `Licenca expira em ${licenseDays} dia${licenseDays !== 1 ? "s" : ""}.`
              : "Licenca expirada."}
          </div>
        )}
        {children}
      </div>
    </AppShell>
  );
}
