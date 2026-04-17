import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type { Transaction } from '@/types/financial';

interface TransactionFilters {
  status?: string;
  therapist_id?: string;
  clinic_id?: string;
  patient_id?: string;
  date_start?: string;
  date_end?: string;
}

const KEYS = {
  all: ['transactions'] as const,
  list: (filters?: TransactionFilters, page?: number, pageSize?: number) =>
    ['transactions', 'list', filters, page, pageSize] as const,
  detail: (id: string) => ['transactions', id] as const,
};

export function useTransactions(filters?: TransactionFilters, page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: Transaction[]; total: number }>({
    queryKey: KEYS.list(filters, page, pageSize),
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (filters?.status) params.set('status', filters.status);
      if (filters?.therapist_id) params.set('therapist_id', filters.therapist_id);
      if (filters?.clinic_id) params.set('clinic_id', filters.clinic_id);
      if (filters?.patient_id) params.set('patient_id', filters.patient_id);
      if (filters?.date_start) params.set('date_start', filters.date_start);
      if (filters?.date_end) params.set('date_end', filters.date_end);
      return api.get(`/api/transactions?${params}`);
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useTransaction(id?: string) {
  const { user } = useAuthStore();
  return useQuery<Transaction>({
    queryKey: KEYS.detail(id!),
    queryFn: async () => {
      const res = await api.get(`/api/transactions/${id}`);
      return res.data ?? res;
    },
    enabled: !!user && !!id,
    staleTime: 2 * 60 * 1000,
  });
}
