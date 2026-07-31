/**
 * n8n workflow hooks — TanStack Query wrappers over `/api/n8n/workflows`.
 * Mirrors useMeta.ts / useIntegrationAccounts.ts conventions: const KEY per
 * query key, `api.*` from `@noctusai/seed/infra`, mutations invalidate the
 * relevant keys on success.
 *
 * API contract: bare typed responses (no envelope). `account_id` identifies
 * the selected client's n8n `integration_accounts` row — threaded from
 * `useActiveAccountStore` like every other social-wiring provider hook.
 *
 * Status-code contract (see PROJECT.md n8n-workflows-page §S4 brief):
 *   409 — run blocked (should not normally reach here; the FE renders the
 *         run button disabled using `can_run`/`run_blocked_reason` from the
 *         list payload BEFORE calling run, but a race is still possible).
 *   422 — invalid tree op (e.g. folder-into-own-descendant); the FE also
 *         disables the offending drop target client-side as a first line.
 *   424 — the account's n8n credential is missing/incomplete → render a
 *         "reconectar" state, NEVER an empty list.
 *   502 — the n8n instance itself is unreachable → render a distinct
 *         "instância indisponível" state, NEVER an empty list.
 * `getApiErrorStatus` recovers the numeric status from the seed api
 * client's `Error("[<status>] <message>")` convention (see
 * `seed/lib/frontend/src/api.ts:handleResponse`) — the client does not
 * carry a structured `.status` field today (flagged as scoped-improvement).
 */
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { useActiveAccountStore } from "@/state/useActiveAccount";

// ─── Types (mirror the FE↔BE contract verbatim) ─────────────────────────────

export interface N8nTagOut {
  id: string;
  name: string;
}

export interface N8nFolderOut {
  id: string; // UUID
  name: string;
  parent_id: string | null;
  position: number;
}

export interface N8nWorkflowOut {
  id: string;
  name: string;
  active: boolean;
  archived: boolean;
  tags: N8nTagOut[];
  folder_id: string | null;
  can_run: boolean;
  run_blocked_reason: string | null;
  open_url: string;
  updated_at: string | null;
}

export interface N8nWorkflowListResponse {
  workflows: N8nWorkflowOut[];
  folders: N8nFolderOut[];
}

export interface N8nExecutionOut {
  id: number;
  status: string | null;
  mode: string | null;
  started_at: string | null;
  stopped_at: string | null;
}

/**
 * Inferred — the contract table names `N8nExecutionListResponse` as the
 * return shape but doesn't spell its fields. Following the established
 * `N8nWorkflowListResponse` naming convention (`{ workflows, folders }`),
 * the executions list is assumed `{ executions: N8nExecutionOut[] }`. S3
 * MUST match this exactly or surface a contract amendment.
 */
export interface N8nExecutionListResponse {
  executions: N8nExecutionOut[];
}

export interface N8nRunResult {
  workflow_id: string;
  dispatched: boolean;
  http_status: number | null;
}

export type N8nScope = "client" | "unassigned";

// ─── Error-status helper ─────────────────────────────────────────────────

/**
 * Recovers the HTTP status code the seed api client embedded in a thrown
 * `Error("[<status>] <message>")`. Returns null when the error isn't in that
 * shape (network failure, non-Error throw, etc).
 */
export function getApiErrorStatus(err: unknown): number | null {
  if (!(err instanceof Error)) return null;
  const match = err.message.match(/^\[(\d+)\]/);
  return match ? parseInt(match[1], 10) : null;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const WORKFLOWS_KEY = (
  accountId: string | null,
  scope: N8nScope,
  includeArchived: boolean,
) => ["sw", "n8n", "workflows", accountId, scope, includeArchived] as const;

const EXECUTIONS_KEY = (workflowId: string, accountId: string | null) =>
  ["sw", "n8n", "workflows", workflowId, "executions", accountId] as const;

function invalidateAllWorkflowLists(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["sw", "n8n", "workflows"] });
}

// ─── List hook ───────────────────────────────────────────────────────────

export interface UseN8nWorkflowsOptions {
  scope: N8nScope;
  includeArchived?: boolean;
  /** Overrides the store's active account; mainly for tests. */
  accountId?: string | null;
}

/**
 * useN8nWorkflows — GET /api/n8n/workflows?account_id&scope&include_archived
 *
 * Returns the react-query result verbatim (not unwrapped) so callers can
 * read `isLoading` / `isError` / `error` directly — the 424-vs-502 status
 * distinction lives in `error` via `getApiErrorStatus`.
 */
