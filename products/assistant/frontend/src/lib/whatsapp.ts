/** Data layer of the pairing page + the conversations page: the seed hooks over `/api/whatsapp/connections*` (admin-only on the server). */
import { createWhatsAppConnectionsHooks, createWhatsAppInboxHooks } from "@noctusai/lib";

import { api, getAuthToken } from "@/lib/api";

export const connectionsHooks = createWhatsAppConnectionsHooks(api);

/** The conversations inbox (`/conversas`): built ONCE at module scope, the organ takes the bag as its `hooks` prop. */
export const inboxHooks = createWhatsAppInboxHooks(api, { getAuthToken });
