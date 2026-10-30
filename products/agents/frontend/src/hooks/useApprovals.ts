/**
 * Approvals hooks — contract §E.2
 * (`GET /api/approvals?estado=pendente`, `POST /api/approvals/{id}/decision`).
 *
 * Shared by the standalone `/aprovacoes` page AND the chat windows'
 * `useApprovalAction` seam (`useApprovalDecisionAdapter`, contract §E.7 —
 * the legacy chat and, since the Renata cutover, a Studio `claude_sdk` agent
 * carrying the academia write tools) — every surface decides through the SAME
 * mutation shape so a decision made from either invalidates both caches.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";

export const APPROVALS_KEY = ["agents", "approvals", "pendente"] as const;
/** Prefix shared with `useLegacyChat.ts`'s per-conversation messages key —
 * used to invalidate every open conversation's message list after a
 * decision lands somewhere else (contract §E.2 "then refetch"). */
export const CONVERSATIONS_PREFIX = ["agents", "bia", "conversations"] as const;

export interface ApprovalDiff {
  antes: string | null;
  depois: string;
}

export interface Approval {
  id: string;
  conversation_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  classe: string;
  resumo: string;
  diff: ApprovalDiff | null;
  decision: "pendente" | "aprovada" | "negada" | "expirada";
  decided_by: string | null;
  decided_at: string | null;
  requested_by: string;
  created_at: string;
  updated_at: string;
}

export interface ApprovalListResponse {
  items: Approval[];
  total: number;
}

/** The decided approval leaves the cached pending list (and `total`). Shared with `useLegacyChat.ts`. */
export function withoutApproval(
  old: ApprovalListResponse | undefined,
  approvalId: string,
): ApprovalListResponse | undefined {
  if (!old?.items.some((a) => a.id === approvalId)) return old;
  return { ...old, items: old.items.filter((a) => a.id !== approvalId), total: Math.max(0, old.total - 1) };
}

export function useApprovals() {
  const query = useQuery<ApprovalListResponse>({
    queryKey: APPROVALS_KEY,
    queryFn: () => api.get<ApprovalListResponse>("/api/approvals", { estado: "pendente" }),
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
  };
}

/**
 * Decide a pending approval. Contract §E.2 error rows: 409 `already_decided`
 * (someone else — or another tab — already settled it) and 409 `orphaned`
 * (no live turn is waiting, e.g. the process restarted) both mean "the local
 * view is stale" — the caller MUST refetch after showing the message so the
 * UI reflects the authoritative server state instead of staying stuck on a
 * `pendente` row that no longer exists.
 */
export function useDecideApproval() {
  const mutation = useCacheWriteMutation<Approval, { approvalId: string; aprovada: boolean }>({
    mutationFn: ({ approvalId, aprovada }) =>
      api.post<Approval>(`/api/approvals/${approvalId}/decision`, { aprovada }),
    // A decided approval leaves the pending list on the click. On error the card comes back
    // (rollback) and settle re-reads the authoritative state — already_decided / orphaned
    // (contract §E.2 "then refetch"). Open conversations' messages carry the decision card:
    // server-rendered, so they are refreshed in the background, on success AND on error.
    targets: ({ approvalId }) => [
      {
        queryKey: APPROVALS_KEY,
        optimistic: (old: ApprovalListResponse | undefined) => withoutApproval(old, approvalId),
      },
    ],
    invalidate: [CONVERSATIONS_PREFIX],
  });

  return {
    decide: async (approvalId: string, aprovada: boolean) => {
      try {
        await mutation.mutateAsync({ approvalId, aprovada });
      } catch (err) {
        throw new Error(errorMessage(err));
      }
    },
    isPending: mutation.isPending,
  };
}


/** Prefix of every approvals query (pending list + any filtered view). */
const APPROVALS_KEY_PREFIX = ["agents", "approvals"] as const;

/**
 * The `ChatWindow` approval-card seam (contract §E.7): one decision POST, the decided approval leaves the pending
 * list on the click (rolled back on error), and the settle refetch covers the "already_decided" / "orphaned"
 * contract (§E.2). Used by every chat window that can show an approval card.
 */
export function useApprovalDecisionAdapter() {
  const mutation = useCacheWriteMutation<unknown, { approvalId: string; aprovada: boolean }>({
    mutationFn: ({ approvalId, aprovada }) => api.post(`/api/approvals/${approvalId}/decision`, { aprovada }),
    targets: ({ approvalId }) => [
      {
        queryKey: APPROVALS_KEY,
        optimistic: (old: ApprovalListResponse | undefined) => withoutApproval(old, approvalId),
      },
    ],
    invalidate: [CONVERSATIONS_PREFIX, APPROVALS_KEY_PREFIX],
  });

  return {
    decide: async (approvalId: string, aprovada: boolean) => {
      try {
        await mutation.mutateAsync({ approvalId, aprovada });
      } catch (err) {
        throw new Error(errorMessage(err));
      }
    },
    isPending: mutation.isPending,
  };
}
