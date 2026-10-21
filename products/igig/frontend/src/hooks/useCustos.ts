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
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";
import { addTo, patchById, removeById } from "@/lib/cacheOps";

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

const FUNCOES_KEY = [...CUSTOS_QUERY_KEY, "funcoes"] as const;
const PROFISSIONAIS_KEY = [...CUSTOS_QUERY_KEY, "profissionais"] as const;

/** Both lists move together — see the module note: a função's rate changes
 * what its profissionais cost, a profissional's resolved rate is computed
 * server-side. The written row shows at once; the other list settles. */
const AMBAS = [CUSTOS_QUERY_KEY];

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
  type Vars = { nome: string; custo_hora_padrao: number };
  return useCacheWriteMutation<Funcao, Vars>({
    mutationFn: (payload) => api.post<Funcao>("/api/custos/funcoes", payload),
    targets: [addTo<Funcao, Vars>(FUNCOES_KEY)],
    invalidate: AMBAS,
  });
}

export function useAtualizarFuncao() {
  type Vars = { id: string; nome?: string; custo_hora_padrao?: number };
  return useCacheWriteMutation<Funcao, Vars>({
    mutationFn: ({ id, ...patch }) => api.patch<Funcao>(`/api/custos/funcoes/${id}`, patch),
    targets: [patchById<Funcao, Vars>(FUNCOES_KEY, (v) => v.id, ({ id: _id, ...changes }) => changes)],
    invalidate: AMBAS,
  });
}

export function useRemoverFuncao() {
  return useCacheWriteMutation<{ ok: boolean }, string>({
    mutationFn: (id) => api.delete<{ ok: boolean }>(`/api/custos/funcoes/${id}`),
    targets: [removeById<{ ok: boolean }, string>(FUNCOES_KEY, (id) => id)],
    invalidate: AMBAS,
  });
}

// ─── Profissionais ─────────────────────────────────────────────────────────

/** `apenasAtivos` maps to `?apenas_ativos=true` — omitted (the default) lists
 * everyone, inactive profissionais included; the esteira's "Responsável"
 * picker asks for `true` (achado 21). */
export function useProfissionais(apenasAtivos?: boolean) {
  const query = useQuery({
    queryKey: [...CUSTOS_QUERY_KEY, "profissionais", apenasAtivos ?? false],
    queryFn: () =>
      api.get<Profissional[]>(
        "/api/custos/profissionais",
        apenasAtivos ? { apenas_ativos: true } : {},
      ),
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
  /**
   * The `public.noctus_users` id this person signs in as.
   *
   * LOAD-BEARING, not optional metadata. The timesheet stores apontamentos
   * against the signed-in user, and `bi_service` maps hours to a rate via
   * `profissional.usuario_id` — a profissional without it is SKIPPED, so their
   * hours cost nothing. Leave it unset and the BI's custo real and the DRE's
   * margin stay at zero no matter how carefully the rates are filled in.
   */
  usuario_id?: string | null;
  ativo?: boolean;
}

/** A team member, from the framework's `/api/team` — the candidates a
 *  profissional can be bound to. */
export interface MembroEquipe {
  id: string;
  nome: string;
  email: string;
}

export function useMembrosEquipe() {
  const query = useQuery({
    queryKey: ["igig", "equipe", "membros"],
    queryFn: () => api.get<{ data: MembroEquipe[] }>("/api/team"),
  });
  return {
    ...query,
    membros: query.data?.data ?? [],
    loading: query.isPending && !query.data,
  };
}

export function useCriarProfissional() {
  return useCacheWriteMutation<Profissional, ProfissionalPayload>({
    mutationFn: (payload) => api.post<Profissional>("/api/custos/profissionais", payload),
    targets: [
      // Everyone list; the "só ativos" list too when the new person is active.
      addTo<Profissional, ProfissionalPayload>([...PROFISSIONAIS_KEY, false]),
      addTo<Profissional, ProfissionalPayload>([...PROFISSIONAIS_KEY, true], "append", (p) => (p.ativo ? p : null)),
    ],
    invalidate: AMBAS,
  });
}

/** Every field optional — a PATCH that toggles `ativo` must not be forced to
 *  resend `nome`, which would silently overwrite a concurrent rename. */
export type ProfissionalPatch = Partial<ProfissionalPayload> & { id: string };

export function useAtualizarProfissional() {
  return useCacheWriteMutation<Profissional, ProfissionalPatch>({
    mutationFn: ({ id, ...patch }) => api.patch<Profissional>(`/api/custos/profissionais/${id}`, patch),
    // Commit the server's row: it carries the RESOLVED rate (`custo_hora_efetivo`).
    targets: [patchById<Profissional, ProfissionalPatch>(PROFISSIONAIS_KEY, (v) => v.id, ({ id: _id, ...changes }) => changes)],
    invalidate: AMBAS,
  });
}

export function useRemoverProfissional() {
  return useCacheWriteMutation<{ ok: boolean }, string>({
    mutationFn: (id) => api.delete<{ ok: boolean }>(`/api/custos/profissionais/${id}`),
    targets: [removeById<{ ok: boolean }, string>(PROFISSIONAIS_KEY, (id) => id)],
    invalidate: AMBAS,
  });
}
