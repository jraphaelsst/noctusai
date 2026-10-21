/**
 * n8n account settings + tags hooks — `/api/n8n/settings` and `/api/n8n/tags`.
 * Mirrors useN8nWorkflows.ts conventions (const KEY, api.* client,
 * mutation-invalidates-query pattern).
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { useActiveAccountId } from "@/state/useActiveAccount";
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
  const accountId = useActiveAccountId("n8n");
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
  const storeAccountId = useActiveAccountId("n8n");
  return useCacheWriteMutation<N8nSettingsOut, N8nSettingsUpdateBody>({
    mutationFn: (body) => {
      return api.put<N8nSettingsOut>("/api/n8n/settings", {
        account_id: storeAccountId,
        ...body,
      });
    },
    // The PUT answers with the settings row: it is the cache entry for this account.
    targets: [{ queryKey: SETTINGS_KEY(storeAccountId), commit: (_old, saved) => saved }],
    // A tag change can also affect the workflow list's tag pointer.
    invalidate: [["sw", "n8n", "settings"], ["sw", "n8n", "workflows"]],
  });
}

// ─── Tags ─────────────────────────────────────────────────────────────────

/** GET /api/n8n/tags?account_id= */
export function useN8nTags() {
  const accountId = useActiveAccountId("n8n");
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
  const storeAccountId = useActiveAccountId("n8n");
  return useCacheWriteMutation<N8nTagOut, string>({
    mutationFn: (name) =>
      api.post<N8nTagOut>("/api/n8n/tags", { account_id: storeAccountId, name }),
    targets: [
      { queryKey: TAGS_KEY(storeAccountId), commit: (old: N8nTagOut[] | undefined, saved) => listOps.replace(old, saved.id, saved) },
    ],
  });
}
