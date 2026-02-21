import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { Atividade, TipoAtividade } from '@/types/clientes';
import { useAuthStore } from '@/store/authStore';

export function useAtividades(clienteId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['atividades', clienteId],
    queryFn: async () => {
      if (!clienteId) return [];

      const { data, error } = await supabase
        .from('atividades')
        .select(`
          *,
          usuario:profiles!atividades_usuario_id_fkey(id, nome, email)
        `)
        .eq('cliente_id', clienteId)
        .order('data_execucao', { ascending: false });

      if (error) throw error;
      return data as Atividade[];
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
      const { data: result, error } = await supabase.functions.invoke('registrar-atividade', {
        body: data,
      });

      if (error) throw error;

      // Registrar ação
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        supabase.from("user_actions_log").insert({
          usuario_id: user.id,
          tipo_acao: 'criar',
          tipo_entidade: 'atividade',
          entidade_id: result.atividade?.id,
          descricao: `Registrou atividade do tipo ${data.tipo}`,
          detalhes: { tipo: data.tipo, cliente_id: data.cliente_id }
        }).then();
      }

      return result;
    },
    onSuccess: (result, variables) => {
      queryClient.setQueryData(
        ['atividades', variables.cliente_id],
        result.atividades
      );
      toast.success('Atividade registrada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao registrar atividade', {
        description: error.message,
      });
    },
  });
}
