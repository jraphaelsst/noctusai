/**
 * Binds the seed `createWhatsAppConnectionHooks` factory to this
 * product's authenticated API client. Same one-liner pattern the other
 * hooks use for seed factories — the WhatsApp connection UX lives in the
 * seed; the product only supplies its `api`.
 */
import { api } from "@noctusai/seed/infra";
import { createWhatsAppConnectionHooks } from "@noctusai/lib";

const hooks = createWhatsAppConnectionHooks(api);

export const useWhatsAppConnection = hooks.useWhatsAppConnection;
export const useWhatsAppQr = hooks.useWhatsAppQr;
export const useWhatsAppActions = hooks.useWhatsAppActions;

export type {
  WhatsAppConnection,
  WhatsAppQr,
  WhatsAppWebhookResult,
} from "@noctusai/lib";
