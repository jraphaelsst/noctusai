/**
 * Dashboard hook — CONTRACT.md (ninho-vazio) §Cashflow + dashboard,
 * `GET /api/dashboard?meses=`.
 *
 * Every number on the page comes from this payload; the page never derives
 * a KPI of its own. Money fields are integer centavos.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { NivelGrupoterapia } from "@/hooks/usePlanos";

export interface DashboardPorPlano {
  plano_id: string | null;
  nome: string;
  nivel_grupoterapia: NivelGrupoterapia;
  membros: number;
}

export interface DashboardKpis {
  membros_total: number;
  membros_ativos: number;
  por_plano: DashboardPorPlano[];
  mrr_centavos: number;
  arpu_centavos: number;
  em_carencia: number;
  novos_mes: number;
  cancelamentos_mes: number;
  churn_mes_pct: number;
  receita_mes_centavos: number;
  saldo_mes_centavos: number;
  conversao_pago_pct: number;
}

export interface DashboardMes {
  /** `YYYY-MM` */
  mes: string;
  entradas_centavos: number;
  saidas_centavos: number;
  novos_membros: number;
  cancelamentos: number;
  mrr_centavos: number;
}

export interface DashboardGrupoterapia {
  sessao_id: string;
  titulo: string;
  inicio: string;
  vagas_fala: number;
  reservas: number;
}

export interface DashboardSeries {
  mensal: DashboardMes[];
  origem_membros: Array<{ origem: string; membros: number }>;
  status_membros: Array<{ status: string; membros: number }>;
  grupoterapia: DashboardGrupoterapia[];
}

export interface DashboardResponse {
  kpis: DashboardKpis;
  series: DashboardSeries;
  gerado_em: string;
}

export const dashboardKeys = {
  all: ["dashboard"] as const,
  detail: (meses: number) => ["dashboard", meses] as const,
};

/** `meses` is the window (1..24, backend default 12). */
export function useDashboard(meses = 12) {
  return useQuery({
    queryKey: dashboardKeys.detail(meses),
    queryFn: () => api.get<DashboardResponse>("/api/dashboard", { meses }),
    // Org-wide aggregates, not personal data — safe to keep the previous
    // window on screen while a new `meses` loads.
    placeholderData: keepPreviousData,
  });
}
