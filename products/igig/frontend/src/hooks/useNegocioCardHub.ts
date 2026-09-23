/**
 * The negócio funnel card's data layer — the seed card hub
 * (`createCardHubHooks`, `@noctusai/lib/components`) mounted on
 * `/api/comercial/negocios` (backend: `app/card_hub.py`,
 * `CARD_HUB_NEGOCIO`). Nothing here is igig-specific except the base path,
 * the query-key root and the member source (`profissional` ⇒ body key
 * `profissional_ids`).
 */
import { createCardHubHooks } from "@noctusai/lib/components";

import { api } from "@/lib/api";

export const negocioCardHub = createCardHubHooks(
  {
    rootKey: ["igig", "negocio-card"],
    basePath: "/api/comercial/negocios",
    entityLabel: "negócio",
  },
  api,
);
