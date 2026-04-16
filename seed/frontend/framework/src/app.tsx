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
import { ErrorBoundary, createAuthProvider, SSOCallback } from "@noctusai/lib";
import { createQueryClient } from "@noctusai/lib/query-client";
import { PageSkeleton } from "@noctusai/lib/design-system";
import type { SupabaseClient } from "@supabase/supabase-js";

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

export interface ProductAppConfig {
  /** Flat routes — for products with a single role/layout */
  routes?: ProductRoute[];
  /** Layout for flat routing */
  Layout?: React.ComponentType<{ children: React.ReactNode }>;
  /** Supabase client */
  supabase: SupabaseClient<any, any, any>;
  /** Full auth store hook */
  useAuthStore: () => any;
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
    Landing,
    Login,
    AcceptInvite,
    ForgotPassword,
    NotFound,
    publicRoutes = [],
    roleRoutes,
    resolveRole,
    defaultRedirect,
    unwrappedRoutes = [],
  } = config;

  const queryClient = createQueryClient();
  const AuthProvider = createAuthProvider(supabase, useAuthStore);

  // Flat routing — single Layout, single set of routes
  function FlatContent() {
    if (!Layout || !routes) return null;
    return (
      <Layout>
        <ErrorBoundary>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
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
    const { user } = useAuthStore();
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
    const { user, isInitialized } = useAuthStore();

    if (!isInitialized) {
      return <PageSkeleton />;
    }

    if (!user) {
      return <Navigate to="/landing" replace />;
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
          {Landing && <Route path="/landing" element={<Landing />} />}
          {Login && <Route path="/login" element={<Login />} />}
          <Route path="/sso" element={<SSOCallback supabase={supabase} />} />
          {AcceptInvite && <Route path="/accept-invite/:token" element={<AcceptInvite />} />}
          {ForgotPassword && <Route path="/forgot-password" element={<ForgotPassword />} />}
          {publicRoutes.map(({ path, component: Component }) => (
            <Route key={path} path={path} element={<Component />} />
          ))}
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
