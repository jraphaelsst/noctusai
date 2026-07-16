/**
 * Product Layout Factory
 *
 * Creates a Layout component with the standard NoctusAI pattern.
 * Products provide static config (nav, brand) and optional enrichment
 * hooks for domain-specific data (DB profiles, roles, theme persistence).
 *
 * The enrichment hook (`useLayoutEnrichment`) is the extension point
 * that makes ANY product framework-first — no matter how complex.
 *
 * ## Dual auth mode (`supabase` vs `sessionAuth`)
 *
 * `ProductLayoutConfig` accepts EITHER `supabase` (default — the
 * original Supabase-JS shape, unchanged) OR `sessionAuth` (the
 * cookie-session sibling — see `LayoutSessionAuth` below). Exactly the
 * same precedence rule as `createProductApp`'s `authProvider` vs
 * `supabase`/`useAuthStore` (`KB § 03-SEED-ARCHITECTURE.md` frontend
 * seams table): when both are present, `sessionAuth` wins. This exists
 * because every auth-adjacent action in this file (logout, password
 * change, activity-refresh) used to call `supabase.auth.*` directly and
 * unconditionally — a product that migrated its `AuthProvider` to
 * `createSessionAuthProvider` (httpOnly-cookie session) while Layout
 * stayed Supabase-bound got a SILENT NO-OP on logout: the session was
 * never established client-side, so `signOut()` had nothing to sign out
 * of, the `nai_session` cookie was never cleared, and the user was
 * redirected to `/login` while their session stayed LIVE. `sessionAuth`
 * makes that failure mode unrepresentable — see `erp-httponly-cookie-
 * session-2026-07` roadmap, engineer-C's Slice-3 blocker finding.
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
  usePageStatus, filterNavByPageStatus, env,
} from "@noctusai/lib";
import type { NavGroupWithRoute, NavItemWithRoute, StatusPagina } from "@noctusai/lib";
import { toast } from "sonner";
import { ChevronLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";
// Structural (duck-typed) supabase shape — see the note in app.tsx. The layout
// only touches `.auth` (refresh/signOut/updateUser) and `.from` (usePageStatus),
// so it never needs the real SupabaseClient class identity (non-assignable across
// two installed @supabase/supabase-js copies due to its `protected supabaseUrl`).
type AnySupabaseClient = { auth: any; from: any };

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

/**
 * Cookie-session sibling of the default `supabase`-based auth wiring — the
 * seam a product on `createSessionAuthProvider` (httpOnly-cookie session,
 * `seed/lib/frontend/src/auth.ts`) supplies instead of a live Supabase-JS
 * client. See the module docstring above for the full "why" (the silent
 * logout no-op this type makes unrepresentable).
 *
 * Every field except `useStatusPaginas` is REQUIRED — a session-mode
 * product cannot construct a `Layout` with a dead button standing in for
 * logout/password-change/session-extend. There is no default that could
 * be correct without knowing the product's own backend contract for
 * those actions (unlike Supabase mode, which has one universal
 * `supabase.auth.*` shape to default to).
 *
 * `usePageStatus` (`@noctusai/lib`) is an RLS `.from('status_pagina')`
 * read — it needs a user-JWT Supabase client, which cookie-session mode
 * doesn't have (the session lives server-side; the browser never holds
 * a JWT). No seed-level backend route serves `status_pagina` over the
 * cookie session yet (a future slice, not this one). `useStatusPaginas`
 * is therefore the one OPTIONAL field: omitting it degrades to exactly
 * the SAME fallback Supabase-mode already uses while its own query is
 * still loading — `navGroupsFallback` (unfiltered nav, no dev-page
 * gating). Not new fake behavior invented for session mode; the
 * pre-existing "no status data yet" path, reused honestly.
 */
