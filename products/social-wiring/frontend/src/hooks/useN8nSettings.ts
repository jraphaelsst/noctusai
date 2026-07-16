/**
 * n8n account settings + tags hooks — `/api/n8n/settings` and `/api/n8n/tags`.
 * Mirrors useN8nWorkflows.ts conventions (const KEY, api.* client,
 * mutation-invalidates-query pattern).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { useActiveAccountStore } from "@/state/useActiveAccount";
import type { N8nTagOut } from "@/hooks/useN8nWorkflows";

export interface N8nSettingsOut {
  account_id: string;
  base_url: string | null;
  has_api_key: boolean;
  tag: N8nTagOut | null;
  status: string;
  reachable: boolean | null;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const SETTINGS_KEY = (accountId: string | null) => ["sw", "n8n", "settings", accountId] as const;
const TAGS_KEY = (accountId: string | null) => ["sw", "n8n", "tags", accountId] as const;

// ─── Settings ───────────────────────────────────────────────────────────

/** GET /api/n8n/settings?account_id= */
export function useN8nSettings() {
  const accountId = useActiveAccountStore((s) => s.activeAccountId);
  return useQuery({
    queryKey: SETTINGS_KEY(accountId),
    queryFn: async (): Promise<N8nSettingsOut> => {
      const res = await api.get<N8nSettingsOut>(
        `/api/n8n/settings?account_id=${encodeURIComponent(accountId ?? "")}`,
      );
      // A queryFn must never return undefined.
      return (
        res ?? {
          account_id: accountId ?? "",
          base_url: null,
          has_api_key: false,
          tag: null,
          status: "unknown",
          reachable: null,
        }
      );
    },
    enabled: !!accountId,
  });
}

export interface N8nSettingsUpdateBody {
  base_url?: string;
  /** Write-only — never round-tripped back from the server. */
  api_key?: string;
  tag_id?: string;
}

/** PUT /api/n8n/settings */
export function useUpdateN8nSettings() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: (body: N8nSettingsUpdateBody) => {
      return api.put<N8nSettingsOut>("/api/n8n/settings", {
        account_id: storeAccountId,
        ...body,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sw", "n8n", "settings"] });
      // A tag change can also affect the workflow list's tag pointer.
      qc.invalidateQueries({ queryKey: ["sw", "n8n", "workflows"] });
    },
  });
}

// ─── Tags ─────────────────────────────────────────────────────────────────

/** GET /api/n8n/tags?account_id= */
export function useN8nTags() {
  const accountId = useActiveAccountStore((s) => s.activeAccountId);
  return useQuery({
    queryKey: TAGS_KEY(accountId),
    queryFn: async (): Promise<N8nTagOut[]> => {
      const res = await api.get<N8nTagOut[]>(
        `/api/n8n/tags?account_id=${encodeURIComponent(accountId ?? "")}`,
      );
      return res ?? [];
    },
    enabled: !!accountId,
  });
}

/** POST /api/n8n/tags */
export function useCreateN8nTag() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: (name: string) =>
      api.post<N8nTagOut>("/api/n8n/tags", { account_id: storeAccountId, name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sw", "n8n", "tags"] });
    },
  });
}
