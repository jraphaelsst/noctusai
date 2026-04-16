/**
 * Therapy Platform — Role-based Layouts via Seed Framework
 *
 * Creates 4 layout instances using createProductLayout(), one per role:
 *   - AdminLayout    (platform admin)
 *   - ClinicLayout   (clinic admin)
 *   - TherapistLayout
 *   - PatientLayout
 *
 * Each layout gets its own nav groups, brand config, and role label.
 * The seed framework handles: AppShell, Sidebar, Header, SSO, page status,
 * trial/license warnings, activity refresh, inactivity warning.
 */
import { createProductLayout } from "@noctusai/seed";
import type { NavGroupWithRoute, NavItemWithRoute } from "@noctusai/shared";
import type { NavGroup, NavItem } from "@noctusai/shared/design-system";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import { NotificationBell } from "@/components/NotificationBell";
import {
  LayoutDashboard, CalendarDays, Users, ClipboardList, UserCircle,
  DollarSign, Star, Settings, MessageSquare, Brain, Heart,
  CheckSquare, BarChart3, AlertTriangle, Building2, Search,
  TrendingUp, Wallet, Smile, BookOpen, Receipt, HeadphonesIcon,
  ShieldCheck, ReceiptText,
} from "lucide-react";

// ── Helper: strip route fields for fallback ─────────────────

function stripRoutes(groups: NavGroupWithRoute[]): NavGroup[] {
  return groups.map((g) => ({ ...g, items: g.items.map(({ route: _r, ...rest }) => rest) })) as NavGroup[];
}

function stripRouteFromItems(items: NavItemWithRoute[]): NavItem[] {
  return items.map(({ route: _r, ...rest }) => rest) as NavItem[];
}

// ── Admin nav ───────────────────────────────────────────────

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

// ── Clinic nav ──────────────────────────────────────────────

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

// ── Therapist nav ───────────────────────────────────────────

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

// ── Patient nav ─────────────────────────────────────────────

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

// ── Shared config ───────────────────────────────────────────

const shared = {
  brandIcon: Heart,
  supabase,
  useAuthStore,
  NotificationBell,
} as const;

// ── Layout instances ────────────────────────────────────────

export const AdminLayout = createProductLayout({
  ...shared,
  brandTitle: "NoctusAI",
  brandSubtitleOverride: "Painel Administrativo",
  navGroups: ADMIN_NAV,
  navGroupsFallback: stripRoutes(ADMIN_NAV),
  roleLabelOverride: "Administrador",
});

export const ClinicLayout = createProductLayout({
  ...shared,
  brandTitle: "Clinica",
  brandSubtitleOverride: "Gestao de Clinica",
  navGroups: CLINIC_NAV,
  navGroupsFallback: stripRoutes(CLINIC_NAV),
  standaloneItems: CLINIC_STANDALONE,
  standaloneItemsFallback: stripRouteFromItems(CLINIC_STANDALONE),
  roleLabelOverride: "Administrador de Clinica",
});

export const TherapistLayout = createProductLayout({
  ...shared,
  brandTitle: "Terapeuta",
  brandSubtitleOverride: "Meu Consultorio",
  navGroups: THERAPIST_NAV,
  navGroupsFallback: stripRoutes(THERAPIST_NAV),
  standaloneItems: THERAPIST_STANDALONE,
  standaloneItemsFallback: stripRouteFromItems(THERAPIST_STANDALONE),
  roleLabelOverride: "Terapeuta",
});

export const PatientLayout = createProductLayout({
  ...shared,
  brandTitle: "NoctusAI",
  brandSubtitleOverride: "Plataforma de Terapia",
  navGroups: PATIENT_NAV,
  navGroupsFallback: stripRoutes(PATIENT_NAV),
  standaloneItems: PATIENT_STANDALONE,
  standaloneItemsFallback: stripRouteFromItems(PATIENT_STANDALONE),
  roleLabelOverride: "Paciente",
});
