/**
 * Leads hooks — `/api/leads` (the fact-table CRUD + list, "Base de Leads"
 * subtab). Built on @tanstack/react-query v5; `queryFn` never returns
 * undefined. Every list/detail query accepts the shared `LeadsFilters`
 * (see `useLeadsFilters.ts`) — the same filter set every subtab reads.
 *
 * List envelope: paginated_response → { data: Lead[], pagination: {...} }.
 * Single item: success_response → { data: Lead }.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { FUNIL_PIPELINE_KEY } from "@/lib/funilKeys";
import {
  buildLeadsQueryParams,
  leadsFiltersQueryKey,
  type LeadsFilters,
} from "./useLeadsFilters";
import type { Lead, LeadCreateInput, LeadUpdateInput } from "@/pages/leads/types";
import type { PaginationMeta } from "./useContacts";

// ─── Types ───────────────────────────────────────────────────────────────────

export type LeadsSort =
  | "data_entrada"
  | "cliente_nome"
  | "origem"
  | "corretor"
  | "created_at";
export type LeadsOrder = "asc" | "desc";

export interface ListLeadsParams {
  page?: number;
  pageSize?: number;
  sort?: LeadsSort;
  order?: LeadsOrder;
}

export interface LeadsPage {
  data: Lead[];
  pagination: PaginationMeta;
}

interface SuccessEnvelope<T> {
  data: T;
}

const BASE = "/api/leads";
const FAMILY_KEY = ["leads", "list"] as const;
const DETAIL_KEY = ["leads", "detail"] as const;

// ─── Queries ─────────────────────────────────────────────────────────────────

export function useLeadsList(filters: LeadsFilters, params?: ListLeadsParams) {
  const search = buildLeadsQueryParams(filters);
  if (params?.page != null) search.set("page", String(params.page));
  if (params?.pageSize != null) search.set("page_size", String(params.pageSize));
  if (params?.sort) search.set("sort", params.sort);
  if (params?.order) search.set("order", params.order);
  const qs = search.toString();

  return useQuery<LeadsPage>({
    queryKey: [...FAMILY_KEY, leadsFiltersQueryKey(filters), params],
    queryFn: () => api.get<LeadsPage>(qs ? `${BASE}?${qs}` : BASE),
    // `filters` + `params` (page/pageSize/sort/order) drive the queryKey —
    // every filter tweak, page turn, or sort click swaps to a fresh key
    // with no cached data. Keep the previous page on screen instead of
    // blanking the whole table for one round trip.
    placeholderData: (prev) => prev,
  });
}

export function useLead(id: string | null) {
  return useQuery<Lead>({
    queryKey: [...DETAIL_KEY, id],
    queryFn: async () => {
      const res = await api.get<SuccessEnvelope<Lead>>(`${BASE}/${encodeURIComponent(id as string)}`);
      return res.data;
    },
    enabled: !!id,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────────────

export function useLeadMutations() {
  const qc = useQueryClient();
  const invalidateFamily = () => qc.invalidateQueries({ queryKey: ["leads"] });

  const create = useMutation<Lead, unknown, LeadCreateInput>({ // noc-allow: invalidate-only — lists are paginated, filtered and server-sorted, and a DB trigger also creates the funil card; placement and the board are the server's call
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<Lead>>(BASE, body);
      return res.data;
    },
    // A new lead gets its funil card from a DB trigger, so the Funil board (and its
    // stage totals) must refetch too — otherwise the card only appears once a search
    // changes the board's query key (prod, 2026-10-21).
    // Not returned (fire-and-forget): the create has succeeded, so the dialog must not
    // wait on the board refetch.
    onSuccess: () => {
      void invalidateFamily();
      void qc.invalidateQueries({ queryKey: [FUNIL_PIPELINE_KEY] });
      void qc.invalidateQueries({ queryKey: [`${FUNIL_PIPELINE_KEY}-stages`] });
    },
  });

  // `["leads","list",filters,params]` pages are reached by the prefix target; the detail by its key.
  const update = useCacheWriteMutation<Lead, { id: string; body: LeadUpdateInput }>({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<Lead>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    targets: ({ id, body }) => [
      {
        queryKey: FAMILY_KEY,
        match: "prefix",
        optimistic: (old: LeadsPage | undefined) => pageOps.patch(old, id, body),
        commit: (old: LeadsPage | undefined, saved) => pageOps.replace(old, saved.id, saved),
      },
      {
        queryKey: [...DETAIL_KEY, id],
        commit: (_old: Lead | undefined, saved) => saved,
      },
    ],
    // Analytics / funil views derived from the lead refresh in the background.
    invalidate: [["leads"]],
  });

  const remove = useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    targets: (id) => [
      {
        queryKey: FAMILY_KEY,
        match: "prefix",
        optimistic: (old: LeadsPage | undefined) => pageOps.remove(old, id),
      },
    ],
    invalidate: [["leads"]],
  });

  return { create, update, remove };
}
