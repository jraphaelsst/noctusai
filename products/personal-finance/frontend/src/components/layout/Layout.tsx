import { useCallback } from "react";
import { useAuthStore } from "@/store/authStore";
import { supabase } from "@/integrations/supabase/client";
import {
  AppShell,
  Sidebar,
  Header as SharedHeader,
  useTheme,
  useActivityRefresh,
  InactivityWarning,
} from "@noctusai/shared/design-system";
import type { NavGroup } from "@noctusai/shared/design-system";
import { NotificationBell } from "@/components/NotificationBell";
import {
  resolveSSOContext, isTrial, subscriptionDaysRemaining, licenseDaysRemaining,
  usePageStatus, filterNavByPageStatus,
} from "@noctusai/shared";
import type { NavGroupWithRoute } from "@noctusai/shared";
import { toast } from "sonner";
import {
  LayoutDashboard, Wallet, ArrowLeftRight, Tags, PiggyBank, Target,
  TrendingUp, Eye, CalendarClock, Landmark, FileBarChart, ArrowUpDown,
  ChevronLeft, DollarSign, Home, BarChart3, LineChart, Users,
} from "lucide-react";

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

// ── Nav groups with route keys for page status filtering ──────────────

const NAV_GROUPS_WITH_ROUTES: NavGroupWithRoute[] = [
  {
    key: "principal",
    label: "Principal",
    icon: Home,
    defaultOpen: true,
    items: [
      { name: "Dashboard", href: "/", icon: LayoutDashboard, route: "dashboard" },
      { name: "Contas", href: "/contas", icon: Wallet, route: "contas" },
      { name: "Transacoes", href: "/transacoes", icon: ArrowLeftRight, route: "transacoes" },
      { name: "Categorias", href: "/categorias", icon: Tags, route: "categorias" },
    ],
  },
  {
    key: "planejamento",
    label: "Planejamento",
    icon: BarChart3,
    defaultOpen: true,
    items: [
      { name: "Orcamentos", href: "/orcamentos", icon: PiggyBank, route: "orcamentos" },
      { name: "Metas", href: "/metas", icon: Target, route: "metas" },
      { name: "Recorrentes", href: "/recorrentes", icon: CalendarClock, route: "recorrentes" },
    ],
  },
  {
    key: "investimentos",
    label: "Investimentos",
    icon: LineChart,
    defaultOpen: true,
    items: [
      { name: "Investimentos", href: "/carteira", icon: TrendingUp, route: "carteira" },
      { name: "Watchlist", href: "/watchlist", icon: Eye, route: "watchlist" },
      { name: "Operacoes", href: "/operacoes", icon: ArrowUpDown, route: "operacoes" },
    ],
  },
  {
    key: "relatorios",
    label: "Relatorios",
    icon: FileBarChart,
    defaultOpen: true,
    items: [
      { name: "Patrimonio", href: "/patrimonio", icon: Landmark, route: "patrimonio" },
      { name: "Relatorios", href: "/relatorios", icon: FileBarChart, route: "relatorios" },
      { name: "Equipe", href: "/equipe", icon: Users, route: "equipe" },
    ],
  },
];

// ── Fallback nav groups (when no status_pagina table exists) ──────────

const NAV_GROUPS_FALLBACK: NavGroup[] = NAV_GROUPS_WITH_ROUTES.map((g) => ({
  ...g,
  items: g.items.map(({ route: _route, ...rest }) => rest),
})) as NavGroup[];

const BackToCore = (
  <a
    href={CORE_URL}
    className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
  >
    <ChevronLeft className="h-4 w-4 shrink-0" />
    Voltar ao NoctusAI
  </a>
);

export function Layout({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  const { theme, toggleTheme } = useTheme();

  useActivityRefresh({
    onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
  });

  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const trialDays = isTrial(ssoCtx) ? subscriptionDaysRemaining(ssoCtx) : null;
  const licenseDays = licenseDaysRemaining(ssoCtx);

  // Page status filtering — gracefully falls back if table doesn't exist
  const { data: statusPaginas } = usePageStatus(supabase, !!user);
  const navGroups = statusPaginas?.length
    ? filterNavByPageStatus(NAV_GROUPS_WITH_ROUTES, statusPaginas, user?.user_metadata?.org_role) as NavGroup[]
    : NAV_GROUPS_FALLBACK;

  const handleLogout = async () => {
    await supabase.auth.signOut();
    if (ssoCtx.isSSO) {
      window.location.href = CORE_URL;
    } else {
      window.location.href = "/login";
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
          brandIcon={DollarSign}
          brandTitle="Financas Pessoais"
          brandSubtitle={ssoCtx.org.name || "NoctusAI"}
          navGroups={navGroups}
          footerContent={ssoCtx.isSSO ? BackToCore : undefined}
        />
      }
      header={({ onMenuToggle }) => (
        <SharedHeader
          user={{
            name: userName,
            email: user?.email || "",
            phone: user?.user_metadata?.phone || user?.phone || "",
            role: ssoCtx.isProductAdmin ? "Administrador" : "Financas Pessoais",
          }}
          onMenuToggle={onMenuToggle}
          logoutBehavior="redirect"
          platformUrl={CORE_URL}
          onLogout={handleLogout}
          theme={theme}
          onThemeToggle={toggleTheme}
          actions={<NotificationBell />}
          onUpdateProfile={handleUpdateProfile}
          onUpdatePassword={handleUpdatePassword}
        />
      )}
    >
      <div className="p-4 sm:p-6">
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
      <InactivityWarning
        onExtend={async () => { await supabase.auth.refreshSession(); }}
        onExpired={() => { window.location.href = CORE_URL; }}
      />
    </AppShell>
  );
}
