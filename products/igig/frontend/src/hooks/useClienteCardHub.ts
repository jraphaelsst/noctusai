/**
 * The cliente card's data layer — the seed card hub (`createCardHubHooks`,
 * `@noctusai/lib/components`) mounted on `/api/clientes` (backend:
 * `app/card_hub.py`, `CARD_HUB_CLIENTE`). Twin of `useNegocioCardHub.ts`:
 * the same organ, a different base path (roadmap R9 — "o card do cliente É o
 * card do funil").
 */
import { createCardHubHooks } from "@noctusai/lib/components";

import { api } from "@/lib/api";

export const clienteCardHub = createCardHubHooks(
  {
    rootKey: ["igig", "cliente-card"],
    basePath: "/api/clientes",
    entityLabel: "cliente",
  },
  api,
);
