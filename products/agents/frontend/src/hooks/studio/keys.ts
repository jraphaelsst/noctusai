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
  // Julia v2 (content API, qualification standard, library, controls, channel threads).
  conteudo: (key: string, kind: string, vid: string) => ["studio", key, "conteudo", kind, vid] as const,
  conteudoAll: (key: string) => ["studio", key, "conteudo"] as const,
  payload: (key: string, vid: string) => ["studio", key, "payload", vid] as const,
  orgSpecs: (key: string) => ["studio", key, "org-specs"] as const,
  orgStatus: (key: string) => ["studio", key, "org-status"] as const,
  compiladoOrg: (key: string, versao: string) => ["studio", key, "compilado-org", versao] as const,
  controle: (key: string) => ["studio", key, "controle"] as const,
  canal: (key: string) => ["studio", key, "canal"] as const,
  threadMensagens: (key: string, threadId: string) => ["studio", key, "canal", "mensagens", threadId] as const,
  conformidade: (key: string) => ["studio", key, "conformidade"] as const,
  bibliotecaRefs: (key: string, vid: string) => ["studio", key, "biblioteca-refs", vid] as const,
  plataformaTextos: () => ["studio", "__plataforma__", "textos"] as const,
  contentTokens: () => ["studio", "__plataforma__", "content-tokens"] as const,
  biblioteca: () => ["studio", "__biblioteca__"] as const,
  bibliotecaVersoes: (chave: string) => ["studio", "__biblioteca__", chave, "versoes"] as const,
  bibliotecaVersao: (id: string) => ["studio", "__biblioteca__", "versao", id] as const,
  qual: () => ["studio", "__qualificacao__"] as const,
  qualVersoes: (chave: string) => ["studio", "__qualificacao__", chave, "versoes"] as const,
  qualVersao: (id: string) => ["studio", "__qualificacao__", "versao", id] as const,
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
