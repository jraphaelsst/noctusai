/**
 * Fluxo de caixa hooks — CONTRACT.md (ninho-vazio) §Cashflow + dashboard,
 * `/api/lancamentos*`.
 *
 * Automatic entries (`origem` = `pagamento` | `estorno`) are booked by the
 * billing webhooks and are read-only: PATCH/DELETE on them is a 409 on the
 * server, and the page never offers the controls.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { dashboardKeys } from "@/hooks/useDashboard";

export type LancamentoTipo = "entrada" | "saida";
export type LancamentoOrigem = "pagamento" | "estorno" | "manual";

export interface Lancamento {
  id: string;
  tipo: LancamentoTipo;
  categoria: string;
  descricao: string | null;
  valor_centavos: number;
  /** `YYYY-MM-DD` */
  data: string;
  origem: LancamentoOrigem;
  pagamento_id: string | null;
  membro_id: string | null;
  membro_nome: string | null;
  created_at: string;
}

export interface LancamentosTotais {
  entradas_centavos: number;
  saidas_centavos: number;
  saldo_centavos: number;
}

export interface LancamentoListResponse {
  items: Lancamento[];
  total: number;
  totais: LancamentosTotais;
}

export interface LancamentosParams {
  de?: string;
  ate?: string;
  tipo?: LancamentoTipo;
  categoria?: string;
  page?: number;
  page_size?: number;
}

export interface LancamentoInput {
  tipo: LancamentoTipo;
  categoria: string;
  descricao?: string | null;
  valor_centavos: number;
  data: string;
}

const lancamentosKeys = {
  all: ["lancamentos"] as const,
  list: (params?: LancamentosParams) => ["lancamentos", "list", params ?? {}] as const,
  categorias: ["lancamentos", "categorias"] as const,
};

export function useLancamentos(params?: LancamentosParams) {
  return useQuery({
    queryKey: lancamentosKeys.list(params),
    queryFn: () => api.get<LancamentoListResponse>("/api/lancamentos", params),
    placeholderData: keepPreviousData,
  });
}

export function useCategoriasLancamento() {
  return useQuery({
    queryKey: lancamentosKeys.categorias,
    queryFn: () => api.get<{ items: string[] }>("/api/lancamentos/categorias"),
  });
}

function useInvalidateCaixa() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: lancamentosKeys.all });
    // Receita/saldo do mês and the monthly series read the same rows.
    qc.invalidateQueries({ queryKey: dashboardKeys.all });
  };
}

export function useCreateLancamento() {
  const invalidate = useInvalidateCaixa();
  return useMutation({
    mutationFn: (data: LancamentoInput) => api.post<Lancamento>("/api/lancamentos", data),
    onSuccess: invalidate,
  });
}

export function useUpdateLancamento() {
  const invalidate = useInvalidateCaixa();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<LancamentoInput>) =>
      api.patch<Lancamento>(`/api/lancamentos/${id}`, data),
    onSuccess: invalidate,
  });
}

export function useDeleteLancamento() {
  const invalidate = useInvalidateCaixa();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/lancamentos/${id}`),
    onSuccess: invalidate,
  });
}
