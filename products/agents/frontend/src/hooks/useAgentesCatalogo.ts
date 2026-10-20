/**
 * Catálogo de agentes — `GET /api/agents/catalogo`.
 *
 * Org tier returns display-level fields only. `ferramentas` / `versao` are
 * platform-admin extras: OPTIONAL, rendered only when the server sends them;
 * this client never requests or infers them.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface AgenteCatalogo {
  key: string;
  nome: string;
  papel: string;
  descricao_publica: string;
  runtime: string;
  capacidades: string[];
  ferramentas?: string[];
  versao?: string | number;
}

const CATALOGO_KEY = ["agents", "catalogo"] as const;

export function useAgentesCatalogo() {
  const query = useQuery<AgenteCatalogo[]>({
    queryKey: CATALOGO_KEY,
    queryFn: () => api.get<AgenteCatalogo[]>("/api/agents/catalogo"),
    placeholderData: (prev) => prev,
  });

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    refetch: query.refetch,
  };
}
