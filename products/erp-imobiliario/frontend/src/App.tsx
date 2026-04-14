import { useState, lazy, Suspense } from "react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { AuthProvider } from "./components/auth/AuthProvider";
import { LoginForm } from "./components/auth/LoginForm";
import { useAuthStore } from "./store/authStore";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { createQueryClient } from "@noctusai/shared/query-client";
import { PageSkeleton } from "@noctusai/shared/design-system";

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
const ImovelDetalhes = lazy(() => import("./pages/ImovelDetalhes"));
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
const ContratoDetalhes = lazy(() => import("./pages/ContratoDetalhes"));
const PropostaDetalhes = lazy(() => import("./pages/PropostaDetalhes"));
const LocacaoDetalhes = lazy(() => import("./pages/LocacaoDetalhes"));
const VistoriaDetalhes = lazy(() => import("./pages/VistoriaDetalhes"));
const PermutaDetalhes = lazy(() => import("./pages/PermutaDetalhes"));
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
const MetaAds = lazy(() => import("./pages/MetaAds"));
const WhatsAppInbox = lazy(() => import("./pages/WhatsAppInbox"));
const NotificacoesPage = lazy(() => import("./pages/Notificacoes"));
const Certidoes = lazy(() => import("./pages/Certidoes"));
const Matriculas = lazy(() => import("./pages/Matriculas"));
const AcceptInvite = lazy(() => import("./pages/AcceptInvite"));
const Equipe = lazy(() => import("./pages/Equipe"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));

const queryClient = createQueryClient();


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
          <Route path="/imoveis/:id" element={<ImovelDetalhes />} />
          <Route path="/condominios" element={<Condominios />} />
          <Route path="/permutas" element={<Permutas />} />
          <Route path="/permutas/:id" element={<PermutaDetalhes />} />
          <Route path="/negociacoes" element={<Negociacoes />} />
          <Route path="/metas" element={<Metas />} />
          <Route path="/usuarios" element={<Usuarios />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/comissoes" element={<Comissoes />} />
          <Route path="/portais" element={<Portais />} />
          <Route path="/financeiro" element={<Financeiro />} />
          <Route path="/propostas" element={<Propostas />} />
          <Route path="/propostas/:id" element={<PropostaDetalhes />} />
          <Route path="/documentos" element={<Documentos />} />
          <Route path="/locacoes" element={<Locacoes />} />
          <Route path="/locacoes/:id" element={<LocacaoDetalhes />} />
          <Route path="/vistorias" element={<Vistorias />} />
          <Route path="/vistorias/:id" element={<VistoriaDetalhes />} />
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
          <Route path="/contratos/:id" element={<ContratoDetalhes />} />
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
          <Route path="/meta-ads" element={<MetaAds />} />
          <Route path="/whatsapp" element={<WhatsAppInbox />} />
          <Route path="/notificacoes" element={<NotificacoesPage />} />
          <Route path="/certidoes" element={<Certidoes />} />
          <Route path="/matriculas" element={<Matriculas />} />
          <Route path="/equipe" element={<Equipe />} />
          <Route path="/log-acoes" element={<LogAcoes />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

function AppContent() {
  const { user, isInitialized } = useAuthStore();
  const [isSignUp, setIsSignUp] = useState(false);

  if (!isInitialized) {
    return <PageSkeleton />;
  }

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
                  {/* Public routes (must work without auth) */}
                  <Route path="/sso" element={<SSOCallback />} />
                  <Route path="/accept-invite/:token" element={<AcceptInvite />} />
                  <Route path="/forgot-password" element={<ForgotPassword />} />
                  {/* All other routes require authentication */}
                  <Route path="/*" element={<AppContent />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
            <Sonner />
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);

export default App;
