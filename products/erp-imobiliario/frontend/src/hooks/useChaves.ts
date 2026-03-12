import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';

export interface Chave {
  id: string;
  org_id: string;
  imovel_id: string;
  codigo: string;
  descricao?: string | null;
  status: 'disponivel' | 'emprestada' | 'perdida';
  ultima_retirada_por?: string | null;
  ultima_retirada_nome?: string | null;
  ultima_retirada_em?: string | null;
  ultima_devolucao_em?: string | null;
  observacoes?: string | null;
  created_at: string;
  historico?: ChaveHistorico[];
}

export interface ChaveHistorico {
  id: string;
  chave_id: string;
  acao: 'retirada' | 'devolucao';
  corretor_id: string;
  corretor_nome: string;
  motivo?: string | null;
  created_at: string;
}

export function useChaves(filters?: { status?: string; imovel_id?: string }) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['chaves', filters],
    queryFn: async () => {
      const result = await api.get('/api/chaves', filters);
      return (result.data || []) as Chave[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useChave(id?: string) {
  return useQuery({
    queryKey: ['chave', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/chaves/${id}`);
      return result.data as Chave;
    },
    enabled: !!id,
  });
}

export function useCreateChave() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: { imovel_id: string; codigo: string; descricao?: string; observacoes?: string }) => {
      const result = await api.post('/api/chaves', data);
      return result.data as Chave;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chaves'] });
      toast.success('Chave registrada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar chave', { description: error.message });
    },
  });
}

export function useUpdateChave() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Chave> & { id: string }) => {
      const result = await api.patch(`/api/chaves/${id}`, data);
      return result.data as Chave;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chaves'] });
      toast.success('Chave atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar chave', { description: error.message });
    },
  });
}

export function useRetirarChave() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, corretor_nome, motivo }: { id: string; corretor_nome: string; motivo?: string }) => {
      const result = await api.post(`/api/chaves/${id}/retirada`, { corretor_nome, motivo });
      return result.data as Chave;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chaves'] });
      queryClient.invalidateQueries({ queryKey: ['chave'] });
      toast.success('Chave retirada registrada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar retirada', { description: error.message });
    },
  });
}

export function useDevolverChave() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, corretor_nome, motivo }: { id: string; corretor_nome: string; motivo?: string }) => {
      const result = await api.post(`/api/chaves/${id}/devolucao`, { corretor_nome, motivo });
      return result.data as Chave;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chaves'] });
      queryClient.invalidateQueries({ queryKey: ['chave'] });
      toast.success('Devolução registrada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar devolução', { description: error.message });
    },
  });
}

export function useChaveHistorico(chaveId?: string) {
  return useQuery({
    queryKey: ['chave-historico', chaveId],
    queryFn: async () => {
      if (!chaveId) return [];
      const result = await api.get(`/api/chaves/${chaveId}/historico`);
      return (result.data || []) as ChaveHistorico[];
    },
    enabled: !!chaveId,
  });
}
