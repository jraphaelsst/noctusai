/**
 * `GET /api/painel` — the agency panel behind the landing screen.
 *
 * See `app/routers/painel_router.py` for why this exists rather than a fix to
 * the YouTube dashboard: that surface genuinely IS a channel dashboard, and a
 * real-estate agency was landing on it.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

export interface PainelItem {
  atendimento_id: string;
  cliente_id: string | null;
  titulo: string | null;
  quando: string | null;
  tipo: string | null;
}

export interface Painel {
  /** Leads that arrived this week and are still in the first stage. */
  novos: number;
  /** Open deals nobody has touched in two weeks. */
  parados: number;
  /** Appointments booked in the next seven days. */
  agendamentos: number;
  /** Duplicate-review groups waiting on a decision. */
  revisao: number;
  /** Sum of `valor_negociado` over OPEN deals — money on the table now. */
  em_negociacao: number;
  proximos_agendamentos: PainelItem[];
  atendimentos_parados: PainelItem[];
}

export const PAINEL_KEY = ["painel"] as const;

/**
 * 🔴 `loading` gates on `isPending || isFetching`, never `isLoading` — under
 * TanStack v5 `isLoading` is false during a background refetch, so an empty
 * branch would render over data that already exists.
 */
export function usePainel() {
  const query = useQuery({
    queryKey: PAINEL_KEY,
    queryFn: () => api.get<Painel>("/api/painel"),
  });
  return { ...query, loading: query.isPending || query.isFetching };
}
