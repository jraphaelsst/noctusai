/**
 * Interessados data hooks — `projects/interessados-CONTRACT.md`.
 *
 * The public `POST /api/public/interessados` write lives in `@/lib/api`
 * (`createInteressado` — used only by `InterestPopup`, not a list/detail
 * hook consumer). This file is the internal, authenticated admin side:
 * `GET /api/interessados` (list, paginated) and `DELETE /api/interessados/
 * {id}`, matching this product's own `useDecisoes.ts` / `useKb.ts`
 * convention (inline `api.get`/`api.delete` calls, typed at the call site).
 */
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";
import type { Envelope } from "@/lib/types";

export interface Interessado {
  id: string;
  nome: string;
  whatsapp: string;
  email: string;
  origem: string | null;
  consentimento_versao: string;
  consentimento_em: string;
  criado_em: string;
}

const interessadosKeys = {
  all: ["interessados"] as const,
  list: (limit: number, offset: number) => ["interessados", "list", limit, offset] as const,
};

export function useInteressadosList(limit = 50, offset = 0) {
  return useQuery({
    queryKey: interessadosKeys.list(limit, offset),
    queryFn: () => api.get<Envelope<Interessado>>("/api/interessados", { limit, offset }),
    placeholderData: keepPreviousData,
  });
}

export function useDeleteInteressado() {
  // The row leaves every cached page on the click and the total follows; a failure
  // puts it back.
  return useCacheWriteMutation<void, string>({
    mutationFn: (id) => api.delete<void>(`/api/interessados/${id}`),
    targets: [
      {
        queryKey: interessadosKeys.all,
        match: "prefix",
        optimistic: (old: Envelope<Interessado> | undefined, id) => pageOps.remove(old, id),
      },
    ],
  });
}
