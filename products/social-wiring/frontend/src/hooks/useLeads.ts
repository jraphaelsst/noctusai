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

  const create = useMutation<Lead, unknown, LeadCreateInput>({
    mutationFn: async (body) => {
      const res = await api.post<SuccessEnvelope<Lead>>(BASE, body);
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const update = useMutation<Lead, unknown, { id: string; body: LeadUpdateInput }>({
    mutationFn: async ({ id, body }) => {
      const res = await api.patch<SuccessEnvelope<Lead>>(
        `${BASE}/${encodeURIComponent(id)}`,
        body,
      );
      return res.data;
    },
    onSuccess: invalidateFamily,
  });

  const remove = useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    onSuccess: invalidateFamily,
  });

  return { create, update, remove };
}
