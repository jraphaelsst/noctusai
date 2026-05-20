/**
 * Product Layout Factory
 *
 * Creates a Layout component with the standard NoctusAI pattern.
 * Products provide static config (nav, brand) and optional enrichment
 * hooks for domain-specific data (DB profiles, roles, theme persistence).
 *
 * The enrichment hook (`useLayoutEnrichment`) is the extension point
 * that makes ANY product framework-first — no matter how complex.
 */
import { useCallback, type ReactNode } from "react";
import {
  AppShell,
  Sidebar,
  Header as SharedHeader,
  useTheme,
  useActivityRefresh,
  InactivityWarning,
  AIBadgeStack,
  PendingConsentBadge,
  LLMSpendBadge,
} from "@noctusai/lib/design-system";
import type { NavGroup, NavItem } from "@noctusai/lib/design-system";
import {
  resolveSSOContext, isTrial, subscriptionDaysRemaining, licenseDaysRemaining,
  usePageStatus, filterNavByPageStatus,
} from "@noctusai/lib";
import type { NavGroupWithRoute, NavItemWithRoute } from "@noctusai/lib";
import { toast } from "sonner";
import { ChevronLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { SupabaseClient } from "@supabase/supabase-js";
type AnySupabaseClient = SupabaseClient<any, any, any>;

/**
 * Enrichment data returned by the optional useLayoutEnrichment hook.
 * Products use this to inject domain-specific data into the framework layout.
 */
/**
 * The seed-default badges that fill `LayoutEnrichment.aiBadge` when no
 * product override is provided. Exported so products with their own
 * product-specific badges can compose:
 *
 *   import { DEFAULT_AI_BADGES, AIBadgeStack } from "@noctusai/seed";
 *   useLayoutEnrichment: () => ({
 *     aiBadge: <AIBadgeStack badges={[<MyBadge/>, ...DEFAULT_AI_BADGES]}/>
 *   });
 *
 * Order matters: the consent badge surfaces "user must decide on N
 * features" (intrinsic to the user), while the spend badge surfaces
 * "org is approaching budget" (operational). Consent first; ops second.
 */
export const DEFAULT_AI_BADGES: ReactNode[] = [
  <PendingConsentBadge key="pending-consent" />,
  <LLMSpendBadge key="llm-spend" />,
];

export interface LayoutEnrichment {
  /** Override user display name (e.g. from product DB profile) */
  userName?: string;
  /** Override user email */
  userEmail?: string;
  /** Override user phone */
  userPhone?: string;
  /** User avatar URL (not available from auth metadata) */
  userAvatar?: string;
  /** Override role label display */
  roleLabel?: string;
  /** Extra nav groups to add conditionally (e.g. admin panel) */
  extraNavGroups?: NavGroupWithRoute[];
  /** Override the effective dev role for page visibility (e.g. "dev" to show dev pages) */
  effectiveDevRole?: string | null;
  /** Whether the enrichment data is still loading */
  isLoading?: boolean;
  /** Whether email field is editable in profile editor */
  canEditEmail?: boolean;
  /** Custom profile update handler (overrides default auth.updateUser) */
  onUpdateProfile?: (data: { name: string; email: string; phone: string }) => Promise<void>;
  /** Custom theme persistence callback (e.g. save to DB) */
  onThemePersist?: (theme: string) => void;
  /** Initial theme from DB (overrides localStorage) */
  initialTheme?: "light" | "dark";
  /** Any extra user props to pass to SharedHeader */
  headerUserProps?: Record<string, any>;
  /**
   * Optional AI-derived badge rendered in the framework Header next to the
   * notification bell. P4 pattern from ai-expansion §5a — Tier 2 Phase 5
   * (2026-04-25). Use this for ambient AI signals: "today's brief" indicator,
   * pending-consent count, monthly-spend watermark, "homework due" badge, etc.
   *
   * Pass a string for plain text, a React element for richer markup, or
   * `null`/`undefined` to render nothing. The framework auto-hides empty
   * values — no need for products to gate render.
   */
  aiBadge?: string | React.ReactNode | null;
}

export interface ProductLayoutConfig {
  brandIcon: LucideIcon;
  brandTitle: string;
  navGroups: NavGroupWithRoute[];
  navGroupsFallback: NavGroup[];
  supabase: AnySupabaseClient;
  useAuthStore: () => { user: any };
  NotificationBell: React.ComponentType;
  standaloneItems?: NavItemWithRoute[];
  standaloneItemsFallback?: NavItem[];
  roleLabels?: Record<string, string>;
  defaultRoleLabel?: string;
  roleLabelOverride?: string;
  brandSubtitleOverride?: string;
  /**
   * Optional enrichment hook — the extension point that makes any product
   * framework-first, no matter how complex its layout needs are.
   *
   * Called inside the Layout component (follows React hooks rules).
   * Returns domain-specific overrides: DB profile data, conditional nav,
   * theme persistence, role labels, loading state.
   */
  useLayoutEnrichment?: () => LayoutEnrichment;
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

// canonical-default-ok: core is a named service (BackToCore nav). Non-local
// deploys MUST set VITE_CORE_URL explicitly.
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
    standaloneItems: standaloneWithRoutes,
    standaloneItemsFallback,
    supabase,
    useAuthStore,
    NotificationBell,
    roleLabels = DEFAULT_ROLE_LABELS,
    defaultRoleLabel = "Membro",
    roleLabelOverride,
    brandSubtitleOverride,
    useLayoutEnrichment,
  } = config;

  return function Layout({ children }: { children: React.ReactNode }) {
    const { user } = useAuthStore();

    // Call enrichment hook if provided (must be called unconditionally — hooks rules)
    const enrichment: LayoutEnrichment = useLayoutEnrichment ? useLayoutEnrichment() : {};

    // Theme — supports DB persistence via enrichment
    const { theme, toggleTheme } = useTheme({
      initialTheme: enrichment.initialTheme,
      onPersist: enrichment.onThemePersist,
    });

    useActivityRefresh({
      onRefresh: useCallback(async () => { await supabase.auth.refreshSession(); }, []),
    });

    // All hooks must be called before any conditional return (Rules of Hooks).
    const { data: statusPaginas } = usePageStatus(supabase, !!user);

    // If enrichment is loading, show loading state
    if (enrichment.isLoading) {
      return (
        <header className="h-14 sm:h-16 bg-card border-b border-border px-4 sm:px-6 flex items-center justify-end">
          <p className="text-sm font-medium text-muted-foreground">Carregando...</p>
        </header>
      );
    }

    const ssoCtx = resolveSSOContext(user?.user_metadata);
    const trialDays = isTrial(ssoCtx) ? subscriptionDaysRemaining(ssoCtx) : null;
    const licenseDays = licenseDaysRemaining(ssoCtx);
    const effectiveRole = enrichment.effectiveDevRole ?? ssoCtx.org.role;

    // Merge base nav groups + conditional extra groups from enrichment
    const allNavGroups = enrichment.extraNavGroups?.length
      ? [...navGroupsWithRoutes, ...enrichment.extraNavGroups]
      : navGroupsWithRoutes;

    const allNavFallback = enrichment.extraNavGroups?.length
      ? [...navGroupsFallback, ...enrichment.extraNavGroups.map(g => ({
          ...g, items: g.items.map(({ route, ...item }) => item),
        })) as NavGroup[]]
      : navGroupsFallback;
    const navGroups = (statusPaginas?.length
      ? filterNavByPageStatus(allNavGroups, statusPaginas, effectiveRole)
      : allNavFallback) as NavGroup[];

    // Standalone items
    const standaloneItems: NavItem[] = standaloneWithRoutes?.length
      ? (statusPaginas?.length
          ? filterNavByPageStatus(
              [{ key: "_standalone", label: "", items: standaloneWithRoutes }],
              statusPaginas,
              effectiveRole,
            ).flatMap((g) => g.items) as NavItem[]
          : (standaloneItemsFallback || standaloneWithRoutes.map(({ route: _r, ...rest }) => rest) as NavItem[]))
      : [];

    const handleLogout = async () => {
      await supabase.auth.signOut();
      window.location.href = ssoCtx.isSSO ? CORE_URL : "/login";
    };

    // Profile update — use enrichment override or default auth.updateUser
    const handleUpdateProfile = enrichment.onUpdateProfile || (async (data: { name: string; email: string; phone: string }) => {
      const { error } = await supabase.auth.updateUser({
        data: { full_name: data.name, phone: data.phone },
      });
      if (error) throw error;
      toast.success("Perfil atualizado com sucesso!");
    });

    const handleUpdatePassword = async (newPassword: string) => {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw error;
      toast.success("Senha atualizada com sucesso!");
    };

    // User display — enrichment overrides auth metadata
    const userName = enrichment.userName
      || user?.user_metadata?.full_name
      || user?.user_metadata?.name
      || user?.email?.split("@")[0]
      || "Usuario";

    const userRole = enrichment.roleLabel
      || roleLabelOverride
      || (ssoCtx.isProductAdmin ? "Administrador" : roleLabels[ssoCtx.org.role] || defaultRoleLabel);

    return (
      <AppShell
        sidebar={
          <Sidebar
            brandIcon={brandIcon}
            brandTitle={brandTitle}
            brandSubtitle={brandSubtitleOverride || ssoCtx.org.name || "NoctusAI"}
            navGroups={navGroups}
            standaloneItems={standaloneItems.length > 0 ? standaloneItems : undefined}
            footerContent={ssoCtx.isSSO ? BackToCore : undefined}
          />
        }
        header={({ onMenuToggle }) => (
          <SharedHeader
            user={{
              name: userName,
              email: enrichment.userEmail || user?.email || "",
              phone: enrichment.userPhone || user?.user_metadata?.phone || user?.phone || "",
              role: userRole,
              ...(enrichment.userAvatar && { avatar: enrichment.userAvatar }),
              ...(enrichment.headerUserProps || {}),
            }}
            onMenuToggle={onMenuToggle}
            logoutBehavior="redirect"
            platformUrl={CORE_URL}
            onLogout={handleLogout}
            theme={theme}
            onThemeToggle={toggleTheme}
            actions={(() => {
              // Default-fill `aiBadge` with the seed standard stack when the
              // product didn't provide one. Semantics:
              //   - `undefined` → use seed default (`<AIBadgeStack/>` of
              //                   `<PendingConsentBadge/>` + `<LLMSpendBadge/>`)
              //   - `null`      → explicit opt-out, render no badge
              //   - other       → product-supplied badge / stack
              // The `!== undefined` check (vs `??`) preserves `null` as
              // explicit-empty. Products that want product-specific badges
              // compose with the defaults: `aiBadge: <AIBadgeStack badges=
              // {[<DailyBriefBadge/>, ...DEFAULT_AI_BADGES]}/>`. The
              // `DEFAULT_AI_BADGES` export lives in this file.
              const aiBadgeContent =
                enrichment.aiBadge !== undefined
                  ? enrichment.aiBadge
                  : <AIBadgeStack badges={DEFAULT_AI_BADGES} />;
              return aiBadgeContent ? (
                <span className="inline-flex items-center gap-2">
                  {aiBadgeContent}
                  <NotificationBell />
                </span>
              ) : (
                <NotificationBell />
              );
            })()}
            canEditEmail={enrichment.canEditEmail}
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
