/**
 * Product Application Factory
 *
 * Creates a complete App component with the standard NoctusAI pattern.
 * Supports both flat routing (most products) and role-based routing
 * (products like Therapy with admin/therapist/patient roles).
 */
import { Suspense, type LazyExoticComponent } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { ErrorBoundary, createAuthProvider, SSOCallback, env } from "@noctusai/lib";
import { createQueryClient } from "@noctusai/lib/query-client";
import { PageSkeleton } from "@noctusai/lib/design-system";
import { ConsentSettingsPage } from "./pages/ConsentSettingsPage";
import { ConsentHubPage } from "./pages/consent/ConsentHubPage";
import { PrivacyPolicyPage } from "./pages/consent/PrivacyPolicyPage";
import { TermsOfUsePage } from "./pages/consent/TermsOfUsePage";

// The seed lib types every supabase seam STRUCTURALLY (duck-typed) so the public
// contract never couples to a specific @supabase/supabase-js COPY. Two installed
// versions of the package expose `supabaseUrl` as a `protected` member, which
// makes their SupabaseClient class identities non-assignable to each other even
// at <any, …> ("not a class derived from"). The framework follows that same
// pattern instead of importing the real SupabaseClient class — here only the
// `.auth` surface is used (createAuthProvider + SSOCallback).
type AnySupabaseClient = { auth: any };

export interface ProductRoute {
  path: string;
  component: LazyExoticComponent<any>;
}

/** Role-based route configuration — each role gets its own routes + layout */
export interface RoleRouteConfig {
  /** Routes for this role */
  routes: ProductRoute[];
  /** Layout component for this role (from createProductLayout) */
  Layout: React.ComponentType<{ children: React.ReactNode }>;
  /** Root path prefix for this role (e.g. "/admin", "/therapist") */
  pathPrefix?: string;
}

/**
 * Auth-provider interface for products whose auth model is NOT Supabase-based.
 *
 * Default path: products pass `supabase` + `useAuthStore` and the framework
 * wires up `createAuthProvider(supabase, useAuthStore)` internally. This works
 * for every consumer product (personal-finance, erp, therapy, etc.) whose
 * auth flows through Supabase.
 *
 * Custom path: products that ARE the identity provider (core control-plane)
 * supply a full `authProvider` so the framework delegates entirely. When
 * `authProvider` is present, `supabase` and `useAuthStore` become optional.
 *
 * The custom provider must expose:
 *   - `AuthProvider` — wraps children, manages auth state.
 *   - `useAuth` — hook returning at minimum `{ user, isInitialized }` so
 *     the framework's route guards + role resolution still work.
 */
export interface CustomAuthProvider {
  AuthProvider: React.ComponentType<{ children: React.ReactNode }>;
  useAuth: () => { user: unknown; isInitialized: boolean };
}

