import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useDashboardResumo() {
  return useQuery({
    queryKey: ["bi-dashboard"],
    queryFn: () => api.get("/api/bi/dashboard"),
    staleTime: 1000 * 60 * 2,
  });
}

export function useBIVendas(periodoInicio?: string, periodoFim?: string) {
  const params: Record<string, string> = {};
  if (periodoInicio) params.periodo_inicio = periodoInicio;
  if (periodoFim) params.periodo_fim = periodoFim;
  return useQuery({
    queryKey: ["bi-vendas", periodoInicio, periodoFim],
    queryFn: () => api.get("/api/bi/vendas", params),
  });
}

export function useBICaptacao() {
  return useQuery({
    queryKey: ["bi-captacao"],
    queryFn: () => api.get("/api/bi/captacao"),
  });
}

export function useBICorretores(periodo?: string) {
  const params: Record<string, string> = {};
  if (periodo) params.periodo = periodo;
  return useQuery({
    queryKey: ["bi-corretores", periodo],
    queryFn: () => api.get("/api/bi/corretores", params),
  });
}

export function useBIImoveis() {
  return useQuery({
    queryKey: ["bi-imoveis"],
    queryFn: () => api.get("/api/bi/imoveis"),
  });
}

export function useBIFinanceiro(periodoInicio?: string, periodoFim?: string) {
  const params: Record<string, string> = {};
  if (periodoInicio) params.periodo_inicio = periodoInicio;
  if (periodoFim) params.periodo_fim = periodoFim;
  return useQuery({
    queryKey: ["bi-financeiro", periodoInicio, periodoFim],
    queryFn: () => api.get("/api/bi/financeiro", params),
  });
}
