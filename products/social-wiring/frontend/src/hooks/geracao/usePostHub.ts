/**
 * The seed card hub bound to an Esteira post (esteira-contract.md §2.4 / §6.2, FE-2):
 * notes, tags, members, reminders, checklists, documents and the timeline over
 * `/api/media-creation/esteira/posts/{id}/…`. Same factory as SW's lead card
 * (`useCardHub.ts`); only the descriptor differs, nothing is re-implemented.
 *
 * The root key nests under `ESTEIRA_KEY`, so every post mutation in `useEsteira`
 * (which invalidates that family) also refreshes the hub reads.
 */
import { createCardHubHooks, flattenTimeline } from "@noctusai/lib/components";
import type { CardHubApi, CardResumoBase } from "@noctusai/lib/components";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { ESTEIRA_KEY } from "@/lib/esteiraKeys";
import { uploadMultipart } from "@/hooks/useCardHub";
import { ESTEIRA_BASE } from "./useEsteira";

const hubApi: CardHubApi = {
  get: (...args: Parameters<CardHubApi["get"]>) => api.get(...args),
  post: (...args: Parameters<CardHubApi["post"]>) => api.post(...args),
  patch: (...args: Parameters<CardHubApi["patch"]>) => api.patch(...args),
  put: (...args: Parameters<CardHubApi["put"]>) => api.put(...args),
  delete: (...args: Parameters<CardHubApi["delete"]>) => api.delete(...args),
  upload: uploadMultipart,
};

export const postHub = createCardHubHooks<CardResumoBase>(
  {
    rootKey: [...ESTEIRA_KEY, "hub"],
    basePath: `${ESTEIRA_BASE}/posts`,
    entityLabel: "post",
  },
  hubApi,
);

export { flattenTimeline };

/**
 * The card hub's "Datas" for a post (`data_entrega` = "Postagem prevista",
 * `entrega_concluida`) go through the hub's `/card` route (contract §5.1 #5).
 * NOC-REMEDIATE[esteira-datas-route]: the seed router documents only `GET /card`;
 * confirm BE-1 mounts `PATCH /posts/{id}/card` for the Datas — 2026-10-10.
 */
export function useDatasPost(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { data_entrega?: string | null; entrega_concluida?: boolean }) =>
      api.patch(`${ESTEIRA_BASE}/posts/${encodeURIComponent(id)}/card`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ESTEIRA_KEY }),
  });
}