export interface ProductAppConfig {
  /** Flat routes — for products with a single role/layout */
  routes?: ProductRoute[];
  /** Layout for flat routing */
  Layout?: React.ComponentType<{ children: React.ReactNode }>;
  /** Supabase client (required unless `authProvider` is provided) */
  supabase?: AnySupabaseClient;
  /** Full auth store hook (required unless `authProvider` is provided) */
  useAuthStore?: () => any;
  /**
   * Custom auth provider. Overrides the default Supabase-based auth wiring.
   * Use this when a product is the identity provider itself (e.g. core) or
   * otherwise needs a non-Supabase auth flow. When provided, `supabase` and
   * `useAuthStore` are not read by the framework.
   */
  authProvider?: CustomAuthProvider;
  /** Standard public pages */
  Landing?: LazyExoticComponent<any>;
  Login?: LazyExoticComponent<any>;
  AcceptInvite?: LazyExoticComponent<any>;
  ForgotPassword?: LazyExoticComponent<any>;
  NotFound?: LazyExoticComponent<any>;
  /** Additional public routes (no auth) */
  publicRoutes?: ProductRoute[];
  /**
   * Role-based routing — for products with multiple user roles.
   * Map of role key → { routes, Layout, pathPrefix }.
   * Used with `resolveRole` to determine which role config to show.
   */
  roleRoutes?: Record<string, RoleRouteConfig>;
  /**
   * Resolve the user's role from auth metadata.
   * Returns a key that matches one of the `roleRoutes` keys.
   * Required when `roleRoutes` is provided.
   */
  resolveRole?: (user: any) => string;
  /**
   * Default redirect path after login.
   * For flat routing: defaults to "/".
   * For role routing: overrides the role-based redirect.
   */
  defaultRedirect?: string;
  /**
   * Path to redirect unauthenticated users who hit a non-root protected route.
   * Defaults to "/" which renders the Landing page at root (if provided).
   * Products without a Landing page MUST set this to "/login" to avoid a
   * redirect loop (no Landing → root falls through to this redirect → loop).
   */
  unauthRedirect?: string;
  /**
   * Routes that should render WITHOUT the Layout wrapper.
   * Useful for full-screen pages like video sessions.
   */
  unwrappedRoutes?: ProductRoute[];
}

