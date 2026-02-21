import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { Cliente, ColunaFunil, EtapaFunil } from '@/types/clientes';
import { useAuthStore } from '@/store/authStore';
import { useIsAdmin } from './useUserRole';

interface FiltrosFunil {
  busca?: string;
  responsavelId?: string;
  origem?: string;
  etapa?: EtapaFunil;
  incluirArquivados?: boolean;
  dataInicio?: Date;
  dataFim?: Date;
}

const ETAPAS: EtapaFunil[] = ['qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado'];

export function useFunil(filtros?: FiltrosFunil) {
  const { user } = useAuthStore();
  const { isAdmin } = useIsAdmin();

  return useQuery({
    queryKey: ['funil', filtros, user?.id],
    queryFn: async () => {
      if (!user) return [];

      let query = supabase
        .from('clientes')
        .select(`
          *,
          usuario:profiles!clientes_usuario_id_fkey(id, nome, email)
        `)
        .order('kanban_pos', { ascending: true });

      // Aplicar filtros de acesso
      if (!isAdmin && filtros?.responsavelId !== 'todos') {
        query = query.eq('usuario_id', user.id);
      } else if (filtros?.responsavelId && filtros.responsavelId !== 'todos') {
        query = query.eq('usuario_id', filtros.responsavelId);
      }

      if (!filtros?.incluirArquivados) {
        query = query.eq('arquivado', false);
      }

      if (filtros?.etapa) {
        query = query.eq('etapa_atual', filtros.etapa);
      }

      if (filtros?.origem && filtros.origem !== 'todas') {
        query = query.eq('origem', filtros.origem);
      }

      if (filtros?.dataInicio) {
        query = query.gte('created_at', filtros.dataInicio.toISOString());
      }

      if (filtros?.dataFim) {
        query = query.lte('created_at', filtros.dataFim.toISOString());
      }

      const { data, error } = await query;

      if (error) throw error;

      let clientes = data as Cliente[];

      // Filtro de busca
      if (filtros?.busca) {
        const busca = filtros.busca.toLowerCase();
        clientes = clientes.filter(
          (c) =>
            c.nome.toLowerCase().includes(busca) ||
            c.email?.toLowerCase().includes(busca) ||
            c.telefone?.includes(busca)
        );
      }

      // Agrupar por etapa
      const colunas: ColunaFunil[] = ETAPAS.map((etapa) => {
        const cards = clientes
          .filter((c) => c.etapa_atual === etapa)
          .sort((a, b) => a.kanban_pos - b.kanban_pos);

        return {
          etapa,
          total: cards.length,
          valorTotal: cards.reduce((sum, c) => sum + Number(c.valor_estimado || 0), 0),
          cards,
        };
      });

      return colunas;
    },
    enabled: !!user,
  });
}

interface MoverClienteData {
  cliente_id: string;
  para_etapa: EtapaFunil;
  motivo?: string;
  novo_indice?: number;
}

export function useMoverClienteEtapa() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: MoverClienteData) => {
      const { data: result, error } = await supabase.functions.invoke('mover-cliente-etapa', {
        body: data,
      });

      if (error) throw error;
      return result.data as Cliente;
    },
    onMutate: async (variables) => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ['funil'] });
      const previousData = queryClient.getQueryData(['funil']);

      queryClient.setQueryData(['funil'], (old: ColunaFunil[] | undefined) => {
        if (!old) return old;

        // Encontrar o cliente e movê-lo
        const novasColunas = old.map((coluna) => ({
          ...coluna,
          cards: coluna.cards.filter((c) => c.id !== variables.cliente_id),
        }));

        // Encontrar o cliente
        const cliente = old
          .flatMap((c) => c.cards)
          .find((c) => c.id === variables.cliente_id);

        if (cliente) {
          const colunaDestino = novasColunas.find((c) => c.etapa === variables.para_etapa);
          if (colunaDestino) {
            const clienteAtualizado = {
              ...cliente,
              etapa_atual: variables.para_etapa,
            };

            if (variables.novo_indice !== undefined) {
              colunaDestino.cards.splice(variables.novo_indice, 0, clienteAtualizado);
            } else {
              colunaDestino.cards.unshift(clienteAtualizado);
            }

            colunaDestino.total = colunaDestino.cards.length;
            colunaDestino.valorTotal = colunaDestino.cards.reduce(
              (sum, c) => sum + Number(c.valor_estimado || 0),
              0
            );
          }
        }

        return novasColunas;
      });

      return { previousData };
    },
    onError: (error: Error, variables, context) => {
      // Rollback
      if (context?.previousData) {
        queryClient.setQueryData(['funil'], context.previousData);
      }
      toast.error('Erro ao mover cliente', {
        description: error.message,
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
    },
  });
}
