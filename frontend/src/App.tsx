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

// Lazy load das páginas para melhor performance inicial
const Dashboard = lazy(() => import("./pages/Dashboard"));
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

function AppContent() {
  const { user } = useAuthStore();
  const [isSignUp, setIsSignUp] = useState(false);

  if (!user) {
    return <LoginForm onToggleMode={() => setIsSignUp(!isSignUp)} isSignUp={isSignUp} />;
  }

  return (
    <BrowserRouter>
      <Layout>
        <Suspense fallback={
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
        }>
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
            <Route path="/log-acoes" element={<LogAcoes />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <AuthProvider>
        <AppContent />
        <Toaster />
        <Sonner />
      </AuthProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
