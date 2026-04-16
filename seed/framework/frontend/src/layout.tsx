/**
 * Product Layout Factory
 *
 * Creates a Layout component with the standard NoctusAI pattern:
 * - AppShell with Sidebar + Header
 * - Page status filtering (dev-gated pages)
 * - SSO context resolution
 * - Trial/license expiration warnings
 * - Activity refresh + inactivity warning
 * - Profile update handlers
 * - "Back to Core" link for SSO users
 *
 * Products only provide: brandIcon, brandTitle, navGroups, and supabase client.
 */
import { useCallback } from "react";
import {
  AppShell,
  Sidebar,
  Header as SharedHeader,
  useTheme,
  useActivityRefresh,
  InactivityWarning,
} from "@noctusai/shared/design-system";
import type { NavGroup } from "@noctusai/shared/design-system";
import {
  resolveSSOContext, isTrial, subscriptionDaysRemaining, licenseDaysRemaining,
  usePageStatus, filterNavByPageStatus,
} from "@noctusai/shared";
import type { NavGroupWithRoute } from "@noctusai/shared";
import { toast } from "sonner";
import { ChevronLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { SupabaseClient } from "@supabase/supabase-js";

export interface ProductLayoutConfig {
  /** Brand icon displayed in sidebar */
  brandIcon: LucideIcon;
  /** Product name displayed in sidebar */
  brandTitle: string;
  /** Nav groups with route keys for page status filtering */
  navGroups: NavGroupWithRoute[];
  /** Fallback nav groups when status_pagina table doesn't exist */
  navGroupsFallback: NavGroup[];
  /** Supabase client instance */
  supabase: SupabaseClient;
  /** Auth store hook (returns { user }) */
  useAuthStore: () => { user: any };
  /** Notification bell component */
  NotificationBell: React.ComponentType;
  /** Role labels for display (e.g. { admin: "Administrador" }) */
  roleLabels?: Record<string, string>;
  /** Default role label when no match (e.g. "Membro") */
  defaultRoleLabel?: string;
}

const DEFAULT_ROLE_LABELS: Record<string, string> = {
  owner: "Proprietario",
  admin: "Administrador",
  manager: "Gerente",
  member: "Membro",
  viewer: "Visualizador",
  dev: "Desenvolvedor",
  test: "Teste",
};

const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

const BackToCore = (
  <a
    href={CORE_URL}
    className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
  >
    <ChevronLeft className="h-4 w-4 shrink-0" />
    Voltar ao NoctusAI
  </a>
);

export function createProductLayout(config: ProductLayoutConfig) {
  const {
    brandIcon,
    brandTitle,
    navGroups: navGroupsWithRoutes,
    navGroupsFallback,
    supabase,
    useAuthStore,
    NotificationBell,
    roleLabels = DEFAULT_ROLE_LABELS,
    defaultRoleLabel = "Membro",
  } = config;

  return function Layout({ children }: { children: React.ReactNode }) {
    const { user } = useAuthStore();
    const { theme, toggleTheme } = useTheme();

    useActivityRefresh({
      onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
    });

    const ssoCtx = resolveSSOContext(user?.user_metadata);
    const trialDays = isTrial(ssoCtx) ? subscriptionDaysRemaining(ssoCtx) : null;
    const licenseDays = licenseDaysRemaining(ssoCtx);

    const { data: statusPaginas } = usePageStatus(supabase, !!user);
    const navGroups: NavGroup[] = statusPaginas?.length
      ? filterNavByPageStatus(navGroupsWithRoutes, statusPaginas, ssoCtx.org.role)
      : navGroupsFallback;

    const handleLogout = async () => {
      await supabase.auth.signOut();
      window.location.href = ssoCtx.isSSO ? CORE_URL : "/login";
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

    const userRole = ssoCtx.isProductAdmin
      ? "Administrador"
      : roleLabels[ssoCtx.org.role] || defaultRoleLabel;

    return (
      <AppShell
        sidebar={
          <Sidebar
            brandIcon={brandIcon}
            brandTitle={brandTitle}
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
              role: userRole,
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
        <InactivityWarning
          onExtend={async () => { await supabase.auth.refreshSession(); }}
          onExpired={() => { window.location.href = CORE_URL; }}
        />
      </AppShell>
    );
  };
}
