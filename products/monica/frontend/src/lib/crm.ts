/**
 * The CRM hooks, built ONCE at module scope from the seed organs (the organs take the api client; the product
 * writes no query code). Every page imports from here, so Funil, Lista, Conversas and the lead modal share one
 * query cache per resource.
 */
import { createLeadsHooks, createWhatsAppConnectionsHooks, createWhatsAppInboxHooks } from "@noctusai/lib";
import { createOrgSpecsHooks } from "@noctusai/lib/components";

import { api, getAuthToken } from "@/lib/api";

/** The agent definition whose org specs the Contexto page edits (Mônica's future lead agent; not activated). */
export const CONTEXTO_AGENT_KEY = "monica-leads";

export const leadsHooks = createLeadsHooks(api);
export const connectionsHooks = createWhatsAppConnectionsHooks(api);
export const inboxHooks = createWhatsAppInboxHooks(api, { getAuthToken });
/** `/api/contexto` is monica's own proxy to the agents org specs (it forwards the user's bearer). */
export const contextoHooks = createOrgSpecsHooks(api, { path: () => "/api/contexto" });

export const CONVERSAS_PATH = "/conversas";
export const CONEXOES_PATH = "/configuracoes/conexoes";

/** Deep link to one conversation (the inbox opens `?chat=`). */
export function conversationPath(chatId: string): string {
  return `${CONVERSAS_PATH}?chat=${encodeURIComponent(chatId)}`;
}
