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

function useSeedOnSuccess(clienteId: string) {
  const qc = useQueryClient();
  return (data: NegociacaoEstruturada) => {
    qc.setQueryData(ESTRUTURADA_KEY(clienteId), data);
  };
}

function useInvalidateOnSuccess(clienteId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ESTRUTURADA_KEY(clienteId) });
  };
}

// ─── Parcelas ───────────────────────────────────────────────────────────────

export function useCreateParcela(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: (payload: ParcelaCreate) =>
      api.post<NegociacaoEstruturada>(`${base(clienteId)}/parcelas`, payload),
    onSuccess,
  });
}

export function useUpdateParcela(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: ParcelaPatch }) =>
      api.patch<NegociacaoEstruturada>(
        `${base(clienteId)}/parcelas/${id}`,
        patch,
      ),
    onSuccess,
  });
}

export function useDeleteParcela(clienteId: string) {
  const onSuccess = useInvalidateOnSuccess(clienteId);
  return useMutation({
    mutationFn: (id: string) => api.delete(`${base(clienteId)}/parcelas/${id}`),
    onSuccess,
  });
}

export function useDividirSaldo(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: (payload: DividirSaldoPayload) =>
      api.post<NegociacaoEstruturada>(
        `${base(clienteId)}/parcelas/dividir-saldo`,
        payload,
      ),
    onSuccess,
  });
}

// ─── Favorecidos ────────────────────────────────────────────────────────────

export function useCreateFavorecido(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: (payload: FavorecidoCreate) =>
      api.post<NegociacaoEstruturada>(
        `${base(clienteId)}/favorecidos`,
        payload,
      ),
    onSuccess,
  });
}

export function useUpdateFavorecido(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: FavorecidoPatch }) =>
      api.patch<NegociacaoEstruturada>(
        `${base(clienteId)}/favorecidos/${id}`,
        patch,
      ),
    onSuccess,
  });
}

export function useDeleteFavorecido(clienteId: string) {
  const onSuccess = useInvalidateOnSuccess(clienteId);
  return useMutation({
    mutationFn: (id: string) =>
      api.delete(`${base(clienteId)}/favorecidos/${id}`),
    onSuccess,
  });
}

// ─── Intermediários ─────────────────────────────────────────────────────────

export function useCreateIntermediario(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: (payload: IntermediarioCreate) =>
      api.post<NegociacaoEstruturada>(
        `${base(clienteId)}/intermediarios`,
        payload,
      ),
    onSuccess,
  });
}

export function useUpdateIntermediario(clienteId: string) {
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: IntermediarioPatch }) =>
      api.patch<NegociacaoEstruturada>(
        `${base(clienteId)}/intermediarios/${id}`,
        patch,
      ),
    onSuccess,
  });
}

export function useDeleteIntermediario(clienteId: string) {
  const onSuccess = useInvalidateOnSuccess(clienteId);
  return useMutation({
    mutationFn: (id: string) =>
      api.delete(`${base(clienteId)}/intermediarios/${id}`),
    onSuccess,
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
  return useMutation({
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
  const onSuccess = useSeedOnSuccess(clienteId);
  return useMutation({
    mutationFn: (payload: TermosNegocioPut) =>
      api.put<NegociacaoEstruturada>(`${base(clienteId)}/termos`, payload),
    onSuccess,
  });
}
