/**
 * Julia › the org's ONE WhatsApp line (QR / status / reconnect), via the seed connections hooks over the product
 * `/api/whatsapp/connections` router. The pairing UI itself is the seed `ConnectionPairingPanel` organ; this file only
 * binds it to the product's api client. The line's identity (`connection_id`) comes from the routing read
 * (`useJuliaRoteamento`), so there is exactly one source of "which line is Julia's".
 */
import { createWhatsAppConnectionsHooks } from "@noctusai/lib/components";
import type { ApiClient } from "@noctusai/lib";

import { api } from "@/lib/api";

export const juliaLinhaHooks = createWhatsAppConnectionsHooks(api as unknown as ApiClient);
