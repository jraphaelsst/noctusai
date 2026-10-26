/**
 * `createOrgSpecsHooks(api, options?)` — the org's own context for an agent (TanStack Query v5).
 *
 * The `agents` product declares, per agent definition, the placeholders an org fills (`{{org.<chave>}}`):
 *   GET {path(agentKey)}  → OrgSpecsData  (the FORM: label/help/type/required, the org's values, what is missing)
 *   PUT {path(agentKey)}  → { valores } → OrgSpecsData  (admin-only, enforced server-side; blank clears)
 *
 * The default `path` is agents' own Studio route. A product that is not agents (e.g. `monica`) passes
 * its OWN backend proxy, which forwards the logged-in user's token to agents
 * (`noctusai_lib.integrations.agents.make_agents_org_specs_client`):
 *   createOrgSpecsHooks(api, { path: () => "/api/contexto" })
 *
 * Writes go through `useCacheWriteMutation` (the saved view is committed to the cache; derived views
 * named in `invalidate` refetch in the background). → KB § INTEGRATIONS/agents-org-specs.md
 */
import { useQuery, type QueryKey } from '@tanstack/react-query';
import { useCacheWriteMutation } from '../../cache-writes';
import type { ApiClient } from '../../api';

export interface OrgSpecDef {
  chave: string;
  rotulo: string;
  descricao?: string | null;
  tipo: 'texto' | 'texto_longo';
  obrigatoria: boolean;
  exemplo?: string | null;
  id?: string;
}
export interface OrgSpecValor {
  chave: string;
  valor: string;
  updated_at?: string | null;
}
export interface OrgSpecsData {
  agent_key: string;
  version_id?: string | null;
  versao?: number | null;
  declaradas: OrgSpecDef[];
  valores: OrgSpecValor[];
  faltando: string[];
}

/** What a screen needs from a query without ever misreading "loading" as "empty". */
export interface OrgSpecsView {
  data: OrgSpecsData | undefined;
  /** First load, nothing to show yet. */
  showSkeleton: boolean;
  /** Showing data while a refetch runs. */
  isRefreshing: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

export interface CreateOrgSpecsHooksOptions {
  /** Route of the specs resource for an agent. Default: agents' `/api/studio/agents/{key}/specs`. */
  path?: (agentKey: string) => string;
  /** Cache key of the specs entry; position 1 should identify the agent. Default `['org-specs', agentKey]`. */
  queryKey?: (agentKey: string) => QueryKey;
  /** Derived views to refetch after a save (completeness status, compiled prompt, controls...). */
  invalidate?: (agentKey: string) => QueryKey[];
}

export interface OrgSpecsHooks {
  useOrgSpecs: (agentKey: string) => OrgSpecsView;
  useUpdateOrgSpecs: (agentKey: string) => ReturnType<typeof useCacheWriteMutation<OrgSpecsData, { valores: Record<string, string> }>>;
}

export function createOrgSpecsHooks(api: ApiClient, options: CreateOrgSpecsHooksOptions = {}): OrgSpecsHooks {
  const path = options.path ?? ((k: string) => `/api/studio/agents/${encodeURIComponent(k)}/specs`);
  const keyOf = options.queryKey ?? ((k: string): QueryKey => ['org-specs', k]);

  function useOrgSpecs(agentKey: string): OrgSpecsView {
    const q = useQuery<OrgSpecsData>({
      queryKey: keyOf(agentKey),
      queryFn: () => api.get<OrgSpecsData>(path(agentKey)),
      enabled: !!agentKey,
      retry: false,
      // Keep the previous result only while the agent stays the same: never show agent A's form under agent B.
      placeholderData: (prev, prevQuery) => (prevQuery && prevQuery.queryKey.includes(agentKey) ? prev : undefined),
    });
    return {
      data: q.data,
      showSkeleton: q.isPending && !q.data,
      isRefreshing: q.isFetching && !!q.data,
      isError: q.isError,
      error: q.error,
      refetch: () => {
        void q.refetch();
      },
    };
  }

  function useUpdateOrgSpecs(agentKey: string) {
    return useCacheWriteMutation<OrgSpecsData, { valores: Record<string, string> }>({
      mutationFn: (payload) => api.put<OrgSpecsData>(path(agentKey), payload),
      targets: [{ queryKey: keyOf(agentKey), commit: (_old, saved) => saved }],
      invalidate: options.invalidate?.(agentKey) ?? [],
    });
  }

  return { useOrgSpecs, useUpdateOrgSpecs };
}
