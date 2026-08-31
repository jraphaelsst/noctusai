import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { HomeworkAssignment } from '@/types';

const KEYS = {
  all: ['homework'] as const,
  list: (page: number, pageSize: number) => ['homework', 'list', page, pageSize] as const,
};

export function useHomeworkList(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: HomeworkAssignment[]; total: number }>({
    queryKey: KEYS.list(page, pageSize),
    queryFn: async () => {
      const res = await api.get(`/api/homework?page=${page}&page_size=${pageSize}`);
      return res;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateHomework() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      patient_id: string;
      titulo: string;
      descricao: string;
      data_limite?: string;
    }) => {
      return api.post('/api/homework', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Tarefa criada com sucesso');
    },
    onError: () => {
      toast.error('Erro ao criar tarefa');
    },
  });
}

export function useSubmitHomework() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, resposta_paciente }: { id: string; resposta_paciente: string }) => {
      return api.post(`/api/homework/${id}/submit`, { resposta_paciente });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Resposta enviada');
    },
    onError: () => {
      toast.error('Erro ao enviar resposta');
    },
  });
}

export function useReviewHomework() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, feedback_terapeuta }: { id: string; feedback_terapeuta: string }) => {
      return api.post(`/api/homework/${id}/review`, { feedback_terapeuta });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Feedback enviado');
    },
    onError: () => {
      toast.error('Erro ao enviar feedback');
    },
  });
}
