/**
 * Favorecidos — the org's REGISTRY of payees (who receives a parcela's
 * money). Org-level, unrelated to any one card: a card SELECTS a registry
 * entry (`PUT .../atendimentos/{id}/favorecidos/selecao`, see
 * `useSelecionarFavorecidoRegistro` in `./useNegociacaoEstruturada`) instead
 * of free-typing bank data per negociação.
 *
 * 🔴 LGPD-FIRST. The LIST endpoint returns MASKED values only
 * (`cpf_cnpj_mascarado` / `pix_mascarado`); the clear values exist only on the
 * single-record GET, which the edit dialog alone calls. Nothing sensitive goes
 * in a URL: ids are opaque uuids, and the search term is a NAME (a document-
 * looking term is never sent — see `termoDeBuscaSeguro`).
 *
 * Contract (backend built in parallel): `FAVORECIDOS_API_BASE` is the one
 * place the prefix lives.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

export const FAVORECIDOS_API_BASE = "/api/card-hub/favorecidos";
export const FAVORECIDOS_KEY = ["sw", "favorecidos"] as const;

export type FavorecidoTipoPessoa = "PF" | "PJ";

/** One row of the LIST — masked, safe to render and to keep in a cache. */
export interface FavorecidoResumo {
  id: string;
  nome: string;
  tipo_pessoa: FavorecidoTipoPessoa;
  cpf_cnpj_mascarado: string | null;
  banco: string | null;
  banco_requer_revisao?: boolean;
  pix_tipo: string | null;
  pix_mascarado: string | null;
  ativo: boolean;
}

/** The full record (single GET) — clear values; only the edit dialog reads it. */
export interface FavorecidoCompleto {
  id: string;
  nome: string;
  tipo_pessoa: FavorecidoTipoPessoa;
  cpf_cnpj: string | null;
  banco: string | null;
  agencia: string | null;
  conta: string | null;
  tipo_conta: string | null;
  pix_tipo: string | null;
  pix: string | null;
  intermediario_id?: string | null;
  ativo: boolean;
}

export type FavorecidoInput = Omit<FavorecidoCompleto, "id" | "ativo"> & {
  ativo?: boolean;
};
export type FavorecidoPatchInput = Partial<FavorecidoInput>;

export type FavorecidoFiltroAtivo = "ativos" | "inativos" | "todos";

export const PIX_TIPOS = [
  { value: "cpf", label: "CPF" },
  { value: "cnpj", label: "CNPJ" },
  { value: "email", label: "E-mail" },
  { value: "telefone", label: "Telefone" },
  { value: "aleatoria", label: "Chave aleatória" },
] as const;

export const TIPOS_CONTA = [
  { value: "corrente", label: "Corrente" },
  { value: "poupanca", label: "Poupança" },
  { value: "pagamento", label: "Pagamento" },
] as const;

/**
 * The search term that may be sent to the server. The search is by NAME; a
 * term that looks like a document (4+ digits) is a CPF/CNPJ being typed and
 * must never reach a URL (access logs, history, referrers) — it returns
 * `null` and the caller shows a hint instead.
 */
export function termoDeBuscaSeguro(q: string): string | null {
  const t = q.trim();
  if (!t) return "";
  const digitos = t.replace(/\D/g, "").length;
  return digitos >= 4 ? null : t;
}

export function useFavorecidos(
  opts: { q?: string; ativo?: FavorecidoFiltroAtivo } = {},
) {
  const q = termoDeBuscaSeguro(opts.q ?? "") ?? "";
  const ativo = opts.ativo ?? "ativos";
  return useQuery({
    queryKey: [...FAVORECIDOS_KEY, "list", q, ativo] as const,
    queryFn: () => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (ativo !== "todos") {
        params.set("ativo", ativo === "ativos" ? "true" : "false");
      }
      const qs = params.toString();
      return api.get<{ items: FavorecidoResumo[] }>(
        qs ? `${FAVORECIDOS_API_BASE}?${qs}` : FAVORECIDOS_API_BASE,
      );
    },
    // Typing in the search box swaps the key: keep the previous rows on screen
    // (no skeleton flash, no unmount) until the new ones land.
    placeholderData: (prev) => prev,
  });
}

/** Clear-value record. Only enabled while an edit dialog is open on `id`. */
export function useFavorecido(id: string | null) {
  return useQuery({
    queryKey: [...FAVORECIDOS_KEY, "detail", id ?? "__none__"] as const,
    queryFn: () =>
      api.get<FavorecidoCompleto>(
        `${FAVORECIDOS_API_BASE}/${encodeURIComponent(id as string)}`,
      ),
    enabled: !!id,
    // Clear PII: never keep it around once nothing observes it.
    gcTime: 0,
  });
}

function useInvalidateRegistro() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: FAVORECIDOS_KEY });
}

export function useCreateFavorecidoRegistro() {
  const invalidate = useInvalidateRegistro();
  return useMutation({ // noc-allow: invalidate-only — the answer holds CLEAR cpf/pix, while the list keeps only MASKED rows the server builds; deriving them client-side would put PII in the cache (LGPD)
    mutationFn: (payload: FavorecidoInput) =>
      api.post<FavorecidoCompleto>(FAVORECIDOS_API_BASE, payload),
    onSuccess: invalidate,
  });
}

export function useUpdateFavorecidoRegistro() {
  return useCacheWriteMutation<FavorecidoCompleto, { id: string; patch: FavorecidoPatchInput }>({
    mutationFn: ({ id, patch }) =>
      api.patch<FavorecidoCompleto>(
        `${FAVORECIDOS_API_BASE}/${encodeURIComponent(id)}`,
        patch,
      ),
    // Only the NON-sensitive fields reach the list rows; the masked ones (cpf/pix) refetch on settle.
    targets: ({ id }) => [
      {
        queryKey: [...FAVORECIDOS_KEY, "list"],
        match: "prefix",
        commit: (old: { items: FavorecidoResumo[] } | undefined, saved) =>
          listOps.within(old, "items", (l) =>
            listOps.patch(l, id, {
              nome: saved.nome,
              tipo_pessoa: saved.tipo_pessoa,
              banco: saved.banco,
              pix_tipo: saved.pix_tipo,
              ativo: saved.ativo,
            }),
          ),
      },
    ],
    invalidate: [FAVORECIDOS_KEY],
  });
}

/** Soft delete — the row is deactivated, never removed. */
export function useDeactivateFavorecidoRegistro() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${FAVORECIDOS_API_BASE}/${encodeURIComponent(id)}`),
    targets: (id) => [
      {
        queryKey: [...FAVORECIDOS_KEY, "list"],
        match: "prefix",
        optimistic: (old: { items: FavorecidoResumo[] } | undefined) =>
          listOps.within(old, "items", (l) => listOps.patch(l, id, { ativo: false })),
      },
    ],
    invalidate: [FAVORECIDOS_KEY],
  });
}
