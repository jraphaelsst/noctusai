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
