/**
 * Approvals hooks — contract §E.2
 * (`GET /api/approvals?estado=pendente`, `POST /api/approvals/{id}/decision`).
 *
 * Shared by the standalone `/aprovacoes` page AND `useJuliaChat.ts`'s
 * `useApprovalAction` adapter (the `ChatWindow` approval-card seam,
 * contract §E.7) — both decide through the SAME mutation shape so a
 * decision made from either surface invalidates both caches.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";

export const APPROVALS_KEY = ["agents", "approvals", "pendente"] as const;
/** Prefix shared with `useJuliaChat.ts`'s per-conversation messages key —
 * used to invalidate every open conversation's message list after a
 * decision lands somewhere else (contract §E.2 "then refetch"). */
export const CONVERSATIONS_PREFIX = ["agents", "julia", "conversations"] as const;

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

interface ApprovalListResponse {
  items: Approval[];
  total: number;
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
  const qc = useQueryClient();

  const mutation = useMutation<Approval, unknown, { approvalId: string; aprovada: boolean }>({
    mutationFn: ({ approvalId, aprovada }) =>
      api.post<Approval>(`/api/approvals/${approvalId}/decision`, { aprovada }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: APPROVALS_KEY });
      qc.invalidateQueries({ queryKey: CONVERSATIONS_PREFIX });
    },
    onError: () => {
      // already_decided / orphaned — refetch so the card/list reflects the
      // authoritative server state (contract §E.2 "then refetch").
      qc.invalidateQueries({ queryKey: APPROVALS_KEY });
      qc.invalidateQueries({ queryKey: CONVERSATIONS_PREFIX });
    },
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
