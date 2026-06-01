/**
 * Integration accounts hooks — TanStack Query wrappers for the
 * multi-account credential system. Mirrors useTeam.ts conventions:
 *   · const KEY per query key
 *   · api.get / api.post / api.patch / api.delete from @noctusai/seed/infra
 *   · mutations invalidate their relevant keys on success
 *
 * Providers: YouTube, Meta, n8n, Google Drive, Gmail (WAHA excluded — handled
 * by Conexao page / useWhatsAppConnections).
 *
 * API contract: all endpoints return bare arrays/objects (NO envelope).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface ManualKeyField {
  /** BE uses `name` (not `key`) */
  name: string;
  label: string;
  placeholder: string;
  type: "text" | "password" | "url";
}

export interface IntegrationProvider {
  /** BE uses `id` (not `name`) */
  id: string;
  display_name: string;
  icon: string | null;
  oauth_supported: boolean;
  manual_entry: boolean;
  manual_key_fields: ManualKeyField[];
  scopes: string[];
  tutorial_url: string | null;
}

export type IntegrationStatus =
  | "wiring"
  | "validating"
  | "validated"
  | "error"
  | "disconnected";

export interface IntegrationAccount {
  id: string;
  org_id: string;
  provider: string;
  account_label: string;
  /** Which client this account belongs to; null = unassigned. */
  client_id: string | null;
  /** Current account status. */
  status: IntegrationStatus;
  /**
   * Provider-specific channel/session data from the last sync.
   * YouTube: { channel_id, title, thumbnail_url, subscriber_count, video_count, view_count }
   * WhatsApp: { session, phone, webhook_url }
   */
  channel_info: Record<string, unknown>;
  metadata: Record<string, unknown>;
  is_default: boolean;
  /** ISO timestamp of the last successful sync; null if never synced. */
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAccountInput {
  provider: string;
  account_label: string;
  credential: Record<string, string>;
  metadata?: Record<string, unknown>;
  is_default?: boolean;
  /** Assign to a client on creation. */
  client_id?: string | null;
}

export interface UpdateAccountInput {
  account_label?: string;
  metadata?: Record<string, unknown>;
  is_default?: boolean;
  /** Reassign to a different client (null = unassign). */
  client_id?: string | null;
}

export interface OAuthStartResponse {
  auth_url: string;
  state: string;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const PROVIDERS_KEY = ["sw", "integrations", "providers"] as const;
const ACCOUNTS_KEY = (provider?: string, clientId?: string | null) => {
  if (provider && clientId !== undefined && clientId !== null) {
    return ["sw", "integrations", "accounts", provider, "client", clientId] as const;
  }
  if (provider) {
    return ["sw", "integrations", "accounts", provider] as const;
  }
  return ["sw", "integrations", "accounts"] as const;
};
const ACCOUNT_KEY = (id: string) => ["sw", "integrations", "accounts", "detail", id] as const;

// ─── Provider registry ───────────────────────────────────────────────────────

export function useIntegrationProviders() {
  return useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: async () => {
      const res = await api.get<IntegrationProvider[]>("/api/integrations/providers");
      return res ?? [];
    },
    staleTime: 5 * 60 * 1000, // provider list changes rarely
  });
}

// ─── Account list ────────────────────────────────────────────────────────────

export interface UseIntegrationAccountsOptions {
  provider?: string;
  /** Filter by client; pass null to fetch unassigned accounts. */
  clientId?: string | null;
}

export function useIntegrationAccounts(
  providerOrOptions?: string | UseIntegrationAccountsOptions,
) {
  const { provider, clientId } =
    typeof providerOrOptions === "string"
      ? { provider: providerOrOptions, clientId: undefined }
      : (providerOrOptions ?? {});

  return useQuery({
    queryKey: ACCOUNTS_KEY(provider, clientId),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (provider) params.set("provider", provider);
      if (clientId !== undefined && clientId !== null) {
        params.set("client_id", clientId);
      }
      const qs = params.toString();
      const url = qs ? `/api/integrations/accounts?${qs}` : "/api/integrations/accounts";
      const res = await api.get<IntegrationAccount[]>(url);
      return res ?? [];
    },
  });
}

// ─── Single account ──────────────────────────────────────────────────────────

export function useIntegrationAccount(id: string) {
  return useQuery({
    queryKey: ACCOUNT_KEY(id),
    queryFn: async () => {
      const res = await api.get<IntegrationAccount>(`/api/integrations/accounts/${id}`);
      return res;
    },
    enabled: !!id,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAccountInput) =>
      api.post<IntegrationAccount>("/api/integrations/accounts", payload),
    onSuccess: (res, variables) => {
      // res is a bare account; fall back to variables.provider
      const provider = (res as any)?.provider ?? variables.provider;
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      if (provider) qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(provider) });
    },
  });
}

export function useUpdateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateAccountInput & { id: string }) =>
      api.patch<IntegrationAccount>(`/api/integrations/accounts/${id}`, payload),
    onSuccess: (res) => {
      const provider = (res as any)?.provider;
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      if (provider) qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(provider) });
    },
  });
}

export function useSetDefaultAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.patch<IntegrationAccount>(`/api/integrations/accounts/${id}/set-default`, {}),
    onSuccess: (res) => {
      const provider = (res as any)?.provider;
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      if (provider) qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(provider) });
    },
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/integrations/accounts/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
    },
  });
}

// ─── Sync account ────────────────────────────────────────────────────────────

/**
 * useSyncAccount — triggers POST /api/integrations/accounts/{id}/sync which
 * refreshes channel_info + status on the backend and returns the updated account.
 * Invalidates the full accounts query key so all listing hooks re-fetch.
 */
export function useSyncAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<IntegrationAccount>(`/api/integrations/accounts/${id}/sync`, {}),
    onSuccess: (res) => {
      const provider = (res as any)?.provider;
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      if (provider) qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(provider) });
      if ((res as any)?.id) {
        qc.invalidateQueries({ queryKey: ACCOUNT_KEY((res as any).id) });
      }
    },
  });
}

// ─── Legacy adoption ─────────────────────────────────────────────────────────

/**
 * useAdoptLegacy — promotes a pre-existing single-account connection into a
 * first-class default integration account. Idempotent; returns null when
 * there's nothing to adopt.
 */
export function useAdoptLegacy(provider: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<IntegrationAccount | null>(
        `/api/integrations/accounts/${provider}/adopt-legacy`,
        {}
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(provider) });
    },
  });
}

// ─── YouTube OAuth ───────────────────────────────────────────────────────────

export interface YouTubeOAuthStartOptions {
  /** Assign the new account to this client after OAuth completes. */
  clientId?: string | null;
}

export function useStartYouTubeOAuth() {
  return useMutation({
    mutationFn: async (options?: YouTubeOAuthStartOptions) => {
      const body: Record<string, unknown> = {};
      if (options?.clientId) body.client_id = options.clientId;
      const res = await api.post<OAuthStartResponse>(
        "/api/integrations/accounts/youtube/oauth/start",
        body
      );
      return res;
    },
    onSuccess: (res) => {
      if (res?.auth_url) {
        window.location.assign(res.auth_url);
      }
    },
  });
}
