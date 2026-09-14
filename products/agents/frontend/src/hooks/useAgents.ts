/**
 * Agents list + toggle hooks — contract §E.2
 * (`GET /api/agents`, `POST /api/agents/{key}/toggle`).
 *
 * `GET /api/agents` returns `estado_externo: {auto_reply_enabled} | null`
 * for `one-chat` (live from social-wiring), plus `aviso` when it could not
 * be reached / is not configured yet. `julia`'s own `ativo` is the local
 * source of truth; `one-chat`'s `ativo` mirrors whatever social-wiring last
 * reported (contract: "the response reflects social-wiring's returned
 * state").
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

const AGENTS_KEY = ["agents", "list"] as const;

export interface EstadoExterno {
  auto_reply_enabled: boolean;
}

export interface Agent {
  key: string;
  nome: string;
  runtime: string;
  owner_product: string | null;
  ativo: boolean;
  estado_externo: EstadoExterno | null;
  aviso: string | null;
}

interface AgentListResponse {
  items: Agent[];
  total: number;
}

/**
 * `isPending` alone, NOT `isPending || isFetching` — the org has few
 * agents so this list never paginates, but the same reasoning as
 * `WhatsAppChatWindow`'s adapter hooks applies: once the first page has
 * landed, a background refetch (e.g. after a toggle's invalidate) must not
 * unmount the list back to a skeleton
 * (`KB § PATTERNS/frontend/lying-loading-state.md`).
 */
export function useAgents() {
  const query = useQuery<AgentListResponse>({
    queryKey: AGENTS_KEY,
    queryFn: () => api.get<AgentListResponse>("/api/agents"),
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    refetch: query.refetch,
  };
}

/**
 * Toggle an agent on/off — optimistic with rollback on error (contract
 * §E.2: "502 upstream_failed" / "409 not_configured"). The optimistic patch
 * only flips `ativo`; `estado_externo` is left alone until the server
 * responds (it is social-wiring's own truth for `one-chat`, not something
 * this client can predict).
 */
export function useToggleAgent() {
  const qc = useQueryClient();

  return useMutation<Agent, unknown, { key: string; ativo: boolean }>({
    mutationFn: ({ key, ativo }) =>
      api.post<Agent>(`/api/agents/${key}/toggle`, { ativo }),
    onMutate: async ({ key, ativo }) => {
      await qc.cancelQueries({ queryKey: AGENTS_KEY });
      const previous = qc.getQueryData<AgentListResponse>(AGENTS_KEY);
      if (previous) {
        qc.setQueryData<AgentListResponse>(AGENTS_KEY, {
          ...previous,
          items: previous.items.map((a) => (a.key === key ? { ...a, ativo } : a)),
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      const ctx = context as { previous?: AgentListResponse } | undefined;
      if (ctx?.previous) qc.setQueryData(AGENTS_KEY, ctx.previous);
    },
    onSuccess: (updated) => {
      qc.setQueryData<AgentListResponse>(AGENTS_KEY, (prev) =>
        prev
          ? { ...prev, items: prev.items.map((a) => (a.key === updated.key ? updated : a)) }
          : prev,
      );
    },
  });
}
