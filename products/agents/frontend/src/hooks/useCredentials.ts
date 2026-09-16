/**
 * Credenciais e integrações — `/api/admin/credentials` (platform admin only).
 *
 * No hook here ever receives a secret: the backend returns `prefix` /
 * `fingerprint` only. `useSetCredential` sends a value the page never keeps
 * after the request (write-only field).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const CREDENTIALS_KEY = ["agents", "admin", "credentials"] as const;

export type CredentialKind = "product_token" | "api_key" | "key_ring" | "config";
export type Severity = "info" | "warning" | "critical";

export interface RingKey {
  fingerprint: string;
  active_from: string;
  retire_at: string | null;
  signing: boolean;
  state: "staged" | "active" | "retiring" | "retired";
}

export interface Credential {
  name: string;
  label: string;
  kind: CredentialKind;
  env_var: string;
  configured: boolean;
  source: "db" | "env" | null;
  prefix: string | null;
  fingerprint: string | null;
  value: string | null;
  expires_at: string | null;
  days_left: number | null;
  last_used_at: string | null;
  revoked: boolean;
  scopes: string[];
  renewable: boolean;
  probeable: boolean;
  writable: boolean;
  ring: RingKey[];
  warnings: string[];
  severity: Severity;
}

export interface CredentialList {
  items: Credential[];
  total: number;
  alerts: number;
}

export interface ProbeResult {
  name: string;
  status: "ok" | "unauthorized" | "forbidden" | "unreachable" | "error";
  ok: boolean;
  http_status: number | null;
  detail: string;
  checked_at: string;
}

export interface RenewResult {
  credential: Credential;
  warnings: string[];
}

/**
 * `enabled` lets a caller (the dashboard banner) skip the request for a user
 * who can't be a platform admin. Never retried: a 403 is an answer.
 */
export function useCredentials({ enabled = true }: { enabled?: boolean } = {}) {
  const query = useQuery<CredentialList>({
    queryKey: CREDENTIALS_KEY,
    queryFn: () => api.get<CredentialList>("/api/admin/credentials"),
    enabled,
    retry: false,
  });

  return {
    data: query.data,
    error: query.error,
    showSkeleton: enabled && query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
  };
}

function useReplaceOne() {
  const qc = useQueryClient();
  return (updated: Credential) =>
    qc.setQueryData<CredentialList>(CREDENTIALS_KEY, (prev) => {
      if (!prev) return prev;
      const items = prev.items.map((c) => (c.name === updated.name ? updated : c));
      return { ...prev, items, alerts: items.filter((c) => c.severity !== "info").length };
    });
}

export function useSetCredential() {
  const replace = useReplaceOne();
  return useMutation<Credential, unknown, { name: string; value: string }>({
    mutationFn: ({ name, value }) => api.put<Credential>(`/api/admin/credentials/${name}`, { value }),
    onSuccess: replace,
  });
}

export function useImportCredential() {
  const replace = useReplaceOne();
  return useMutation<Credential, unknown, { name: string }>({
    mutationFn: ({ name }) => api.post<Credential>(`/api/admin/credentials/${name}/import-env`, {}),
    onSuccess: replace,
  });
}

export function useProbeCredential() {
  return useMutation<ProbeResult, unknown, { name: string }>({
    mutationFn: ({ name }) => api.post<ProbeResult>(`/api/admin/credentials/${name}/health`, {}),
  });
}

export function useRenewCredential() {
  const replace = useReplaceOne();
  return useMutation<RenewResult, unknown, { name: string }>({
    mutationFn: ({ name }) => api.post<RenewResult>(`/api/admin/credentials/${name}/renew`, {}),
    onSuccess: (result) => replace(result.credential),
  });
}

export function useRingAction() {
  const replace = useReplaceOne();
  return useMutation<Credential, unknown, { action: "rotate" | "prune" }>({
    mutationFn: ({ action }) =>
      api.post<Credential>(`/api/admin/credentials/approval_assertion_secrets/${action}`, {}),
    onSuccess: replace,
  });
}
