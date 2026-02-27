import { useState, lazy, Suspense } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { AuthProvider } from "./components/auth/AuthProvider";
import { LoginForm } from "./components/auth/LoginForm";
import { useAuthStore } from "./store/authStore";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorBoundary } from "./components/ErrorBoundary";

// Lazy load das páginas para melhor performance inicial
const Dashboard = lazy(() => import("./pages/Dashboard"));
const SSOCallback = lazy(() => import("./pages/SSOCallback"));
const Metas = lazy(() => import("./pages/Metas"));
const Usuarios = lazy(() => import("./pages/Usuarios"));
const Admin = lazy(() => import("./pages/Admin"));
const Funil = lazy(() => import("./pages/Funil"));
const Clientes = lazy(() => import("./pages/Clientes"));
const ClienteDetalhes = lazy(() => import("./pages/ClienteDetalhes"));
const NotFound = lazy(() => import("./pages/NotFound"));
const LogAcoes = lazy(() => import("./pages/LogAcoes"));
const Imoveis = lazy(() => import("./pages/Imoveis"));
const Permutas = lazy(() => import("./pages/Permutas"));
const Negociacoes = lazy(() => import("./pages/Negociacoes"));
const Condominios = lazy(() => import("./pages/Condominios"));
const Comissoes = lazy(() => import("./pages/Comissoes"));
const Portais = lazy(() => import("./pages/Portais"));
const Financeiro = lazy(() => import("./pages/Financeiro"));
const Propostas = lazy(() => import("./pages/Propostas"));
const Documentos = lazy(() => import("./pages/Documentos"));
const Locacoes = lazy(() => import("./pages/Locacoes"));
const Vistorias = lazy(() => import("./pages/Vistorias"));
const Relatorios = lazy(() => import("./pages/Relatorios"));
const Distribuicao = lazy(() => import("./pages/Distribuicao"));
const Marketing = lazy(() => import("./pages/Marketing"));
const Agenda = lazy(() => import("./pages/Agenda"));
const Dimob = lazy(() => import("./pages/Dimob"));
const Gamificacao = lazy(() => import("./pages/Gamificacao"));
const Chaves = lazy(() => import("./pages/Chaves"));
const PortalExterno = lazy(() => import("./pages/PortalExterno"));
const SiteImoveis = lazy(() => import("./pages/SiteImoveis"));
const Campo = lazy(() => import("./pages/Campo"));
const AnaliseCredito = lazy(() => import("./pages/AnaliseCredito"));
const Filiais = lazy(() => import("./pages/Filiais"));
const Contratos = lazy(() => import("./pages/Contratos"));
const Assinaturas = lazy(() => import("./pages/Assinaturas"));
const PortalCliente = lazy(() => import("./pages/PortalCliente"));
const Manutencao = lazy(() => import("./pages/Manutencao"));
const Seguros = lazy(() => import("./pages/Seguros"));
const Impostos = lazy(() => import("./pages/Impostos"));
const Banco = lazy(() => import("./pages/Banco"));
const Emails = lazy(() => import("./pages/Emails"));
const BI = lazy(() => import("./pages/BI"));
const Matching = lazy(() => import("./pages/Matching"));
const Configuracoes = lazy(() => import("./pages/Configuracoes"));

// QueryClient com configurações otimizadas
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutos - dados considerados "fresh"
      gcTime: 1000 * 60 * 10, // 10 minutos - tempo de cache
      refetchOnWindowFocus: false, // Evita refetches desnecessários
      retry: 1, // Reduz tentativas de retry
    },
  },
});

const PageSkeleton = () => (
  <div className="container mx-auto p-6 space-y-4">
    <Skeleton className="h-12 w-64" />
    <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
      <Skeleton className="h-32" />
    </div>
    <Skeleton className="h-96" />
  </div>
);

function AuthenticatedRoutes() {
  return (
    <Layout>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/funil" element={<Funil />} />
          <Route path="/clientes" element={<Clientes />} />
          <Route path="/clientes/:id" element={<ClienteDetalhes />} />
          <Route path="/imoveis" element={<Imoveis />} />
          <Route path="/condominios" element={<Condominios />} />
          <Route path="/permutas" element={<Permutas />} />
          <Route path="/negociacoes" element={<Negociacoes />} />
          <Route path="/metas" element={<Metas />} />
          <Route path="/usuarios" element={<Usuarios />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/comissoes" element={<Comissoes />} />
          <Route path="/portais" element={<Portais />} />
          <Route path="/financeiro" element={<Financeiro />} />
          <Route path="/propostas" element={<Propostas />} />
          <Route path="/documentos" element={<Documentos />} />
          <Route path="/locacoes" element={<Locacoes />} />
          <Route path="/vistorias" element={<Vistorias />} />
          <Route path="/relatorios" element={<Relatorios />} />
          <Route path="/distribuicao" element={<Distribuicao />} />
          <Route path="/marketing" element={<Marketing />} />
          <Route path="/agenda" element={<Agenda />} />
          <Route path="/dimob" element={<Dimob />} />
          <Route path="/gamificacao" element={<Gamificacao />} />
          <Route path="/chaves" element={<Chaves />} />
          <Route path="/portal" element={<PortalExterno />} />
          <Route path="/site" element={<SiteImoveis />} />
          <Route path="/campo" element={<Campo />} />
          <Route path="/analise-credito" element={<AnaliseCredito />} />
          <Route path="/filiais" element={<Filiais />} />
          <Route path="/contratos" element={<Contratos />} />
          <Route path="/assinaturas" element={<Assinaturas />} />
          <Route path="/portal-cliente" element={<PortalCliente />} />
          <Route path="/manutencao" element={<Manutencao />} />
          <Route path="/seguros" element={<Seguros />} />
          <Route path="/impostos" element={<Impostos />} />
          <Route path="/banco" element={<Banco />} />
          <Route path="/emails" element={<Emails />} />
          <Route path="/bi" element={<BI />} />
          <Route path="/matching" element={<Matching />} />
          <Route path="/configuracoes" element={<Configuracoes />} />
          <Route path="/log-acoes" element={<LogAcoes />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

function AppContent() {
  const { user } = useAuthStore();
  const [isSignUp, setIsSignUp] = useState(false);

  if (!user) {
    return <LoginForm onToggleMode={() => setIsSignUp(!isSignUp)} isSignUp={isSignUp} />;
  }

  return <AuthenticatedRoutes />;
}

const App = () => (
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <AuthProvider>
            <ErrorBoundary>
              <Suspense fallback={<PageSkeleton />}>
                <Routes>
                  {/* Public route: SSO callback (must work without auth) */}
                  <Route path="/sso" element={<SSOCallback />} />
                  {/* All other routes require authentication */}
                  <Route path="/*" element={<AppContent />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
            <Toaster />
            <Sonner />
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);

export default App;
