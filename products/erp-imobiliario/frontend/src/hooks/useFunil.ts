import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { ColunaFunil, EtapaFunil, Cliente } from '@/types/clientes';
import { toast } from 'sonner';

interface FiltrosFunil {
  busca?: string;
  responsavelId?: string;
  origem?: string;
  etapa?: EtapaFunil;
  incluirArquivados?: boolean;
  dataInicio?: Date;
  dataFim?: Date;
}

export function useFunil(filtros?: FiltrosFunil) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['funil', filtros],
    queryFn: async () => {
      const result = await api.get('/api/funil', {
        busca: filtros?.busca,
        responsavel_id: filtros?.responsavelId,
        origem: filtros?.origem,
        etapa: filtros?.etapa,
        incluir_arquivados: filtros?.incluirArquivados || false,
      });
      return (result.data || []) as ColunaFunil[];
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
      const result = await api.post(`/api/clientes/${data.cliente_id}/mover-etapa`, {
        para_etapa: data.para_etapa,
        motivo: data.motivo,
        novo_indice: data.novo_indice,
      });
      return result.data as Cliente;
    },
    onMutate: async (variables) => {
      // Optimistic update (UI only)
      await queryClient.cancelQueries({ queryKey: ['funil'] });
      const previousData = queryClient.getQueryData(['funil']);

      queryClient.setQueryData(['funil'], (old: ColunaFunil[] | undefined) => {
        if (!old) return old;
        const novasColunas = old.map((coluna) => ({
          ...coluna,
          cards: coluna.cards.filter((c) => c.id !== variables.cliente_id),
        }));
        const cliente = old.flatMap((c) => c.cards).find((c) => c.id === variables.cliente_id);
        if (cliente) {
          const colunaDestino = novasColunas.find((c) => c.etapa === variables.para_etapa);
          if (colunaDestino) {
            const clienteAtualizado = { ...cliente, etapa_atual: variables.para_etapa };
            if (variables.novo_indice !== undefined) {
              colunaDestino.cards.splice(variables.novo_indice, 0, clienteAtualizado);
            } else {
              colunaDestino.cards.unshift(clienteAtualizado);
            }
            colunaDestino.total = colunaDestino.cards.length;
            colunaDestino.valorTotal = colunaDestino.cards.reduce(
              (sum, c) => sum + Number(c.valor_estimado || 0), 0
            );
          }
        }
        return novasColunas;
      });

      return { previousData };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['funil'], context.previousData);
      }
      toast.error('Erro ao mover cliente', { description: error.message });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
    },
  });
}
