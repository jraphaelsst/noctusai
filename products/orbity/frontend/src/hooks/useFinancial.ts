/**
 * Financial hooks for Orbity -- the layer over the seed finance + contracts organs.
 *
 * The money model (contracts, receivables, payables, settlements, DRE, cash flow) is the organs': their own hooks
 * (`createFinanceHooks` / `createContractsHooks`, built in `pages/Financeiro.tsx`) talk to /api/finance and
 * /api/contracts. What lives here is only what the organs do not know:
 *   - the month summary that honours the "charge kept after the client was inactivated" rule;
 *   - the gateway state of every charge (queued / generating / retrying / generated / failed / skipped + last error);
 *   - re-queueing a skipped/failed charge, and an extra (one-off) charge for a client.
 *
 * Loading states: callers compute `showSkeleton = isPending && !data` and `isRefreshing = isFetching && !!data`
 * (never `isLoading`: it is false mid-refetch, so an empty branch would lie over data that exists).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { toast } from "sonner";
import { financeKeys } from "@noctusai/lib";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";

// ---------------------------------------------------------------------------
// Types (mirror backend schemas/financial.py)
// ---------------------------------------------------------------------------

export type GenerationStatus = "queued" | "generating" | "retrying" | "generated" | "failed" | "skipped";
export type EntryStatus = "open" | "partial" | "paid" | "cancelled";

export interface MonthlyCashFlow {
  reference_month: string;
  paid_revenues: number;
  paid_expenses: number;
  net: number;
  pending_revenues: number;
  overdue_revenues: number;
}

export interface Charge {
  entry_id: string;
  client_id: string | null;
  client_name: string | null;
  contract_id: string | null;
  description: string;
  due_date: string;
  amount_cents: number;
  settled_cents: number;
  entry_status: EntryStatus;
  overdue: boolean;
  generation_status: GenerationStatus;
  generation_attempts: number;
  last_error: string | null;
  next_attempt_at: string | null;
  gateway: string | null;
  billing_method: string | null;
  external_id: string | null;
  invoice_url: string | null;
  pix_payload: string | null;
  preserved_after_deactivation: boolean;
  gateway_cancel_status: "pending" | "done" | "failed" | null;
  gateway_cancel_error: string | null;
}

export interface ChargeList {
  items: Charge[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChargeFilters {
  client_id?: string;
  generation_status?: GenerationStatus;
  page?: number;
  page_size?: number;
}

export interface ExtraChargeCreate {
  client_id: string;
  description: string;
  amount_cents: number;
  due_date: string;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Month summary. `month` is YYYY-MM; the backend expects the first day (YYYY-MM-01).
 * `placeholderData` keeps the previous month's totals on screen during a month change.
 */
export function useCashFlow(month: string) {
  const { user } = useAuthStore();
  const monthParam = month.length === 7 ? `${month}-01` : month;

  return useQuery({
    queryKey: ["financial-cash-flow", month],
    queryFn: async () => api.get<MonthlyCashFlow>(`/api/financial/cash-flow/${monthParam}`),
    placeholderData: (prev) => prev,
    enabled: !!user && !!month,
    staleTime: 2 * 60 * 1000,
  });
}

/** Is a payment gateway configured for this org? (false => charges stay plain receivables.) */
export function useGatewayStatus() {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["financial-gateway"],
    queryFn: async () => api.get<{ gateway: string; configured: boolean }>("/api/financial/gateway"),
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

/**
 * Charges with their gateway state. Polls every 15s while any charge on screen is still moving
 * (queued / generating / retrying) so the status banner follows the worker without a manual refresh.
 */
export function useCharges(filters?: ChargeFilters) {
  const { user } = useAuthStore();
  return useQuery({
    queryKey: ["financial-charges", filters],
    queryFn: async () =>
      api.get<ChargeList>("/api/financial/charges", {
        client_id: filters?.client_id,
        generation_status: filters?.generation_status,
        page: filters?.page ?? 1,
        page_size: filters?.page_size ?? 50,
      }),
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 30 * 1000,
    refetchInterval: (query) =>
      query.state.data?.items.some((c) => ["queued", "generating", "retrying"].includes(c.generation_status)) ? 15_000 : false,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

// Settle also refreshes what the charge change moves but the client cannot compute:
// the month cash-flow summary and the finance organ's receivables/DRE views.
const DERIVED = [["financial-cash-flow"], [...financeKeys.all]];

/** Send a skipped/failed charge to the gateway (after the operator fixed what blocked it). */
export function useRequeueCharge() {
  return useCacheWriteMutation<Charge, string>({
    mutationFn: async (entryId) => api.post<Charge>(`/api/financial/charges/${entryId}/generate`, {}),
    targets: (entryId) => [
      {
        queryKey: ["financial-charges"],
        match: "prefix",
        commit: (old: ChargeList | undefined, saved) => pageOps.replace(old, entryId, saved, "entry_id"),
      },
    ],
    invalidate: DERIVED,
    onSuccess: () => {
      toast.success("Cobrança enviada para a fila do gateway");
    },
    onError: (error: Error) => {
      toast.error("Não foi possível enviar a cobrança ao gateway", { description: error.message });
    },
  });
}

export function useCreateExtraCharge() {
  const queryClient = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — charges are cached per generation_status filter + page; whether the new (queued) charge belongs in a given cached window is the server's call
    mutationFn: async (data: ExtraChargeCreate) => api.post<Charge>("/api/financial/charges", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-charges"] });
      for (const queryKey of DERIVED) queryClient.invalidateQueries({ queryKey });
      toast.success("Cobrança criada");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar a cobrança", { description: error.message });
    },
  });
}
