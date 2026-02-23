import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { Atividade, TipoAtividade } from '@/types/clientes';
import { useAuthStore } from '@/store/authStore';

export function useAtividades(clienteId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['atividades', clienteId],
    queryFn: async () => {
      if (!clienteId) return [];
      const result = await api.get('/api/atividades', { cliente_id: clienteId });
      return (result.data || []) as Atividade[];
    },
    enabled: !!user && !!clienteId,
  });
}

interface CreateAtividadeData {
  cliente_id: string;
  tipo: TipoAtividade;
  descricao: string;
  data_execucao?: string;
}

export function useCreateAtividade() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateAtividadeData) => {
      // Action logging happens server-side now
      const result = await api.post('/api/atividades', data);
      return result.data;
    },
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['atividades', variables.cliente_id] });
      toast.success('Atividade registrada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar atividade', { description: error.message });
    },
  });
}