export interface LayoutSessionAuth {
  /**
   * MUST actually invalidate the server-side session — e.g.
   * `logoutSession()` from `@noctusai/lib` (`POST /api/auth/logout`,
   * SEC-4 upstream-revoke). A handler that only clears client-side state
   * reproduces the exact silent-no-op bug this type exists to prevent.
   */
  onLogout: () => Promise<void>;
  /**
   * Change password. No seed-level cookie-session password-change
   * endpoint ships yet — wire this to the product's own backend route.
   */
  onUpdatePassword: (newPassword: string) => Promise<void>;
  /**
   * Update profile (name/email/phone) — the session-mode counterpart of
   * this file's default Supabase `handleUpdateProfile`
   * (`supabase.auth.updateUser`). `LayoutEnrichment.onUpdateProfile`
   * still overrides this per-render when the product's
   * `useLayoutEnrichment` hook returns one.
   */
  onUpdateProfile: (data: { name: string; email: string; phone: string }) => Promise<void>;
  /**
   * Called by `useActivityRefresh` (periodic, activity-gated) and
   * `InactivityWarning.onExtend` ("Continuar" click) to keep the session
   * alive. Supabase mode calls `supabase.auth.refreshSession()`;
   * cookie-session mode has no client-refreshable JWT — wire this to
   * whatever session-touch/extend mechanism the product's backend
   * exposes (verify the actual `SessionStore` TTL semantics before
   * assuming a bare re-`GET /api/auth/me` is sufficient).
   */
  onExtend: () => Promise<void>;
  /**
   * Optional page-status source for nav dev-gating — see the class
   * doc above. Shape mirrors the `{ data }` slice of `usePageStatus`'s
   * TanStack Query result so a product can wire this to its own
   * `useQuery` once it has a backend endpoint, or to a plain value.
   */
  useStatusPaginas?: () => { data?: StatusPagina[] };
}