export function useN8nWorkflows(
  options: UseN8nWorkflowsOptions,
): UseQueryResult<N8nWorkflowListResponse, Error> {
  const { scope, includeArchived = false, accountId: accountIdOverride } = options;
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  const accountId = accountIdOverride !== undefined ? accountIdOverride : storeAccountId;

  return useQuery({
    queryKey: WORKFLOWS_KEY(accountId, scope, includeArchived),
    queryFn: async (): Promise<N8nWorkflowListResponse> => {
      const params = new URLSearchParams();
      if (accountId) params.set("account_id", accountId);
      params.set("scope", scope);
      params.set("include_archived", String(includeArchived));
      const res = await api.get<N8nWorkflowListResponse>(
        `/api/n8n/workflows?${params.toString()}`,
      );
      // A queryFn must never return undefined — the backend always ships
      // `{workflows, folders}` on 200, but stay defensive.
      return res ?? { workflows: [], folders: [] };
    },
    enabled: !!accountId,
  });
}

// ─── Assign / unassign ─────────────────────────────────────────────────────

/** POST /api/n8n/workflows/{id}/assign — the ONLY way a workflow enters a
 * client's tree (applies the client's n8n tag). */
export function useAssignWorkflow() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: ({ workflowId, accountId }: { workflowId: string; accountId?: string | null }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.post<N8nWorkflowOut>(
        `/api/n8n/workflows/${encodeURIComponent(workflowId)}/assign`,
        { account_id: effectiveAccountId },
      );
    },
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}

/** DELETE /api/n8n/workflows/{id}/assign — removes the client tag (moves
 * the workflow back to the "Sem cliente" bucket). */
export function useUnassignWorkflow() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: ({ workflowId, accountId }: { workflowId: string; accountId?: string | null }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.delete<N8nWorkflowOut>(
        `/api/n8n/workflows/${encodeURIComponent(workflowId)}/assign?account_id=${encodeURIComponent(
          effectiveAccountId ?? "",
        )}`,
      );
    },
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}

// ─── Update (rename / toggle active / move folder) ─────────────────────────

export interface N8nWorkflowUpdateBody {
  name?: string;
  active?: boolean;
  folder_id?: string | null;
}

/** PATCH /api/n8n/workflows/{id} */
export function useUpdateWorkflow() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: ({
      workflowId,
      body,
      accountId,
    }: {
      workflowId: string;
      body: N8nWorkflowUpdateBody;
      accountId?: string | null;
    }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.patch<N8nWorkflowOut>(`/api/n8n/workflows/${encodeURIComponent(workflowId)}`, {
        account_id: effectiveAccountId,
        ...body,
      });
    },
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}

// ─── Delete ─────────────────────────────────────────────────────────────

/** DELETE /api/n8n/workflows/{id} — irreversible; caller must confirm first. */
export function useDeleteWorkflow() {
  const qc = useQueryClient();
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: ({ workflowId, accountId }: { workflowId: string; accountId?: string | null }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.delete<void>(
        `/api/n8n/workflows/${encodeURIComponent(workflowId)}?account_id=${encodeURIComponent(
          effectiveAccountId ?? "",
        )}`,
      );
    },
    onSuccess: () => invalidateAllWorkflowLists(qc),
  });
}

// ─── Run ─────────────────────────────────────────────────────────────────

/** POST /api/n8n/workflows/{id}/run — the caller MUST gate on `can_run`
 * before invoking (the UI never offers a clickable-looking disabled button). */
export function useRunWorkflow() {
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useMutation({
    mutationFn: ({ workflowId, accountId }: { workflowId: string; accountId?: string | null }) => {
      const effectiveAccountId = accountId ?? storeAccountId;
      return api.post<N8nRunResult>(`/api/n8n/workflows/${encodeURIComponent(workflowId)}/run`, {
        account_id: effectiveAccountId,
      });
    },
  });
}

// ─── Executions ─────────────────────────────────────────────────────────

/** GET /api/n8n/workflows/{id}/executions — on-demand (enabled only while
 * the executions dialog for that workflow is open). */
export function useWorkflowExecutions(workflowId: string | null, limit = 20) {
  const storeAccountId = useActiveAccountStore((s) => s.activeAccountId);
  return useQuery({
    queryKey: EXECUTIONS_KEY(workflowId ?? "", storeAccountId),
    queryFn: async (): Promise<N8nExecutionListResponse> => {
      const params = new URLSearchParams();
      if (storeAccountId) params.set("account_id", storeAccountId);
      params.set("limit", String(limit));
      const res = await api.get<N8nExecutionListResponse>(
        `/api/n8n/workflows/${encodeURIComponent(workflowId ?? "")}/executions?${params.toString()}`,
      );
      return res ?? { executions: [] };
    },
    enabled: !!workflowId && !!storeAccountId,
  });
}
