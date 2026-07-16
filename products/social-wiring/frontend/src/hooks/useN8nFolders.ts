/**
 * n8n folder-tree mutation hooks — `/api/n8n/folders`. The tree itself is
 * read as part of `useN8nWorkflows`'s list payload (`{workflows, folders}`);
 * these hooks only cover the create/reparent/delete mutations, all of which
 * invalidate the shared workflow-list query keys on success.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { useActiveAccountStore } from "@/state/useActiveAccount";
import type { N8nFolderOut } from "@/hooks/useN8nWorkflows";

function invalidateAllWorkflowLists(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["sw", "n8n", "workflows"] });
}

// ─── Create ─────────────────────────────────────────────────────────────

export interface N8nFolderCreateBody {
  name: string;
  parent_id?: string | null;
}

/** POST /api/n8n/folders */
export function useCreateFolder() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: ({ body, accountId }: { body: N8nFolderCreateBody; accountId?: string | null }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.post<N8nFolderOut>("/api/n8n/folders", {
        account_id: effectiveAccountId,
        ...body,
      });
    },
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}

// ─── Update (rename / reparent / reorder) ───────────────────────────────

export interface N8nFolderUpdateBody {
  name?: string;
  parent_id?: string | null;
  position?: number;
}

/** PATCH /api/n8n/folders/{id} */
export function useUpdateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, body }: { folderId: string; body: N8nFolderUpdateBody }) =>
      api.patch<N8nFolderOut>(`/api/n8n/folders/${encodeURIComponent(folderId)}`, body),
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}

// ─── Delete ─────────────────────────────────────────────────────────────

/**
 * DELETE /api/n8n/folders/{id}?reassign_to=<uuid|null>
 *
 * `reassignTo` is REQUIRED by the caller (even if `null`) — the contract
 * states where the folder's workflows/child-folders land after delete.
 * Inferred query encoding: `null` OMITS the query param entirely (standard
 * FastAPI `Optional[UUID] = None` — a literal `"null"` string would fail
 * UUID parsing and 422); a UUID is sent verbatim. S3 must match this
 * encoding exactly.
 */
export function useDeleteFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, reassignTo }: { folderId: string; reassignTo: string | null }) => {
      const qs = reassignTo !== null ? `?reassign_to=${encodeURIComponent(reassignTo)}` : "";
      return api.delete<void>(`/api/n8n/folders/${encodeURIComponent(folderId)}${qs}`);
    },
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}
