/**
 * Product Application Factory
 *
 * Creates a complete App component with the standard NoctusAI pattern.
 * Supports both flat routing (most products) and role-based routing
 * (products like Therapy with admin/therapist/patient roles).
 */
import { Suspense, type LazyExoticComponent } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { ErrorBoundary, createAuthProvider, SSOCallback, env } from "@noctusai/lib";
import { createQueryClient } from "@noctusai/lib/query-client";
import { PageSkeleton } from "@noctusai/lib/design-system";
import { ConsentSettingsPage } from "./pages/ConsentSettingsPage";
import { SemAcessoPage } from "./pages/SemAcessoPage";
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

// ── Deep-link-preserving login redirect ──────────────────────────────────
//
// An unauthenticated visitor opening an internal URL (e.g. a bookmarked
// "/clientes/123" or a link shared by a teammate) was bounced to Landing/
// Login and, after signing in, always landed on "/" — the deep link was
// silently discarded. Fixed HERE (the seed's own route guard), not per
// product: every `createProductApp` consumer inherits the fix.
//
// `sessionStorage` (not a query param) carries the intended path across the
// redirect — a query param would show up in the URL bar and could itself be
// abused as an open-redirect vector; `sessionStorage` is invisible and never
// leaves the browser. The value can ONLY ever be a same-origin relative path
// because it is captured from `useLocation()`, which reflects the CURRENT
// window location and can never contain a scheme or host — so there is no
// open-redirect surface even before the defense-in-depth check in
// `_consumeIntendedPath` below.
const _INTENDED_PATH_KEY = "noctus:intended-path";

function _rememberIntendedPath(pathname: string, search: string): void {
  const full = pathname + search;
  // Nothing to remember for the root itself, and never overwrite a real
  // intended path with the login/landing page we are about to bounce to.
  if (!full || full === "/") return;
  try {
    window.sessionStorage.setItem(_INTENDED_PATH_KEY, full);
  } catch {
    // Storage unavailable (private browsing / disabled) — the deep link is
    // lost, but that must never block the redirect itself.
  }
}

function _consumeIntendedPath(): string | null {
  let stored: string | null = null;
  try {
    stored = window.sessionStorage.getItem(_INTENDED_PATH_KEY);
    if (stored) window.sessionStorage.removeItem(_INTENDED_PATH_KEY);
  } catch {
    return null;
  }
  // Defense in depth: only ever follow a same-origin relative path, even
  // though `_rememberIntendedPath` can never have stored anything else.
  // `//evil.com` is browser-parsed as protocol-relative — reject it.
  if (stored && stored.startsWith("/") && !stored.startsWith("//")) {
    return stored;
  }
  return null;
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
  // The SSO audience binding needs this product's slug (VITE_PRODUCT_SLUG,
  // injected by createViteConfig). Never silently omit it: core refuses an
  // unbound token, so a product without a slug cannot log in.
  if (supabase && !env.PRODUCT_SLUG) {
    console.error(
      "createProductApp: VITE_PRODUCT_SLUG is empty — SSO redemption would omit " +
        "product_slug. Build with createViteConfig (derives it from start.sh / " +
        "products/<slug>/frontend).",
    );
  }
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
    const location = useLocation();

    if (!isInitialized) {
      return <PageSkeleton />;
    }

    if (!user) {
      // Remember where the visitor was actually trying to go BEFORE bouncing
      // them to Landing/login — otherwise a deep link (bookmark, shared URL)
      // is silently discarded and they always land on "/" post-login.
      _rememberIntendedPath(location.pathname, location.search);
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

    // Authenticated, and we just landed on "/" — the universal post-login
    // destination (every product's own Login page, and the seed's own
    // SSOCallback, `navigate`/redirect to "/" on success; neither is seed
    // route-guard code we can intercept there). Restore a remembered deep
    // link BEFORE any routing below runs. Any OTHER current path means the
    // visitor already navigated somewhere themselves — never override that.
    if (location.pathname === "/" && !location.search) {
      const intended = _consumeIntendedPath();
      if (intended) {
        return <Navigate to={intended} replace />;
      }
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
                  productSlug={env.PRODUCT_SLUG || undefined}
                  onIdentityChange={() => queryClient.clear()}
                />
              }
            />
          )}
          {/* Seed-mounted license-gate landing: every product gets it with zero
              per-product code. Public on purpose — the user is blocked BECAUSE
              their org has no license, so it cannot sit behind the auth guard. */}
          <Route
            path="/sem-acesso"
            element={
              <SemAcessoPage
                coreUrl={env.CORE_URL}
                onSignOut={async () => {
                  try {
                    await supabase?.auth.signOut();
                  } finally {
                    window.location.assign("/login");
                  }
                }}
              />
            }
          />
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
