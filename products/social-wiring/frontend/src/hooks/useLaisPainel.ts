/**
 * Lais › Painel (contract wave 9): GET /api/lais/painel?mes=YYYY-MM → {data}.
 * Loading = two signals off `data` (never `isLoading`); month change keeps the
 * previous month on screen (`placeholderData: prev`) with a refreshing marker.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface PainelConsumo { turnos: number; custo_usd: number; limite_diario_usd: number }
export interface Painel {
  atividades: { consumo: PainelConsumo | null; cobrancas: number; pre_agendamentos: number };
  funil: { topo: number; atendidos: number; enviados: number };
  por_canal: { canal: string; total: number }[];
  status_por_canal: { canal: string; enviado: number; nao_pronto: number; erro: number }[];
  por_hora: number[];
  fora_horario_pct: number;
  por_dia_semana: number[];
  melhor_dia: string | null;
  seis_meses: { mes: string; enviado: number; nao_enviado: number }[];
}

export function mesAtual(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function useLaisPainel(mes: string) {
  const q = useQuery({
    queryKey: ["lais", "painel", mes],
    queryFn: async () => (await api.get<{ data: Painel }>(`/api/lais/painel?mes=${mes}`)).data,
    placeholderData: keepPreviousData,
  });
  return {
    ...q,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
  };
}

export function pct(parte: number, total: number): number {
  return total > 0 ? Math.round((parte / total) * 100) : 0;
}
