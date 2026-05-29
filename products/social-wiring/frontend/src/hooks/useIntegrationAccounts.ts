/**
 * Integration accounts hooks — TanStack Query wrappers for the
 * multi-account credential system. Mirrors useTeam.ts conventions:
 *   · const KEY per query key
 *   · api.get / api.post / api.patch / api.delete from @noctusai/seed/infra
 *   · mutations invalidate their relevant keys on success
 *
 * Providers: YouTube, Meta, n8n, Google Drive, Gmail (WAHA excluded — handled
 * by Conexao page / useWhatsAppConnections).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface ManualKeyField {
  key: string;
  label: string;
  placeholder: string;
  type: "text" | "password" | "url";
}

export interface IntegrationProvider {
  name: string;
  display_name: string;
  oauth_supported: boolean;
  manual_key_fields: ManualKeyField[];
  tutorial_url: string | null;
  scopes: string[];
}

export interface IntegrationAccount {
  id: string;
  provider: string;
  account_label: string;
  metadata: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateAccountInput {
  provider: string;
  account_label: string;
  credential: Record<string, string>;
  metadata?: Record<string, unknown>;
  is_default?: boolean;
}

export interface UpdateAccountInput {
  account_label?: string;
  credential?: Record<string, string>;
  metadata?: Record<string, unknown>;
}

export interface OAuthStartResponse {
  auth_url: string;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const PROVIDERS_KEY = ["sw", "integrations", "providers"] as const;
const ACCOUNTS_KEY = (provider?: string) =>
  provider
    ? (["sw", "integrations", "accounts", provider] as const)
    : (["sw", "integrations", "accounts"] as const);
const ACCOUNT_KEY = (id: string) => ["sw", "integrations", "accounts", "detail", id] as const;

// ─── Provider registry ───────────────────────────────────────────────────────

export function useIntegrationProviders() {
  return useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: async () => {
      const res = await api.get<{ providers: IntegrationProvider[] }>(
        "/api/integrations/providers"
      );
      return res.providers ?? [];
    },
    staleTime: 5 * 60 * 1000, // provider list changes rarely
  });
}

// ─── Account list ────────────────────────────────────────────────────────────

export function useIntegrationAccounts(provider?: string) {
  return useQuery({
    queryKey: ACCOUNTS_KEY(provider),
    queryFn: async () => {
      const url = provider
        ? `/api/integrations/accounts?provider=${encodeURIComponent(provider)}`
        : "/api/integrations/accounts";
      const res = await api.get<{ data: IntegrationAccount[] }>(url);
      return res.data ?? [];
    },
  });
}

// ─── Single account ──────────────────────────────────────────────────────────

export function useIntegrationAccount(id: string) {
  return useQuery({
    queryKey: ACCOUNT_KEY(id),
    queryFn: async () => {
      const res = await api.get<{ data: IntegrationAccount }>(
        `/api/integrations/accounts/${id}`
      );
      return res.data;
    },
    enabled: !!id,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAccountInput) =>
      api.post<{ data: IntegrationAccount }>("/api/integrations/accounts", payload),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(variables.provider) });
    },
  });
}

export function useUpdateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateAccountInput & { id: string }) =>
      api.patch<{ data: IntegrationAccount }>(`/api/integrations/accounts/${id}`, payload),
    onSuccess: (res) => {
      const provider = (res as any)?.data?.provider;
      qc.invalidateQueries({ queryKey: ACCOUNTS_KEY() });
      if (provider) qc.invalidateQueries({ queryKey: ACCOUNTS_KEY(provider) });
    },
  });
}

export function useSetDefaultAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.patch<{ data: IntegrationAccount }>(
        `/api/integrations/accounts/${id}/set-default`,
        {}
      ),
    onSuccess: (res) => {
      const provider = (res as any)?.data?.provider;
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

// ─── YouTube OAuth ───────────────────────────────────────────────────────────

export function useStartYouTubeOAuth() {
  return useMutation({
    mutationFn: async () => {
      const res = await api.post<OAuthStartResponse>(
        "/api/integrations/accounts/youtube/oauth/start",
        {}
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
