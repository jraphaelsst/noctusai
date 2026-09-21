/**
 * Agent Studio — query keys + the one loading-state projection every studio
 * hook returns.
 *
 * KEY CONVENTION (shared with FE-KE, which cannot import this file in wave 1):
 * every studio query key starts with `["studio", <agentKey>, ...]`, so
 * `invalidateQueries({ queryKey: ["studio", key] })` refreshes everything an
 * agent owns. The agent list is `["studio", "__list__"]` (a key can never be
 * `__list__` — §B1 slug CHECK forbids underscores).
 *
 * LOADING (`KB § PATTERNS/frontend/lying-loading-state.md`): the two signals
 * are derived HERE, once, from `data` — never `isLoading`, never a bare
 * `isFetching`. Consumers get `showSkeleton` (nothing to render yet) and
 * `isRefreshing` (indicator only). `isPlaceholderData` is exposed so an
 * editor never seeds its form from a PREVIOUS key's placeholder.
 */
import type { UseQueryResult } from "@tanstack/react-query";

export const studioKeys = {
  list: () => ["studio", "__list__"] as const,
  agent: (key: string) => ["studio", key] as const,
  detail: (key: string) => ["studio", key, "detail"] as const,
  versions: (key: string) => ["studio", key, "version"] as const,
  version: (key: string, vid: string) => ["studio", key, "version", vid] as const,
  skillFile: (key: string, skillId: string, fileId: string) =>
    ["studio", key, "skill-file", skillId, fileId] as const,
  compiledAll: (key: string) => ["studio", key, "compiled"] as const,
  compiled: (key: string, vid: string, clientId: string | null) =>
    ["studio", key, "compiled", vid, clientId ?? "__sem_cliente__"] as const,
  diff: (key: string, a: string, b: string) => ["studio", key, "diff", a, b] as const,
  clients: (key: string) => ["studio", key, "clients"] as const,
  client: (key: string, clientId: string) => ["studio", key, "clients", clientId] as const,
  prompt: (hash: string) => ["studio-prompt", hash] as const,
};

export interface QueryView<T> {
  data: T | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  error: unknown;
  isPlaceholderData: boolean;
  refetch: () => void;
}

export function toView<T>(q: UseQueryResult<T>): QueryView<T> {
  return {
    data: q.data,
    showSkeleton: q.isPending && !q.data,
    isRefreshing: q.isFetching && !!q.data,
    isError: q.isError,
    error: q.error,
    isPlaceholderData: q.isPlaceholderData,
    refetch: () => {
      void q.refetch();
    },
  };
}

/**
 * `placeholderData` that keeps the previous result ONLY while the agent stays
 * the same (key position 1). Switching version / client / diff pair inside one
 * agent keeps the view mounted; switching agents never shows the previous
 * agent's definition under the new agent's header.
 */
export function keepWithinAgent<T>(agentKey: string) {
  return (prev: T | undefined, prevQuery?: { queryKey: readonly unknown[] }) =>
    prevQuery && prevQuery.queryKey[1] === agentKey ? prev : undefined;
}

/** Encodes one path segment (keys/ids are slug/uuid-shaped, but never trust that). */
export function seg(value: string): string {
  return encodeURIComponent(value);
}
