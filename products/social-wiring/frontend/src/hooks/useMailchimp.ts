/**
 * Mailchimp per-cliente connection hooks — TanStack Query wrappers for the
 * manual API-key Mailchimp integration scoped to one cliente.
 *
 * Mirrors the conventions in useIntegrationAccounts.ts / useWhatsAppConnections.ts:
 *   · const KEY per query key (["sw", "mailchimp", ...] namespace)
 *   · api.get / api.put from @noctusai/seed/infra
 *   · the mutation invalidates the connection query on success
 *   · queryFns never return undefined (TanStack v5 contract) — the BE always
 *     returns the connection shape (nulls when not connected), so no ?? guard
 *     is needed, but we keep the enabled-guard on clientId.
 *
 * API contract (BE builds the same):
 *   GET /api/mailchimp/connection?client_id=<uuid>
 *     → { connected, client_id, server_prefix, audience_id, audience_name,
 *         created_at, updated_at }  (always 200; nulls when not connected)
 *   PUT /api/mailchimp/connection
 *     body { api_key, server_prefix?, audience_id?, client_id }
 *     → upserts the cliente's connection; returns the same shape.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types (mirror the BE contract) ─────────────────────────────────────────

export interface MailchimpConnection {
  connected: boolean;
  client_id: string;
  server_prefix: string | null;
  audience_id: string | null;
  audience_name: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface UpsertMailchimpConnectionInput {
  api_key: string;
  server_prefix?: string;
  audience_id?: string;
  client_id: string;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const CONNECTION_KEY = (clientId: string | null) =>
  ["sw", "mailchimp", "connection", clientId] as const;

// ─── Connection query ────────────────────────────────────────────────────────

/**
 * Fetch the Mailchimp connection for a specific cliente.
 * Maps to GET /api/mailchimp/connection?client_id=<id>. Enabled only when a
 * clientId is provided. Returns { connected: false, ... } when not connected.
 */
export function useMailchimpConnection(clientId: string | null) {
  return useQuery<MailchimpConnection>({
    queryKey: CONNECTION_KEY(clientId),
    queryFn: () =>
      api.get<MailchimpConnection>(
        `/api/mailchimp/connection?client_id=${encodeURIComponent(clientId!)}`,
      ),
    enabled: !!clientId,
  });
}

// ─── Upsert mutation ─────────────────────────────────────────────────────────

/**
 * Upsert (connect / re-key) the cliente's Mailchimp connection.
 * Maps to PUT /api/mailchimp/connection. Invalidates the connection query for
 * that cliente on success so the grid reflects the new connected state.
 */
export function useUpsertMailchimpConnection() {
  const qc = useQueryClient();
  return useMutation<MailchimpConnection, unknown, UpsertMailchimpConnectionInput>({
    mutationFn: (payload) =>
      api.put<MailchimpConnection>("/api/mailchimp/connection", payload),
    onSuccess: (res, variables) => {
      const clientId = (res as MailchimpConnection)?.client_id ?? variables.client_id;
      qc.invalidateQueries({ queryKey: CONNECTION_KEY(clientId) });
    },
  });
}
