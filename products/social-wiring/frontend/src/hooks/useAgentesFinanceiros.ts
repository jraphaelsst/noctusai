/**
 * Agentes financeiros — the org's registry of financing banks (migration 100).
 *
 * Two consumers with DIFFERENT needs, which is why `incluirInativos` is a
 * parameter rather than a constant:
 *
 *  - the card's Financiamento dropdown asks for ACTIVE agents only. Offering a
 *    retired bank would let someone select an institution the agency no longer
 *    works with.
 *  - the management page asks for ALL of them. It is the surface where an
 *    agent is reactivated, and one you cannot see is one you cannot bring
 *    back.
 *
 * 🔴 RETIRE, NEVER DELETE. The delete endpoint 409s while any atendimento
 * points at an agent — the FK is `ON DELETE RESTRICT`. Retiring (`ativo:
 * false`) is the normal way one leaves the dropdown, and every deal it already
 * finances keeps rendering it. The UI says so at the point of the click rather
 * than letting the server's refusal be the first anyone hears of it.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface AgenteFinanceiro {
  id: string;
  nome: string;
  /** Brazilian payment-system code — "104" is Caixa. A STRING: the codes are
   *  zero-padded and "001" is not 1 on any document that prints it. */
  codigo_banco: string | null;
  agencia: string | null;
  contato_nome: string | null;
  contato_email: string | null;
  contato_telefone: string | null;
  observacoes: string | null;
  ativo: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgenteFinanceiroPatch {
  nome?: string;
  codigo_banco?: string | null;
  agencia?: string | null;
  contato_nome?: string | null;
  contato_email?: string | null;
  contato_telefone?: string | null;
  observacoes?: string | null;
  ativo?: boolean;
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const BASE = "/api/agentes-financeiros";

/** The flag is part of the key: the two consumers hold genuinely different
 *  lists, and sharing one cache entry would let the management page's fetch
 *  put retired banks into the card's dropdown. */
const KEY = (incluirInativos: boolean) =>
  ["sw", "agentes-financeiros", { incluirInativos }] as const;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useAgentesFinanceiros(incluirInativos = false) {
  return useQuery({
    queryKey: KEY(incluirInativos),
    queryFn: async () => {
      const res = await api.get<{ items: AgenteFinanceiro[]; total: number }>(
        `${BASE}?incluir_inativos=${incluirInativos}`,
      );
      return res?.items ?? [];
    },
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

const AGENTES_PREFIX = ["sw", "agentes-financeiros"] as const;

/**
 * Both lists (active-only and full) are written after every change.
 *
 * Retiring an agent removes it from the active list and changes it in the
 * full one; creating adds it to both. `match: 'prefix'` reaches each cached
 * list so the dropdown never keeps offering a bank somebody just retired on
 * the other page.
 */
export function useCriarAgenteFinanceiro() {
  return useCacheWriteMutation<AgenteFinanceiro, AgenteFinanceiroPatch>({
    mutationFn: (dados) => api.post<AgenteFinanceiro>(BASE, dados),
    targets: [
      {
        queryKey: AGENTES_PREFIX,
        match: "prefix",
        commit: (old: AgenteFinanceiro[] | undefined, saved) =>
          saved.ativo === false ? old : listOps.append(old, saved),
      },
    ],
  });
}

export function useAtualizarAgenteFinanceiro() {
  return useCacheWriteMutation<AgenteFinanceiro, { id: string; patch: AgenteFinanceiroPatch }>({
    mutationFn: ({ id, patch }) =>
      api.patch<AgenteFinanceiro>(`${BASE}/${encodeURIComponent(id)}`, patch),
    targets: [
      {
        queryKey: AGENTES_PREFIX,
        match: "prefix",
        optimistic: (old: AgenteFinanceiro[] | undefined, { id, patch }) =>
          listOps.patch(old, id, patch as Partial<AgenteFinanceiro>),
        // A retired agent leaves the active-only list on the settle refetch (the op cannot tell
        // which list it is editing); the full list already shows it correctly.
        commit: (old: AgenteFinanceiro[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
  });
}

export function useRemoverAgenteFinanceiro() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    targets: [
      {
        queryKey: AGENTES_PREFIX,
        match: "prefix",
        optimistic: (old: AgenteFinanceiro[] | undefined, id) => listOps.remove(old, id),
      },
    ],
  });
}
