/**
 * The CRM hooks, built ONCE at module scope from the seed organs (the organs take the api client; the product
 * writes no query code). Every page imports from here, so Funil, Lista, Conversas and the lead modal share one
 * query cache per resource.
 */
import { createClientsHooks, createLeadsHooks, createWhatsAppConnectionsHooks, createWhatsAppInboxHooks, leadsKeys } from "@noctusai/lib";
import { createOrgSpecsHooks } from "@noctusai/lib/components";

import { api, getAuthToken } from "@/lib/api";

/** The agent definition whose org specs the Contexto page edits (Mônica's future lead agent; not activated). */
export const CONTEXTO_AGENT_KEY = "monica-leads";

export const leadsHooks = createLeadsHooks(api);
/** Pacientes (the seed clients organ over `/api/clients`; the noun "Paciente" is the backend config). */
export const clientsHooks = createClientsHooks(api);
/** A purge deletes / detaches leads: the board and the list refresh with it. */
export const connectionsHooks = createWhatsAppConnectionsHooks(api, { purgeInvalidates: [leadsKeys.all] });
export const inboxHooks = createWhatsAppInboxHooks(api, { getAuthToken });
/** `/api/contexto` is monica's own proxy to the agents org specs (it forwards the user's bearer). */
export const contextoHooks = createOrgSpecsHooks(api, { path: () => "/api/contexto" });

export const CONVERSAS_PATH = "/conversas";
export const CONEXOES_PATH = "/configuracoes/conexoes";

/** Deep link to one conversation (the inbox opens `?chat=`). */
export function conversationPath(chatId: string): string {
  return `${CONVERSAS_PATH}?chat=${encodeURIComponent(chatId)}`;
}

export const PACIENTES_PATH = "/pacientes";

/** One patient's page. */
export function patientPath(clientId: string): string {
  return `${PACIENTES_PATH}/${encodeURIComponent(clientId)}`;
}

/** The patient converted from a lead (the list resolves `?lead=` and redirects). */
export function patientOfLeadPath(leadId: string): string {
  return `${PACIENTES_PATH}?lead=${encodeURIComponent(leadId)}`;
}
