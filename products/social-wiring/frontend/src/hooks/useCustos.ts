/**
 * `GET /api/custos` — per-integration spend for the Custos page.
 *
 * See `app/routers/custos_router.py` for the aggregation. USD→BRL uses the
 * latest stored PTAX bulletin; a missing bulletin surfaces as
 * `fx_pendente=true` with `custo_brl=null` rather than a guessed rate.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface CustosPorModelo {
  provider: string;
  model: string;
  chamadas: number;
  total_tokens: number;
  custo_usd: number;
  custo_brl: number | null;
}

export interface CustosPorDia {
  data: string;
  custo_brl: number;
}

export interface CustosIntegracao {
  nome: string;
  chamadas: number;
  custo_brl: number | null;
  fx_pendente: boolean;
  observacao: string | null;
}

export interface CustosOut {
  de: string;
  ate: string;
  total_brl: number;
  fx_pendente: boolean;
  integracoes: CustosIntegracao[];
  serie_diaria: CustosPorDia[];
  llm_por_modelo: CustosPorModelo[];
}

export type CustosPeriodo = "este_mes" | "ultimos_30_dias" | "mes_anterior";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Resolve a named period into `{from, to}` ISO date strings — pure, no
 * network — so the hook + a test can share the exact same boundary math. */
export function resolvePeriodo(periodo: CustosPeriodo, hoje: Date = new Date()): { from: string; to: string } {
  const ano = hoje.getUTCFullYear();
  const mes = hoje.getUTCMonth();
  switch (periodo) {
    case "ultimos_30_dias": {
      const from = new Date(hoje);
      from.setUTCDate(from.getUTCDate() - 29);
      return { from: isoDate(from), to: isoDate(hoje) };
    }
    case "mes_anterior": {
      const inicio = new Date(Date.UTC(ano, mes - 1, 1));
      const fim = new Date(Date.UTC(ano, mes, 0));
      return { from: isoDate(inicio), to: isoDate(fim) };
    }
    case "este_mes":
    default: {
      const inicio = new Date(Date.UTC(ano, mes, 1));
      return { from: isoDate(inicio), to: isoDate(hoje) };
    }
  }
}

export function useCustos(periodo: CustosPeriodo) {
  const { from, to } = resolvePeriodo(periodo);
  const query = useQuery({
    queryKey: ["custos", from, to],
    queryFn: () => api.get<CustosOut>(`/api/custos?from=${from}&to=${to}`),
    // Keep the previous period's numbers on screen while the new period
    // loads instead of blanking every card back to zero.
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}
