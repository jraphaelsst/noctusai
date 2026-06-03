/**
 * Financial hooks for Orbity — contracts, expenses, revenues, cash-flow.
 *
 * All list endpoints return { items, total, page, page_size }.
 * Single-resource endpoints (GET/PATCH/DELETE /:id) return the resource directly.
 * Cash-flow returns MonthlyCashFlowOut flat (no wrapper).
 *
 * Convention: one file per domain entity, TanStack Query throughout.
 * `api` is imported from `@/lib/api` (the local seam, not seed directly).
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuthStore } from "@noctusai/seed/infra";

// ---------------------------------------------------------------------------
// Domain types (mirrors backend schemas/financial.py)
// ---------------------------------------------------------------------------

export type ContractStatus = "active" | "paused" | "ended";
export type ExpenseRecurrence = "none" | "monthly" | "installment";
export type RevenueStatus = "pending" | "paid" | "overdue" | "canceled";

export interface Contract {
  id: string;
  org_id: string;
  client_id: string | null;
  title: string;
  monthly_value: number;
  billing_day: number;
  start_date: string;
  end_date: string | null;
  status: ContractStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Expense {
  id: string;
  org_id: string;
  category: string;
  description: string;
  amount: number;
  due_date: string;
  paid: boolean;
  paid_at: string | null;
  recurrence: ExpenseRecurrence;
  installments_total: number | null;
  installment_n: number | null;
  created_at: string;
  updated_at: string;
}

export interface Revenue {
  id: string;
  org_id: string;
  client_id: string | null;
  contract_id: string | null;
  reference_month: string;
  amount: number;
  status: RevenueStatus;
  due_date: string;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MonthlyCashFlow {
  reference_month: string;
  paid_revenues: number;
  paid_expenses: number;
  net: number;
  pending_revenues: number;
  overdue_revenues: number;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Contracts
// ---------------------------------------------------------------------------

export interface ContractFilters {
  status?: ContractStatus;
  client_id?: string;
  page?: number;
  page_size?: number;
}

export interface ContractCreate {
  title: string;
  monthly_value: number;
  billing_day?: number;
  start_date: string;
  end_date?: string;
  status?: ContractStatus;
  client_id?: string;
  notes?: string;
}

export interface ContractUpdate {
  id: string;
  title?: string;
  monthly_value?: number;
  billing_day?: number;
  start_date?: string;
  end_date?: string;
  status?: ContractStatus;
  client_id?: string;
  notes?: string;
}

export function useContracts(filters?: ContractFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["financial-contracts", filters],
    queryFn: async () => {
      const result = await api.get<ListResponse<Contract>>(
        "/api/financial/contracts",
        {
          status: filters?.status,
          client_id: filters?.client_id,
          page: filters?.page ?? 1,
          page_size: filters?.page_size ?? 50,
        },
      );
      return result;
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ContractCreate) => {
      return api.post<Contract>("/api/financial/contracts", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-contracts"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Contrato criado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar contrato", { description: error.message });
    },
  });
}

export function useUpdateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ContractUpdate) => {
      return api.patch<Contract>(`/api/financial/contracts/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-contracts"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Contrato atualizado com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar contrato", { description: error.message });
    },
  });
}

export function useDeleteContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/financial/contracts/${id}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-contracts"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Contrato removido com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover contrato", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Expenses
// ---------------------------------------------------------------------------

export interface ExpenseFilters {
  paid?: boolean;
  recurrence?: ExpenseRecurrence;
  page?: number;
  page_size?: number;
}

export interface ExpenseCreate {
  description: string;
  amount: number;
  due_date: string;
  category?: string;
  paid?: boolean;
  paid_at?: string;
  recurrence?: ExpenseRecurrence;
  installments_total?: number;
  installment_n?: number;
}

export interface ExpenseUpdate {
  id: string;
  description?: string;
  amount?: number;
  due_date?: string;
  category?: string;
  paid?: boolean;
  paid_at?: string;
  recurrence?: ExpenseRecurrence;
  installments_total?: number;
  installment_n?: number;
}

export function useExpenses(filters?: ExpenseFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["financial-expenses", filters],
    queryFn: async () => {
      const result = await api.get<ListResponse<Expense>>(
        "/api/financial/expenses",
        {
          paid: filters?.paid,
          recurrence: filters?.recurrence,
          page: filters?.page ?? 1,
          page_size: filters?.page_size ?? 50,
        },
      );
      return result;
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateExpense() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ExpenseCreate) => {
      return api.post<Expense>("/api/financial/expenses", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-expenses"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Despesa criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar despesa", { description: error.message });
    },
  });
}

export function useUpdateExpense() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ExpenseUpdate) => {
      return api.patch<Expense>(`/api/financial/expenses/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-expenses"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Despesa atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar despesa", { description: error.message });
    },
  });
}

export function useDeleteExpense() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/financial/expenses/${id}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-expenses"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Despesa removida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover despesa", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Revenues
// ---------------------------------------------------------------------------

export interface RevenueFilters {
  status?: RevenueStatus;
  client_id?: string;
  reference_month?: string;
  page?: number;
  page_size?: number;
}

export interface RevenueCreate {
  reference_month: string;
  amount: number;
  due_date: string;
  client_id?: string;
  contract_id?: string;
  status?: RevenueStatus;
  paid_at?: string;
}

export interface RevenueUpdate {
  id: string;
  reference_month?: string;
  amount?: number;
  due_date?: string;
  client_id?: string;
  contract_id?: string;
  status?: RevenueStatus;
  paid_at?: string;
}

export function useRevenues(filters?: RevenueFilters) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ["financial-revenues", filters],
    queryFn: async () => {
      const result = await api.get<ListResponse<Revenue>>(
        "/api/financial/revenues",
        {
          status: filters?.status,
          client_id: filters?.client_id,
          reference_month: filters?.reference_month,
          page: filters?.page ?? 1,
          page_size: filters?.page_size ?? 50,
        },
      );
      return result;
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useCreateRevenue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: RevenueCreate) => {
      return api.post<Revenue>("/api/financial/revenues", data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-revenues"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Receita criada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao criar receita", { description: error.message });
    },
  });
}

export function useUpdateRevenue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: RevenueUpdate) => {
      return api.patch<Revenue>(`/api/financial/revenues/${id}`, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-revenues"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Receita atualizada com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao atualizar receita", { description: error.message });
    },
  });
}

export function useDeleteRevenue() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete<{ ok: boolean; id: string }>(
        `/api/financial/revenues/${id}`,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["financial-revenues"] });
      queryClient.invalidateQueries({ queryKey: ["financial-cash-flow"] });
      toast.success("Receita removida com sucesso!");
    },
    onError: (error: Error) => {
      toast.error("Erro ao remover receita", { description: error.message });
    },
  });
}

// ---------------------------------------------------------------------------
// Cash-flow summary
// ---------------------------------------------------------------------------

/**
 * Fetch the monthly cash-flow summary.
 *
 * @param month - YYYY-MM string (e.g. "2026-06"). The hook converts it
 *   to YYYY-MM-01 (first day of month) as the backend expects.
 */
export function useCashFlow(month: string) {
  const { user } = useAuthStore();
  // Backend expects YYYY-MM-DD (first day of month)
  const monthParam = month.length === 7 ? `${month}-01` : month;

  return useQuery({
    queryKey: ["financial-cash-flow", month],
    queryFn: async () => {
      return api.get<MonthlyCashFlow>(
        `/api/financial/cash-flow/${monthParam}`,
      );
    },
    enabled: !!user && !!month,
    staleTime: 2 * 60 * 1000,
  });
}
