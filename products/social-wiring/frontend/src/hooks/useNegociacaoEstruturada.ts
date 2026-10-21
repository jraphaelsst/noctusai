/**
 * Negociação estruturada — TanStack Query hooks for `.../negociacao/estruturada`
 * and its sub-resources (parcelas, favorecidos, intermediários), plus the
 * posse/permuta slice of the existing `.../negociacao` PATCH.
 *
 * 🔴 EVERY WRITE THAT RETURNS THE FULL AGGREGATE IS SEEDED, NEVER INVALIDATED.
 * POST/PATCH on parcelas, favorecidos and intermediários all return the whole
 * `NegociacaoEstruturada` (same rationale as `useNegociacaoMutation` in
 * `./useNegociacao`): the numbers on screen — in particular
 * `saldo_nao_alocado`, which the server recomputes on every write — are the
 * ones the server just calculated, not a second read that could race it.
 * DELETE returns 204 with no body, so those invalidate instead.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import type {
  DividirSaldoPayload,
  FavorecidoCreate,
  FavorecidoPatch,
  IntermediarioCreate,
  IntermediarioPatch,
  NegociacaoEstruturada,
  NegociacaoPossePatch,
  ParcelaCreate,
  ParcelaPatch,
  TermosNegocioPut,
} from "@/types/negociacaoEstruturada";

// ─── Keys ───────────────────────────────────────────────────────────────────

const ESTRUTURADA_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "negociacao", "estruturada"] as const;

const base = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/negociacao`;

// ─── Queries ────────────────────────────────────────────────────────────────

export function useNegociacaoEstruturada(clienteId: string | null) {
  return useQuery({
    queryKey: ESTRUTURADA_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<NegociacaoEstruturada>(
        `${base(clienteId as string)}/estruturada`,
      ),
    enabled: !!clienteId,
  });
}

// ─── Shared write helpers ───────────────────────────────────────────────────

/** The aggregate comes back whole from every write that returns it: it IS the cache entry. */
const seedTarget = (clienteId: string) => ({
  queryKey: ESTRUTURADA_KEY(clienteId),
  commit: (_old: NegociacaoEstruturada | undefined, saved: NegociacaoEstruturada) => saved,
});

function useInvalidateOnSuccess(clienteId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ESTRUTURADA_KEY(clienteId) });
  };
}

// ─── Parcelas ───────────────────────────────────────────────────────────────

export function useCreateParcela(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, ParcelaCreate>({
    mutationFn: (payload) =>
      api.post<NegociacaoEstruturada>(`${base(clienteId)}/parcelas`, payload),
    targets: [seedTarget(clienteId)],
  });
}

export function useUpdateParcela(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, { id: string; patch: ParcelaPatch }>({
    mutationFn: ({ id, patch }) =>
      api.patch<NegociacaoEstruturada>(
        `${base(clienteId)}/parcelas/${id}`,
        patch,
      ),
    targets: [seedTarget(clienteId)],
  });
}

export function useDeleteParcela(clienteId: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${base(clienteId)}/parcelas/${id}`),
    // The aggregate's recomputed totals (saldo, a_distribuir) converge on the settle.
    targets: (id) => [
      {
        queryKey: ESTRUTURADA_KEY(clienteId),
        optimistic: (old: NegociacaoEstruturada | undefined) =>
          listOps.within(old, "parcelas", (l) => listOps.remove(l, id)),
      },
    ],
  });
}

/** Migration 195 — the FULL ordered id list; the server rewrites every
 *  `ordem` in one transaction and refuses a partial/stale list (400). */
export function useReordenarParcelas(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, string[]>({
    mutationFn: (parcelaIds) =>
      api.put<NegociacaoEstruturada>(`${base(clienteId)}/parcelas/ordem`, {
        parcela_ids: parcelaIds,
      }),
    targets: [seedTarget(clienteId)],
  });
}

export function useDividirSaldo(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, DividirSaldoPayload>({
    mutationFn: (payload) =>
      api.post<NegociacaoEstruturada>(
        `${base(clienteId)}/parcelas/dividir-saldo`,
        payload,
      ),
    targets: [seedTarget(clienteId)],
  });
}

// ─── Favorecidos ────────────────────────────────────────────────────────────

export function useCreateFavorecido(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, FavorecidoCreate>({
    mutationFn: (payload) =>
      api.post<NegociacaoEstruturada>(
        `${base(clienteId)}/favorecidos`,
        payload,
      ),
    targets: [seedTarget(clienteId)],
  });
}

export function useUpdateFavorecido(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, { id: string; patch: FavorecidoPatch }>({
    mutationFn: ({ id, patch }) =>
      api.patch<NegociacaoEstruturada>(
        `${base(clienteId)}/favorecidos/${id}`,
        patch,
      ),
    targets: [seedTarget(clienteId)],
  });
}

export function useDeleteFavorecido(clienteId: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${base(clienteId)}/favorecidos/${id}`),
    // The aggregate's recomputed totals (saldo, a_distribuir) converge on the settle.
    targets: (id) => [
      {
        queryKey: ESTRUTURADA_KEY(clienteId),
        optimistic: (old: NegociacaoEstruturada | undefined) =>
          listOps.within(old, "favorecidos", (l) => listOps.remove(l, id)),
      },
    ],
  });
}

