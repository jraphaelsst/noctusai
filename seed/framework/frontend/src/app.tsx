/**
 * Product Application Factory
 *
 * Creates a complete App component with the standard NoctusAI pattern:
 * - QueryClientProvider + TooltipProvider (structural providers)
 * - BrowserRouter with auth-gated routing
 * - Standard public routes (landing, login, SSO, accept-invite, forgot-password)
 * - Lazy-loaded pages with Suspense + PageSkeleton
 * - ErrorBoundary wrapper
 * - Toaster (sonner)
 *
 * Products only provide: their authenticated routes and the Layout component.
 */
import { Suspense, lazy, type LazyExoticComponent } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { ErrorBoundary } from "@noctusai/shared";
import { createAuthProvider } from "@noctusai/shared";
import { createQueryClient } from "@noctusai/shared/query-client";
import { PageSkeleton } from "@noctusai/shared/design-system";
import { SSOCallback } from "@noctusai/shared";
import type { SupabaseClient } from "@supabase/supabase-js";

export interface ProductRoute {
  path: string;
  component: LazyExoticComponent<any>;
}

export interface ProductAppConfig {
  /** Authenticated routes (product pages) */
  routes: ProductRoute[];
  /** Layout component (from createProductLayout) */
  Layout: React.ComponentType<{ children: React.ReactNode }>;
  /** Supabase client instance */
  supabase: SupabaseClient;
  /** Auth store hook */
  useAuthStore: () => { user: any; isInitialized: boolean };
  /** Custom Landing page component (lazy) */
  Landing?: LazyExoticComponent<any>;
  /** Custom Login page component (lazy) */
  Login?: LazyExoticComponent<any>;
  /** Custom AcceptInvite page component (lazy) */
  AcceptInvite?: LazyExoticComponent<any>;
  /** Custom ForgotPassword page component (lazy) */
  ForgotPassword?: LazyExoticComponent<any>;
  /** Custom NotFound page component (lazy) */
  NotFound?: LazyExoticComponent<any>;
  /** Additional public routes (no auth required) */
  publicRoutes?: ProductRoute[];
}

// Default page components from shared (products can override)
const DefaultLanding = lazy(() => import("@noctusai/shared/design-system").then(m => ({ default: () => null })));
const DefaultNotFound = lazy(() => import("@noctusai/shared/design-system").then(m => ({ default: () => null })));

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
  } = config;

  const queryClient = createQueryClient();
  const AuthProvider = createAuthProvider(supabase, useAuthStore);

  function AppContent() {
    const { user, isInitialized } = useAuthStore();

    if (!isInitialized) {
      return <PageSkeleton />;
    }

    if (!user) {
      return <Navigate to="/landing" replace />;
    }

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

  function AppRoutes() {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          {Landing && <Route path="/landing" element={<Landing />} />}
          {Login && <Route path="/login" element={<Login />} />}
          <Route path="/sso" element={<SSOCallback />} />
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
