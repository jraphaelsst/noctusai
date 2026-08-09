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
  marca_id: string | null;
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
  marca_id?: string | null;
}

export interface UpdateAccountInput {
  account_label?: string;
  metadata?: Record<string, unknown>;
  is_default?: boolean;
  /** Reassign to a different client (null = unassign). */
  marca_id?: string | null;
}

export interface OAuthStartResponse {
  auth_url: string;
  state: string;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const PROVIDERS_KEY = ["sw", "integrations", "providers"] as const;
const ACCOUNTS_KEY = (provider?: string, marcaId?: string | null) => {
  if (provider && marcaId !== undefined && marcaId !== null) {
    return ["sw", "integrations", "accounts", provider, "client", marcaId] as const;
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
  marcaId?: string | null;
}

export function useIntegrationAccounts(
  providerOrOptions?: string | UseIntegrationAccountsOptions,
) {
  const { provider, marcaId } =
    typeof providerOrOptions === "string"
      ? { provider: providerOrOptions, marcaId: undefined }
      : (providerOrOptions ?? {});

  return useQuery({
    queryKey: ACCOUNTS_KEY(provider, marcaId),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (provider) params.set("provider", provider);
      if (marcaId !== undefined && marcaId !== null) {
        params.set("marca_id", marcaId);
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

// ─── OAuth new-tab helper ─────────────────────────────────────────────────────

/**
 * openOAuthTab — opens a blank tab SYNCHRONOUSLY (before any await) so the
 * browser's popup blocker still attributes it to the user gesture that
 * triggered the mutation, and returns a setter that points that tab at the
 * auth URL once it's known (or falls back to a same-tab redirect if the
 * blocker won the race and `window.open` returned null).
 *
 * Usage:
 *   const openTab = openOAuthTab();
 *   ... await the network call ...
 *   openTab(res.auth_url);
 */
function openOAuthTab() {
  // NB: do NOT pass "noopener" here — per the HTML spec `window.open(...,
  // "noopener")` returns `null`, which would strand this blank tab AND trip the
  // fallback below into redirecting the CURRENT page (the exact bug reported).
  // We need the window handle to point the NEW tab at the auth URL, so we open
  // WITHOUT noopener and instead sever the opener link ourselves for anti-
  // reverse-tabnabbing (we never use `tab.opener`).
  const tab =
    typeof window !== "undefined" ? window.open("", "_blank") : null;
  if (tab) {
    try {
      tab.opener = null;
    } catch {
      /* some browsers freeze `opener` — best-effort, non-fatal */
    }
  }
  return (authUrl: string) => {
    if (tab) {
      // Navigate ONLY the new tab; the current page stays put.
      tab.location.href = authUrl;
    } else {
      // Popup blocked (no window handle) — fall back to same-tab redirect so
      // the OAuth flow never silently dies.
      window.location.assign(authUrl);
    }
  };
}

// ─── YouTube OAuth ───────────────────────────────────────────────────────────

export interface YouTubeOAuthStartOptions {
  /** Assign the new account to this client after OAuth completes. */
  marcaId?: string | null;
}

export function useStartYouTubeOAuth() {
  return useMutation({
    mutationFn: async (options?: YouTubeOAuthStartOptions) => {
      const openTab = openOAuthTab();
      const body: Record<string, unknown> = {};
      if (options?.marcaId) body.marca_id = options.marcaId;
      const res = await api.post<OAuthStartResponse>(
        "/api/integrations/accounts/youtube/oauth/start",
        body
      );
      if (res?.auth_url) {
        openTab(res.auth_url);
      }
      return res;
    },
  });
}

// ─── Generic OAuth start (Gmail, Google Drive, …) ────────────────────────────

export interface ProviderOAuthStartOptions {
  /** Assign the new account to this client after OAuth completes. */
  marcaId?: string | null;
}

/**
 * useStartProviderOAuth — generic OAuth-start hook.
 *
 * POSTs to `/api/integrations/accounts/{provider}/oauth/start` with an
 * optional `client_id` body field, then opens the returned `auth_url` in a
 * new tab (see `openOAuthTab`), keeping this app open in the current tab.
 * Mirror of `useStartYouTubeOAuth`.
 *
 * Usage:
 *   const oauthStart = useStartProviderOAuth("gmail");
 *   oauthStart.mutate({ clientId: client.id });
 */
export function useStartProviderOAuth(provider: string) {
  return useMutation({
    mutationFn: async (options?: ProviderOAuthStartOptions) => {
      const openTab = openOAuthTab();
      const body: Record<string, unknown> = {};
      if (options?.marcaId) body.marca_id = options.marcaId;
      const res = await api.post<OAuthStartResponse>(
        `/api/integrations/accounts/${provider}/oauth/start`,
        body,
      );
      if (res?.auth_url) {
        openTab(res.auth_url);
      }
      return res;
    },
  });
}

// ─── Instagram manual token-paste fallback ───────────────────────────────────

export interface SubmitInstagramTokenInput {
  /** Instagram User access token (NOT the app "Token de Cliente"). */
  access_token: string;
  /** Assign the new account to this client. */
  marca_id?: string | null;
}

/**
 * useSubmitInstagramToken — manual fallback for the Instagram Business Login
 * OAuth flow. POSTs a pasted user access token to the backend, which
 * validates it and creates/returns the account (400 on an invalid token).
 * Invalidates the accounts query on success, mirroring the OAuth-start hooks.
 *
 * Usage:
 *   const submitToken = useSubmitInstagramToken();
 *   submitToken.mutate({ access_token, client_id: client.id });
 */
export function useSubmitInstagramToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: SubmitInstagramTokenInput) => {
      const res = await api.post<IntegrationAccount>(
        "/api/integrations/accounts/instagram/token",
        payload,
      );
      return res;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY("instagram") });
    },
  });
}
