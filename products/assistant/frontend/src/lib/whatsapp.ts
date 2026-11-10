/** Data layer of the pairing page: the seed connections hooks over `/api/whatsapp/connections*` (admin-only on the server). */
import { createWhatsAppConnectionsHooks } from "@noctusai/lib";

import { api } from "@/lib/api";

export const connectionsHooks = createWhatsAppConnectionsHooks(api);