export interface ProductLayoutConfig {
  brandIcon: LucideIcon;
  brandTitle: string;
  navGroups: NavGroupWithRoute[];
  navGroupsFallback: NavGroup[];
  /** Supabase-JS client — the default auth path. Required unless `sessionAuth` is provided. */
  supabase?: AnySupabaseClient;
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
  /**
   * Cookie-session auth overrides — the sibling of `supabase` for
   * products on `createSessionAuthProvider`. See `LayoutSessionAuth` for
   * the full rationale. When both `supabase` AND `sessionAuth` are
   * provided, `sessionAuth` WINS (same precedence as `createProductApp`'s
   * `authProvider` over `supabase`/`useAuthStore`). Required unless
   * `supabase` is provided.
   */
  sessionAuth?: LayoutSessionAuth;
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

// Canonical seed resolver (env.CORE_URL) — same-origin + house-port dev
// default. Never hand-roll `VITE_CORE_URL || localhost:5173` (the stale-port
// landmine: 5173 is the dead pre-house vite port). Non-local deploys set
// VITE_CORE_URL; the getter encodes the fallback once for every consumer.
const CORE_URL = env.CORE_URL;

const BackToCore = (
  <a
    href={CORE_URL}
    className="flex items-center gap-3 px-3 py-1.5 rounded-md text-sm font-medium text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
  >
    <ChevronLeft className="h-4 w-4 shrink-0" />
    Voltar ao NoctusAI
  </a>
);

// Sentinel passed to `usePageStatus` when there's no real Supabase client
// (session-auth mode). The query's `enabled` flag is `false` in that case,
// so TanStack Query never invokes `queryFn` — this object only exists so
// the hook can be called UNCONDITIONALLY every render (Rules of Hooks)
// regardless of auth mode, without smuggling a real client through. If it's
// ever reached anyway (a TanStack Query behavior change), it throws loudly
// instead of returning fake data — no silent errors.
const UNREACHABLE_SUPABASE: AnySupabaseClient = {
  auth: {},
  from: () => {
    throw new Error(
      "createProductLayout: usePageStatus queryFn ran with no supabase client " +
        "(session-auth mode) — this should be unreachable because `enabled` is " +
        "false. If you see this, TanStack Query's enabled-gating behavior changed.",
    );
  },
};

/**
 * No-op fallback when `sessionAuth.useStatusPaginas` isn't supplied. Mirrors
 * the existing "no status data yet" degrade path (nav renders unfiltered via
 * `navGroupsFallback`) — not new behavior invented for session mode.
 */
function useNoStatusPaginas(): { data?: StatusPagina[] } {
  return { data: undefined };
}

export function createProductLayout(config: ProductLayoutConfig) {
  const {
    brandIcon,
    brandTitle,
    navGroups: navGroupsWithRoutes,
    navGroupsFallback,
    standaloneItems: standaloneWithRoutes,
    standaloneItemsFallback,
    supabase,
    sessionAuth,
    useAuthStore,
    NotificationBell,
    roleLabels = DEFAULT_ROLE_LABELS,
    defaultRoleLabel = "Membro",
    roleLabelOverride,
    brandSubtitleOverride,
    useLayoutEnrichment,
  } = config;

  if (!sessionAuth && !supabase) {
    throw new Error(
      "createProductLayout: must provide either `sessionAuth` (cookie-session " +
        "auth overrides) or `supabase` (Supabase-JS client).",
    );
  }

  // Resolved ONCE per `createProductLayout()` call (not per render) — stable
  // for this Layout's whole lifetime, so calling this hook slot unconditionally
  // every render doesn't break the Rules of Hooks (the branch is invariant).
  const useSessionStatusPaginas = sessionAuth?.useStatusPaginas ?? useNoStatusPaginas;

  return function Layout({ children }: { children: React.ReactNode }) {
    const { user } = useAuthStore();

    // Call enrichment hook if provided (must be called unconditionally — hooks rules)
    const enrichment: LayoutEnrichment = useLayoutEnrichment ? useLayoutEnrichment() : {};

    // Theme — supports DB persistence via enrichment
    const { theme, toggleTheme } = useTheme({
      initialTheme: enrichment.initialTheme,
      onPersist: enrichment.onThemePersist,
    });

    // Shared by useActivityRefresh (periodic) + InactivityWarning.onExtend
    // ("Continuar" click) — see `LayoutSessionAuth.onExtend` doc for why
    // cookie-session mode needs a distinct implementation. `sessionAuth` /
    // `supabase` are closed over from `createProductLayout`'s config and
    // never change for this Layout's lifetime, so the empty dep array is
    // correct (not a missing-deps lint gap).
    const extendSession = useCallback(async () => {
      if (sessionAuth) {
        await sessionAuth.onExtend();
      } else {
        await supabase!.auth.refreshSession();
      }
    }, []);

    useActivityRefresh({ onRefresh: extendSession });

    // All hooks must be called before any conditional return (Rules of Hooks).
    // Exactly one of these two "hook slots" is live for a given Layout
    // instance (decided once at `createProductLayout()` call time — see
    // `UNREACHABLE_SUPABASE` / `useSessionStatusPaginas` above), so calling
    // both unconditionally every render doesn't break the Rules of Hooks.
    const { data: supabaseStatusPaginas } = usePageStatus(
      supabase ?? UNREACHABLE_SUPABASE,
      !sessionAuth && !!user && !!supabase,
    );
    const { data: sessionStatusPaginas } = useSessionStatusPaginas();
    const statusPaginas = sessionAuth ? sessionStatusPaginas : supabaseStatusPaginas;

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

    // Logout — the load-bearing seam this whole dual-mode design exists
    // for (see the module docstring). `sessionAuth.onLogout` MUST actually
    // invalidate the server-side session; there is no default fallback
    // here on purpose — a silent no-op is exactly the bug being prevented.
    const handleLogout = async () => {
      if (sessionAuth) {
        await sessionAuth.onLogout();
      } else {
        await supabase!.auth.signOut();
      }
      window.location.href = ssoCtx.isSSO ? CORE_URL : "/login";
    };

    // Profile update — enrichment override wins; otherwise the per-mode
    // default (Supabase `auth.updateUser`, or the required
    // `sessionAuth.onUpdateProfile` in cookie-session mode).
    const handleUpdateProfile = enrichment.onUpdateProfile || (sessionAuth
      ? sessionAuth.onUpdateProfile
      : (async (data: { name: string; email: string; phone: string }) => {
          const { error } = await supabase!.auth.updateUser({
            data: { full_name: data.name, phone: data.phone },
          });
          if (error) throw error;
          toast.success("Perfil atualizado com sucesso!");
        }));

    const handleUpdatePassword = async (newPassword: string) => {
      if (sessionAuth) {
        await sessionAuth.onUpdatePassword(newPassword);
      } else {
        const { error } = await supabase!.auth.updateUser({ password: newPassword });
        if (error) throw error;
      }
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
            // The header user-card button is a REAL logout (calls handleLogout →
            // supabase.auth.signOut() + redirect). "Voltar ao NoctusAI" (the
            // redirect-to-hub link) is a SEPARATE control — the Sidebar footer
            // `BackToCore` above — so the two coexist with distinct behaviour.
            // Was "redirect", which made this button silently skip signOut and
            // leave the session live (fixed 2026-07-07).
            logoutBehavior="signout"
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
          onExtend={extendSession}
          onExpired={() => { window.location.href = CORE_URL; }}
        />
      </AppShell>
    );
  };
}
