import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Layout } from "@/components/layout/Layout";
import { useAuthStore } from "@/store/authStore";
import { createQueryClient } from "@noctusai/shared/query-client";
import { PageSkeleton } from "@noctusai/shared/design-system";

const queryClient = createQueryClient();

// Lazy pages — public
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const SSOCallback = lazy(() => import("@/pages/SSOCallback"));
const AcceptInvite = lazy(() => import("@/pages/AcceptInvite"));
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"));

// Lazy pages — authenticated
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Contas = lazy(() => import("@/pages/Contas"));
const Transacoes = lazy(() => import("@/pages/Transacoes"));
const Orcamentos = lazy(() => import("@/pages/Orcamentos"));
const Metas = lazy(() => import("@/pages/Metas"));
const Carteira = lazy(() => import("@/pages/Carteira"));
const CarteiraDetalhes = lazy(() => import("@/pages/CarteiraDetalhes"));
const Watchlist = lazy(() => import("@/pages/Watchlist"));
const ContaDetalhes = lazy(() => import("@/pages/ContaDetalhes"));
const OrcamentoDetalhes = lazy(() => import("@/pages/OrcamentoDetalhes"));
const MetaDetalhes = lazy(() => import("@/pages/MetaDetalhes"));
const WatchlistDetalhes = lazy(() => import("@/pages/WatchlistDetalhes"));
const Categorias = lazy(() => import("@/pages/Categorias"));
const Recorrentes = lazy(() => import("@/pages/Recorrentes"));
const Patrimonio = lazy(() => import("@/pages/Patrimonio"));
const Operacoes = lazy(() => import("@/pages/Operacoes"));
const Relatorios = lazy(() => import("@/pages/Relatorios"));
const Equipe = lazy(() => import("@/pages/Equipe"));
const NotFound = lazy(() => import("@/pages/NotFound"));

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
            <Route path="/" element={<Dashboard />} />
            <Route path="/contas" element={<Contas />} />
            <Route path="/contas/:id" element={<ContaDetalhes />} />
            <Route path="/transacoes" element={<Transacoes />} />
            <Route path="/categorias" element={<Categorias />} />
            <Route path="/orcamentos" element={<Orcamentos />} />
            <Route path="/orcamentos/:id" element={<OrcamentoDetalhes />} />
            <Route path="/metas" element={<Metas />} />
            <Route path="/metas/:id" element={<MetaDetalhes />} />
            <Route path="/carteira" element={<Carteira />} />
            <Route path="/carteira/:id" element={<CarteiraDetalhes />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/watchlist/:id" element={<WatchlistDetalhes />} />
            <Route path="/operacoes" element={<Operacoes />} />
            <Route path="/recorrentes" element={<Recorrentes />} />
            <Route path="/patrimonio" element={<Patrimonio />} />
            <Route path="/relatorios" element={<Relatorios />} />
            <Route path="/equipe" element={<Equipe />} />
            <Route path="*" element={<NotFound />} />
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
        <Route path="/landing" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/sso" element={<SSOCallback />} />
        <Route path="/accept-invite/:token" element={<AcceptInvite />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/*" element={<AppContent />} />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </QueryClientProvider>
  );
}
