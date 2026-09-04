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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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

/**
 * Both lists are invalidated after every write.
 *
 * Retiring an agent removes it from the active list and changes it in the
 * full one; creating adds it to both. Invalidating only the list the caller
 * happened to be reading is how the dropdown keeps offering a bank somebody
 * just retired on the other page.
 */
function useInvalidateAmbas() {
  const qc = useQueryClient();
  return () =>
    qc.invalidateQueries({ queryKey: ["sw", "agentes-financeiros"] });
}

export function useCriarAgenteFinanceiro() {
  const invalidate = useInvalidateAmbas();
  return useMutation({
    mutationFn: (dados: AgenteFinanceiroPatch) =>
      api.post<AgenteFinanceiro>(BASE, dados),
    onSuccess: invalidate,
  });
}

export function useAtualizarAgenteFinanceiro() {
  const invalidate = useInvalidateAmbas();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: AgenteFinanceiroPatch }) =>
      api.patch<AgenteFinanceiro>(`${BASE}/${encodeURIComponent(id)}`, patch),
    onSuccess: invalidate,
  });
}

export function useRemoverAgenteFinanceiro() {
  const invalidate = useInvalidateAmbas();
  return useMutation({
    mutationFn: (id: string) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    onSuccess: invalidate,
  });
}
