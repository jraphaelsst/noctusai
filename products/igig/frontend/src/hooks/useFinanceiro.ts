/**
 * Financeiro hooks — Módulo 6.
 *
 * Backend mirror: `app/routers/financeiro_router.py`.
 *
 * Adding an invoice line returns the INVOICE, not the line, because the total
 * is derived server-side — a caller holding a stale total would show the
 * client a number that does not match the lines.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type StatusFatura = "aberta" | "enviada" | "paga" | "vencida" | "cancelada";
export type TipoItem = "mensalidade" | "excedente" | "desconto" | "avulso";

export interface Fatura {
  id: string;
  cliente_id: string;
  contrato_id: string | null;
  competencia: string;
  valor_total: number;
  vencimento: string | null;
  status: StatusFatura;
  pago_em: string | null;
}

export interface Excedente {
  cliente_id: string;
  cliente_nome: string;
  contrato_id: string;
  competencia: string;
  contratados: number;
  entregues: number;
  excedentes: number;
  valor_unitario: number;
  valor_total: number;
  /** The invoice this lands on — the month AFTER the work. */
  competencia_cobranca: string;
}

export interface DRE {
  cliente_id: string;
  cliente_nome: string;
  receita: number;
  custo: number;
  margem: number;
  margem_percentual: number;
  /** Non-empty ⇒ the margin is OVERSTATED. Must be shown, never hidden. */
  alertas: string[];
}

export interface Inadimplente {
  fatura_id: string;
  cliente_id: string;
  competencia: string;
  valor_total: number;
  vencimento: string;
  dias_atraso: number;
}

export const FINANCEIRO_QUERY_KEY = ["igig", "financeiro"] as const;

export function useFaturas(competencia?: string) {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "faturas", competencia ?? ""],
    queryFn: () =>
      api.get<Fatura[]>("/api/financeiro/faturas", competencia ? { competencia } : {}),
  });
  return { ...query, faturas: query.data ?? [], loading: query.isPending || query.isFetching };
}

export function useCriarFatura() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      cliente_id: string; competencia: string;
      contrato_id?: string; vencimento?: string;
    }) => api.post<Fatura>("/api/financeiro/faturas", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: FINANCEIRO_QUERY_KEY }),
  });
}

export function useAdicionarItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ faturaId, ...item }: {
      faturaId: string; descricao: string; tipo?: TipoItem;
      quantidade?: number; valor_unit?: number;
    }) => api.post<Fatura>(`/api/financeiro/faturas/${faturaId}/itens`, item),
    onSuccess: () => qc.invalidateQueries({ queryKey: FINANCEIRO_QUERY_KEY }),
  });
}

export function useMarcarPaga() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (faturaId: string) =>
      api.post<Fatura>(`/api/financeiro/faturas/${faturaId}/pagar`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: FINANCEIRO_QUERY_KEY }),
  });
}

export function useExcedentes(competencia: string) {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "excedentes", competencia],
    queryFn: () => api.get<Excedente[]>(`/api/financeiro/excedentes/${competencia}`),
    enabled: /^\d{4}-\d{2}$/.test(competencia),
  });
  return { ...query, excedentes: query.data ?? [], loading: query.isPending || query.isFetching };
}

export function useDRE(competencia?: string) {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "dre", competencia ?? ""],
    queryFn: () => api.get<DRE[]>("/api/financeiro/dre", competencia ? { competencia } : {}),
  });
  return { ...query, linhas: query.data ?? [], loading: query.isPending || query.isFetching };
}

export function useInadimplentes() {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "inadimplentes"],
    queryFn: () => api.get<Inadimplente[]>("/api/financeiro/inadimplentes"),
  });
  return { ...query, atrasadas: query.data ?? [], loading: query.isPending || query.isFetching };
}
