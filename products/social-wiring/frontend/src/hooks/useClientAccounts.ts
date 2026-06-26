/**
 * useClientAccounts — convenience aggregation hook for the ClienteModal.
 *
 * Combines all connection types scoped to a single cliente:
 *   · Integration accounts (all providers) via GET /api/integrations/accounts?client_id=
 *   · WhatsApp connections           via GET /api/whatsapp/connections?client_id=
 *
 * Returns unified isLoading / isError flags so the caller can render a single
 * loading / error state without tracking two separate queries.
 *
 * The hook is disabled when clientId is null; callers can pass null safely.
 */
import {
  useIntegrationAccounts,
  type IntegrationAccount,
} from "@/hooks/useIntegrationAccounts";
import {
  useClientWhatsAppConnections,
  type WhatsAppConnectionLine,
} from "@/hooks/useWhatsAppConnections";

export interface ClientAccounts {
  integrationAccounts: IntegrationAccount[];
  waConnections: WhatsAppConnectionLine[];
  /** true while EITHER query is in-flight */
  isLoading: boolean;
  /** true when EITHER query failed */
  isError: boolean;
}

export function useClientAccounts(clientId: string | null): ClientAccounts {
  const integrations = useIntegrationAccounts({ clientId: clientId ?? undefined });
  const waConnections = useClientWhatsAppConnections(clientId);

  return {
    integrationAccounts: integrations.data ?? [],
    waConnections: waConnections.data ?? [],
    isLoading: integrations.isLoading || waConnections.isLoading,
    isError: integrations.isError || waConnections.isError,
  };
}