export function createProductApp(config: ProductAppConfig) {
  const {
    routes,
    Layout,
    supabase,
    useAuthStore,
    authProvider,
    Landing,
    Login,
    AcceptInvite,
    ForgotPassword,
    NotFound,
    publicRoutes = [],
    roleRoutes,
    resolveRole,
    defaultRedirect,
    unauthRedirect = "/",
    unwrappedRoutes = [],
  } = config;

  if (!authProvider && (!supabase || !useAuthStore)) {
    throw new Error(
      "createProductApp: must provide either `authProvider` (custom auth) " +
        "or both `supabase` + `useAuthStore` (Supabase auth).",
    );
  }

  const queryClient = createQueryClient();
  const AuthProvider = authProvider
    ? authProvider.AuthProvider
    : createAuthProvider(supabase!, useAuthStore!);
  const useAuth: () => { user: unknown; isInitialized: boolean } = authProvider
    ? authProvider.useAuth
    : (useAuthStore as () => { user: unknown; isInitialized: boolean });

  // Flat routing — single Layout, single set of routes
  function FlatContent() {
    if (!Layout || !routes) return null;
    return (
      <Layout>
        <ErrorBoundary>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              {/* Seed-mounted routes — auto-injected for every product. */}
              <Route path="/settings/ai" element={<ConsentSettingsPage />} />
              {/* Product-specific routes. */}
              {routes.map(({ path, component: Component }) => (
                <Route key={path} path={path} element={<Component />} />
              ))}
              {NotFound && <Route path="*" element={<NotFound />} />}
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </Layout>
    );
  }

  // Role-based routing — different Layout + routes per role
  function RoleContent() {
    const { user } = useAuth();
    if (!roleRoutes || !resolveRole || !user) return null;

    const role = resolveRole(user);
    const roleConfig = roleRoutes[role];
    if (!roleConfig) return NotFound ? <NotFound /> : null;

    const { routes: roleSpecificRoutes, Layout: RoleLayout, pathPrefix } = roleConfig;

    return (
      <RoleLayout>
        <ErrorBoundary>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              {/* Seed-mounted routes — auto-injected for every role's
                  layout (every authenticated user can manage their own
                  consents regardless of role). */}
              <Route path="/settings/ai" element={<ConsentSettingsPage />} />
              {roleSpecificRoutes.map(({ path, component: Component }) => (
                <Route key={path} path={path} element={<Component />} />
              ))}
              {NotFound && <Route path="*" element={<NotFound />} />}
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </RoleLayout>
    );
  }

  function AppContent() {
    const { user, isInitialized } = useAuth();

    if (!isInitialized) {
      return <PageSkeleton />;
    }

    if (!user) {
      // When a Landing page is provided, serve it at "/" for unauthenticated
      // users and redirect any other protected path to "/" so the visitor
      // always lands on the public marketing page.
      // When no Landing is configured (e.g. products whose entry point is a
      // direct login), redirect to `unauthRedirect` (must be "/login" for
      // landing-less products to avoid a loop).
      if (Landing) {
        return (
          <Routes>
            <Route path="/" element={
              <Suspense fallback={<PageSkeleton />}><Landing /></Suspense>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        );
      }
      return <Navigate to={unauthRedirect} replace />;
    }

    // Determine redirect path
    const redirect = defaultRedirect || (roleRoutes && resolveRole
      ? (() => {
          const role = resolveRole(user);
          const rc = roleRoutes[role];
          return rc?.pathPrefix || rc?.routes[0]?.path || "/";
        })()
      : "/");

    return (
      <Routes>
        {/* Unwrapped routes (no Layout — e.g. full-screen video sessions) */}
        {unwrappedRoutes.map(({ path, component: Component }) => (
          <Route key={path} path={path} element={
            <Suspense fallback={<PageSkeleton />}><Component /></Suspense>
          } />
        ))}

        {/* Role-based routing */}
        {roleRoutes && Object.entries(roleRoutes).map(([roleKey, rc]) => (
          rc.pathPrefix
            ? <Route key={roleKey} path={`${rc.pathPrefix}/*`} element={<RoleContent />} />
            : null
        ))}

        {/* Default redirect for role routing */}
        {roleRoutes && <Route path="/" element={<Navigate to={redirect} replace />} />}

        {/* Flat routing */}
        {routes && <Route path="/*" element={<FlatContent />} />}

        {/* Catch-all for role routing without prefix */}
        {roleRoutes && !routes && <Route path="/*" element={<RoleContent />} />}
      </Routes>
    );
  }

  function AppRoutes() {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          {/* Back-compat: bookmarks / old SPA-shell redirects pointing to
              /landing are silently upgraded to "/" (the new canonical root). */}
          <Route path="/landing" element={<Navigate to="/" replace />} />
          {Login && <Route path="/login" element={<Login />} />}
          {supabase && (
            <Route
              path="/sso"
              element={
                // Resolve core's URL through the CANONICAL seed resolver
                // (`env.CORE_API_URL` / `env.CORE_URL`) — never hand-roll the
                // `import.meta.env.VITE_CORE_* || localhost` fallback (the
                // recurrence that broke SSO for every product whose bundle
                // bakes only VITE_CORE_URL → "Failed to fetch", 2026-05-25).
                // The getter encodes the same-origin fallback + house-port dev
                // default once, for every consumer.
                <SSOCallback
                  supabase={supabase}
                  coreApiUrl={env.CORE_API_URL}
                  coreUrl={env.CORE_URL}
                />
              }
            />
          )}
          {AcceptInvite && <Route path="/accept-invite/:token" element={<AcceptInvite />} />}
          {ForgotPassword && <Route path="/forgot-password" element={<ForgotPassword />} />}
          {publicRoutes.map(({ path, component: Component }) => (
            <Route key={path} path={path} element={<Component />} />
          ))}
          {/* Seed-mounted PUBLIC legal pages — auto-injected for every product,
              no auth, no Layout (Google/Meta verification crawlers must reach
              them). Platform-wide consent docs; see content/consent.ts. */}
          <Route path="/consent" element={<ConsentHubPage />} />
          <Route path="/consent/privacy-policy" element={<PrivacyPolicyPage />} />
          <Route path="/consent/terms-of-use" element={<TermsOfUsePage />} />
          <Route path="/*" element={<AppContent />} />
        </Routes>
      </Suspense>
    );
  }

  return function App() {
    return (
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <BrowserRouter>
            <AuthProvider>
              <AppRoutes />
            </AuthProvider>
          </BrowserRouter>
          <Toaster richColors position="top-right" />
        </TooltipProvider>
      </QueryClientProvider>
    );
  };
}
