/**
 * useImovelRelacionamentos — the imóvel page's two relationship cards:
 * "Interessados" (CONTRACT §4.3) and "Imóveis similares" (§4.4).
 *
 * `placeholderData: keepPreviousData` is safe here: the key's only moving part
 * is the page/limit of the SAME imóvel (and the código never changes under a
 * mounted page), so the previous page's rows are the same imóvel's data — never
 * another record's.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type {
  InteressadoRow,
  ItemsTotal,
  ProprietarioDoImovel,
  SimilaresResponse,
} from "@/types/interesses";

const base = (codigo: string) => `/api/imoveis/${encodeURIComponent(codigo)}`;
const KEY = ["sw", "imovel-relacionamentos"] as const;

export function useImovelInteressados(
  codigo: string | undefined,
  opts: { limit?: number; offset?: number; enabled?: boolean } = {},
) {
  const { limit = 20, offset = 0, enabled = true } = opts;
  return useQuery({
    queryKey: [...KEY, codigo ?? "__none__", "interessados", limit, offset],
    queryFn: () =>
      api.get<ItemsTotal<InteressadoRow>>(
        `${base(codigo as string)}/interessados?limit=${limit}&offset=${offset}`,
      ),
    enabled: !!codigo && enabled,
    placeholderData: keepPreviousData,
  });
}

export function useImovelSimilares(codigo: string | undefined, limit = 10) {
  return useQuery({
    queryKey: [...KEY, codigo ?? "__none__", "similares", limit],
    queryFn: () =>
      api.get<SimilaresResponse>(`${base(codigo as string)}/similares?limit=${limit}`),
    enabled: !!codigo,
    placeholderData: keepPreviousData,
  });
}

/** `GET /api/imoveis/{codigo}/proprietarios` (CONTRACT §4.2) — who owns this imóvel. */
export function useImovelProprietarios(codigo: string | undefined) {
  return useQuery({
    queryKey: [...KEY, codigo ?? "__none__", "proprietarios"],
    queryFn: () =>
      api.get<ItemsTotal<ProprietarioDoImovel>>(`${base(codigo as string)}/proprietarios`),
    enabled: !!codigo,
  });
}
