/**
 * The org's managed Asaas keys — the seed `createApiKeysHooks` over this
 * product's `/api/settings/api-keys` router (`app/routers/api_keys_router.py`).
 */
import { createApiKeysHooks } from "@noctusai/lib/components";

import { api } from "@/lib/api";

export const commerceApiKeys = createApiKeysHooks(api);