/**
 * Pick a registry favorecido for the card (`PUT .../atendimentos/{id}/
 * favorecidos/selecao`). The response shape is not part of the contract, so
 * the aggregate is re-read (invalidate) rather than seeded.
 */
export function useSelecionarFavorecidoRegistro(clienteId: string) {
  const onSuccess = useInvalidateOnSuccess(clienteId);
  return useMutation({ // noc-allow: invalidate-only — the response shape is not part of the contract and the selection rewires which favorecidos the aggregate lists
    mutationFn: ({
      atendimentoId,
      favorecidoId,
      intermediarioId,
    }: {
      atendimentoId: string;
      favorecidoId: string;
      intermediarioId?: string | null;
    }) =>
      api.put(
        `/api/card-hub/atendimentos/${encodeURIComponent(atendimentoId)}/favorecidos/selecao`,
        {
          favorecido_id: favorecidoId,
          ...(intermediarioId ? { intermediario_id: intermediarioId } : {}),
        },
      ),
    onSuccess,
  });
}

// ─── Intermediários ─────────────────────────────────────────────────────────

export function useCreateIntermediario(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, IntermediarioCreate>({
    mutationFn: (payload) =>
      api.post<NegociacaoEstruturada>(
        `${base(clienteId)}/intermediarios`,
        payload,
      ),
    targets: [seedTarget(clienteId)],
  });
}

export function useUpdateIntermediario(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, { id: string; patch: IntermediarioPatch }>({
    mutationFn: ({ id, patch }) =>
      api.patch<NegociacaoEstruturada>(
        `${base(clienteId)}/intermediarios/${id}`,
        patch,
      ),
    targets: [seedTarget(clienteId)],
  });
}

export function useDeleteIntermediario(clienteId: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${base(clienteId)}/intermediarios/${id}`),
    // The aggregate's recomputed totals (saldo, a_distribuir) converge on the settle.
    targets: (id) => [
      {
        queryKey: ESTRUTURADA_KEY(clienteId),
        optimistic: (old: NegociacaoEstruturada | undefined) =>
          listOps.within(old, "intermediarios", (l) => listOps.remove(l, id)),
      },
    ],
  });
}

// ─── Posse / permuta ────────────────────────────────────────────────────────

/**
 * PATCHes the EXISTING `.../negociacao` endpoint (the one
 * `useNegociacaoMutation` in `./useNegociacao` also writes to) — this contract
 * only adds three fields to it, it is not a new route. That endpoint returns
 * the `Negociacao` row, not the `/estruturada` aggregate, so the response
 * cannot be seeded here; invalidate `/estruturada` instead to pick up the
 * fresh `posse_data` / `posse_condicoes` / `permuta_ativo_id`.
 */
export function useNegociacaoPosseMutation(clienteId: string) {
  const onSuccess = useInvalidateOnSuccess(clienteId);
  return useMutation({ // noc-allow: invalidate-only — the PATCH answers the Negociacao row, not the /estruturada aggregate this cache holds
    mutationFn: (patch: NegociacaoPossePatch) =>
      api.patch(base(clienteId), patch),
    onSuccess,
  });
}

// ─── Termos do negócio (114) ────────────────────────────────────────────────

/**
 * PUT `.../negociacao/termos` — replaces the deal's contract clauses as a
 * WHOLE (an absent key is stored as null). Returns the full aggregate, same
 * seed-not-invalidate rationale as every other write here.
 */
export function useAtualizarTermos(clienteId: string) {
  return useCacheWriteMutation<NegociacaoEstruturada, TermosNegocioPut>({
    mutationFn: (payload) =>
      api.put<NegociacaoEstruturada>(`${base(clienteId)}/termos`, payload),
    targets: [seedTarget(clienteId)],
  });
}
