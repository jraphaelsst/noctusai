/**
 * Produtos e Serviços — the orçamento catalog (wave-2 contract, Slice A).
 *
 *   GET    /api/produtos-servicos?secao=&ativo=
 *   POST   /api/produtos-servicos
 *   PATCH  /api/produtos-servicos/{id}
 *   DELETE /api/produtos-servicos/{id}   (referenced ⇒ soft `ativo=false`, 200)
 *
 * Loading = two signals (`KB § PATTERNS/frontend/lying-loading-state.md`),
 * computed HERE so no consumer re-derives them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, cleanParams, unwrapData } from "@/lib/api";
import type { ProdutoServico, ProdutoServicoInput, Secao } from "@/types/crm";

export const PRODUTOS_QUERY_KEY = ["igig", "produtos-servicos"] as const;

export function useProdutosServicos(filtros: { secao?: Secao; ativo?: boolean } = {}) {
  const query = useQuery({
    queryKey: [...PRODUTOS_QUERY_KEY, filtros.secao ?? "", filtros.ativo ?? ""],
    queryFn: () =>
      api.get(
        "/api/produtos-servicos",
        cleanParams({ secao: filtros.secao, ativo: filtros.ativo }),
      ).then(unwrapData<ProdutoServico[]>),
    // Filters ride in the key — keep the previous list while the next loads.
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  return {
    ...query,
    produtos: data ?? [],
    showSkeleton: query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}

export function useProdutoServicoMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: PRODUTOS_QUERY_KEY });

  const criar = useMutation({
    mutationFn: (payload: ProdutoServicoInput) =>
      api.post("/api/produtos-servicos", payload).then(unwrapData<ProdutoServico>),
    onSuccess: invalidate,
  });
  const atualizar = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<ProdutoServicoInput> }) =>
      api.patch(`/api/produtos-servicos/${encodeURIComponent(id)}`, payload).then(unwrapData<ProdutoServico>),
    onSuccess: invalidate,
  });
  /** Resolves with the row when the server soft-deleted (referenced ⇒ ativo=false). */
  const remover = useMutation({
    mutationFn: (id: string) =>
      api.delete(`/api/produtos-servicos/${encodeURIComponent(id)}`).then(unwrapData<ProdutoServico | null>),
    onSuccess: invalidate,
  });
  return { criar, atualizar, remover };
}
