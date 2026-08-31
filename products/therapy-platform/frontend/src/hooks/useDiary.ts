import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { JournalEntry } from '@/types';

const KEYS = {
  all: ['diary'] as const,
  list: (page: number, pageSize: number) => ['diary', 'list', page, pageSize] as const,
};

export function useJournalEntries(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: JournalEntry[]; total: number }>({
    queryKey: KEYS.list(page, pageSize),
    queryFn: async () => {
      const res = await api.get(`/api/diary?page=${page}&page_size=${pageSize}`);
      return res;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateJournalEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      titulo?: string;
      conteudo: string;
      is_shared_with_therapist?: boolean;
    }) => {
      return api.post('/api/diary', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Entrada do diario salva');
    },
    onError: () => {
      toast.error('Erro ao salvar entrada');
    },
  });
}

export function useUpdateJournalEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: {
      id: string;
      titulo?: string;
      conteudo?: string;
      is_shared_with_therapist?: boolean;
    }) => {
      return api.patch(`/api/diary/${id}`, data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Entrada atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar entrada');
    },
  });
}

export function useDeleteJournalEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete(`/api/diary/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Entrada removida');
    },
    onError: () => {
      toast.error('Erro ao remover entrada');
    },
  });
}
