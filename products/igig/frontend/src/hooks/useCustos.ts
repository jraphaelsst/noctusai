/**
 * Custo/hora — funções e profissionais.
 *
 * The rate table that M1's calculadora, M5's BI de eficiência and M6's DRE all
 * price from. Until this surface existed the tables were reachable only from
 * the repository layer, so every one of those three reported R$ 0,00 — a
 * number that reads as an answer rather than as missing input.
 *
 * Both lists are invalidated together on every write: a função's default rate
 * changes what its profissionais cost, so refreshing only the mutated list
 * would leave the other showing a stale `custo_hora_efetivo`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";

export const CUSTOS_QUERY_KEY = ["igig", "custos"] as const;

export interface Funcao {
  id: string;
  org_id: string;
  nome: string;
  custo_hora_padrao: number;
}

export interface Profissional {
  id: string;
  org_id: string;
  nome: string;
  funcao_id: string | null;
  custo_hora_override: number | null;
  usuario_id: string | null;
  ativo: boolean;
  /** Resolved rate (override → função default). Null when undefined. */
  custo_hora_efetivo: number | null;
  /** No override AND no função — this person silently zeroes the DRE. */
  custo_hora_indefinido: boolean;
}

/** Both lists move together — see the module note. */
function useInvalidarCustos() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: CUSTOS_QUERY_KEY });
}

// ─── Funções ───────────────────────────────────────────────────────────────

export function useFuncoes() {
  const query = useQuery({
    queryKey: [...CUSTOS_QUERY_KEY, "funcoes"],
    queryFn: () => api.get<Funcao[]>("/api/custos/funcoes"),
  });
  return {
    ...query,
    funcoes: query.data ?? [],
    // Two signals, never `isLoading`: an empty state gated on `isLoading`
    // renders over data that is merely refetching.
    // → KB § PATTERNS/frontend/lying-loading-state.md
    loading: query.isPending && !query.data,
    refreshing: query.isFetching && !!query.data,
  };
}

export function useCriarFuncao() {
  const invalidar = useInvalidarCustos();
  return useMutation({
    mutationFn: (payload: { nome: string; custo_hora_padrao: number }) =>
      api.post<Funcao>("/api/custos/funcoes", payload),
    onSuccess: invalidar,
  });
}

export function useAtualizarFuncao() {
  const invalidar = useInvalidarCustos();
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: string; nome?: string; custo_hora_padrao?: number }) =>
      api.patch<Funcao>(`/api/custos/funcoes/${id}`, patch),
    onSuccess: invalidar,
  });
}

export function useRemoverFuncao() {
  const invalidar = useInvalidarCustos();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ ok: boolean }>(`/api/custos/funcoes/${id}`),
    onSuccess: invalidar,
  });
}

// ─── Profissionais ─────────────────────────────────────────────────────────

export function useProfissionais() {
  const query = useQuery({
    queryKey: [...CUSTOS_QUERY_KEY, "profissionais"],
    queryFn: () => api.get<Profissional[]>("/api/custos/profissionais"),
  });
  return {
    ...query,
    profissionais: query.data ?? [],
    loading: query.isPending && !query.data,
    refreshing: query.isFetching && !!query.data,
  };
}

export interface ProfissionalPayload {
  nome: string;
  funcao_id?: string | null;
  custo_hora_override?: number | null;
  ativo?: boolean;
}

export function useCriarProfissional() {
  const invalidar = useInvalidarCustos();
  return useMutation({
    mutationFn: (payload: ProfissionalPayload) =>
      api.post<Profissional>("/api/custos/profissionais", payload),
    onSuccess: invalidar,
  });
}

/** Every field optional — a PATCH that toggles `ativo` must not be forced to
 *  resend `nome`, which would silently overwrite a concurrent rename. */
export type ProfissionalPatch = Partial<ProfissionalPayload> & { id: string };

export function useAtualizarProfissional() {
  const invalidar = useInvalidarCustos();
  return useMutation({
    mutationFn: ({ id, ...patch }: ProfissionalPatch) =>
      api.patch<Profissional>(`/api/custos/profissionais/${id}`, patch),
    onSuccess: invalidar,
  });
}

export function useRemoverProfissional() {
  const invalidar = useInvalidarCustos();
  return useMutation({
    mutationFn: (id: string) => api.delete<{ ok: boolean }>(`/api/custos/profissionais/${id}`),
    onSuccess: invalidar,
  });
}
