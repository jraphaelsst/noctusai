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
import { useQuery } from "@tanstack/react-query";
import { addTo, patchById, removeById, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api, cleanParams, unwrapData } from "@/lib/api";
import type { ProdutoServico, ProdutoServicoInput, ProdutoServicoRemovido, Secao } from "@/types/crm";

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
  type Atualizar = { id: string; payload: Partial<ProdutoServicoInput> };
  const criar = useCacheWriteMutation<ProdutoServico, ProdutoServicoInput>({
    mutationFn: (payload) =>
      api.post("/api/produtos-servicos", payload).then(unwrapData<ProdutoServico>),
    // Into the unfiltered list and the list of its own section; other filters settle.
    targets: (v) => [
      addTo<ProdutoServico, ProdutoServicoInput>([...PRODUTOS_QUERY_KEY, "", ""]),
      addTo<ProdutoServico, ProdutoServicoInput>([...PRODUTOS_QUERY_KEY, v.secao, ""]),
    ],
    invalidate: [PRODUTOS_QUERY_KEY],
  });
  const atualizar = useCacheWriteMutation<ProdutoServico, Atualizar>({
    mutationFn: ({ id, payload }) =>
      api.patch(`/api/produtos-servicos/${encodeURIComponent(id)}`, payload).then(unwrapData<ProdutoServico>),
    targets: [patchById<ProdutoServico, Atualizar>(PRODUTOS_QUERY_KEY, (v) => v.id, (v) => v.payload)],
  });
  /** `{id, removido, desativado}` — NOT a `ProdutoServico` (achado 3: the
   * caller used to check `r.ativo === false`, a field the response never
   * carries, so the "foi desativado em vez de excluído" toast never showed). */
  const remover = useCacheWriteMutation<ProdutoServicoRemovido, string>({
    mutationFn: (id) =>
      api.delete(`/api/produtos-servicos/${encodeURIComponent(id)}`).then(unwrapData<ProdutoServicoRemovido>),
    // Gone from the catalog on the click. A referenced product is only deactivated
    // server-side — then the settle brings it back as inativo.
    targets: [removeById<ProdutoServicoRemovido, string>(PRODUTOS_QUERY_KEY, (id) => id)],
  });
  return { criar, atualizar, remover };
}
