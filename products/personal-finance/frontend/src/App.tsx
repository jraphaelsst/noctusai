import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, QueryCache } from "@tanstack/react-query";
import { Toaster, toast } from "sonner";
import { AuthProvider } from "@/components/auth/AuthProvider";
import { Layout } from "@/components/layout/Layout";
import { useAuthStore } from "@/store/authStore";

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      toast.error("Erro ao carregar dados", { description: error.message });
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

// Lazy pages
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
const Recorrentes = lazy(() => import("@/pages/Recorrentes"));
const Patrimonio = lazy(() => import("@/pages/Patrimonio"));
const Relatorios = lazy(() => import("@/pages/Relatorios"));
const SSOCallback = lazy(() => import("@/pages/SSOCallback"));

function PageSkeleton() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/sso" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/sso" element={<SSOCallback />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout>
                <Suspense fallback={<PageSkeleton />}>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/contas" element={<Contas />} />
                    <Route path="/contas/:id" element={<ContaDetalhes />} />
                    <Route path="/transacoes" element={<Transacoes />} />
                    <Route path="/orcamentos" element={<Orcamentos />} />
                    <Route path="/orcamentos/:id" element={<OrcamentoDetalhes />} />
                    <Route path="/metas" element={<Metas />} />
                    <Route path="/metas/:id" element={<MetaDetalhes />} />
                    <Route path="/carteira" element={<Carteira />} />
                    <Route path="/carteira/:id" element={<CarteiraDetalhes />} />
                    <Route path="/watchlist" element={<Watchlist />} />
                    <Route path="/watchlist/:id" element={<WatchlistDetalhes />} />
                    <Route path="/recorrentes" element={<Recorrentes />} />
                    <Route path="/patrimonio" element={<Patrimonio />} />
                    <Route path="/relatorios" element={<Relatorios />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Suspense>
              </Layout>
            </ProtectedRoute>
          }
        />
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
