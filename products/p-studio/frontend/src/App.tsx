import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { useAuth } from "@/stores/auth";
import { Protected } from "@/components/Protected";

import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import CRM from "@/pages/CRM";
import Agenda from "@/pages/Agenda";
import Producao from "@/pages/Producao";
import Imoveis from "@/pages/Imoveis";
import Servicos from "@/pages/Servicos";
import Financeiro from "@/pages/Financeiro";
import Equipamentos from "@/pages/Equipamentos";
import Clientes from "@/pages/Clientes";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

export default function App() {
  const init = useAuth((s) => s.init);
  useEffect(() => init(), [init]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/crm" element={<CRM />} />
            <Route path="/agenda" element={<Agenda />} />
            <Route path="/producao" element={<Producao />} />
            <Route path="/imoveis" element={<Imoveis />} />
            <Route path="/servicos" element={<Servicos />} />
            <Route path="/financeiro" element={<Financeiro />} />
            <Route path="/equipamentos" element={<Equipamentos />} />
            <Route path="/clientes" element={<Clientes />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </QueryClientProvider>
  );
}
