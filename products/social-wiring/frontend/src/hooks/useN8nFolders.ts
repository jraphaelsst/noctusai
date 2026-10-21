/**
 * n8n folder-tree mutation hooks — `/api/n8n/folders`. The tree itself is
 * read as part of `useN8nWorkflows`'s list payload (`{workflows, folders}`);
 * these hooks only cover the create/reparent/delete mutations, all of which
 * invalidate the shared workflow-list query keys on success.
 */
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { useActiveAccountId } from "@/state/useActiveAccount";
import type { N8nFolderOut, N8nWorkflowListResponse } from "@/hooks/useN8nWorkflows";

const WORKFLOWS_PREFIX = ["sw", "n8n", "workflows"] as const;

// ─── Create ─────────────────────────────────────────────────────────────

export interface N8nFolderCreateBody {
  name: string;
  parent_id?: string | null;
}

/** POST /api/n8n/folders */
export function useCreateFolder() {
  const storeAccountId = useActiveAccountId("n8n");
  return useCacheWriteMutation<N8nFolderOut, { body: N8nFolderCreateBody; accountId?: string | null }>({
    mutationFn: ({ body, accountId }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.post<N8nFolderOut>("/api/n8n/folders", {
        account_id: effectiveAccountId,
        ...body,
      });
    },
    // The folder tree rides on every scope/archived list of ONE account (`[…, accountId, scope, archived]`):
    // the new folder lands in exactly those lists, never in another account's.
    targets: ({ accountId }) => [
      {
        queryKey: WORKFLOWS_PREFIX,
        match: "prefix",
        predicate: (key) => key.length === 6 && key[3] === (accountId ?? storeAccountId),
        commit: (old: N8nWorkflowListResponse | undefined, saved) =>
          listOps.within(old, "folders", (l) => listOps.insertSorted(l, saved, (a, b) => a.position - b.position)),
      },
    ],
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
  return useCacheWriteMutation<N8nFolderOut, { folderId: string; body: N8nFolderUpdateBody }>({
    mutationFn: ({ folderId, body }) =>
      api.patch<N8nFolderOut>(`/api/n8n/folders/${encodeURIComponent(folderId)}`, body),
    // Folder ids are globally unique, so the prefix only changes the lists that hold this folder.
    targets: ({ folderId }) => [
      {
        queryKey: WORKFLOWS_PREFIX,
        match: "prefix",
        commit: (old: N8nWorkflowListResponse | undefined, saved) =>
          listOps.within(old, "folders", (l) => listOps.patch(l, folderId, saved) ?? l),
      },
    ],
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
  return useCacheWriteMutation<void, { folderId: string; reassignTo: string | null }>({
    mutationFn: ({ folderId, reassignTo }) => {
      const qs = reassignTo !== null ? `?reassign_to=${encodeURIComponent(reassignTo)}` : "";
      return api.delete<void>(`/api/n8n/folders/${encodeURIComponent(folderId)}${qs}`);
    },
    // The folder leaves every cached list; its workflows and child folders land where the caller said.
    targets: ({ folderId, reassignTo }) => [
      {
        queryKey: WORKFLOWS_PREFIX,
        match: "prefix",
        optimistic: (old: N8nWorkflowListResponse | undefined) => {
          if (!old?.folders?.some((f) => f.id === folderId)) return old;
          return {
            ...old,
            folders: old.folders
              .filter((f) => f.id !== folderId)
              .map((f) => (f.parent_id === folderId ? { ...f, parent_id: reassignTo } : f)),
            workflows: old.workflows.map((w) => (w.folder_id === folderId ? { ...w, folder_id: reassignTo } : w)),
          };
        },
      },
    ],
  });
}
