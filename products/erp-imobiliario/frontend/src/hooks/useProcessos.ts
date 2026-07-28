import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import { ColunaProcessos, EtapaProcesso, ProcessoVenda } from '@/types/processos';

interface FiltrosProcessos {
  busca?: string;
  corretorId?: string;
  etapa?: EtapaProcesso;
  incluirArquivados?: boolean;
}

export function useProcessos(filtros?: FiltrosProcessos) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['processos-venda', filtros],
    queryFn: async () => {
      const result = await api.get('/api/processos-venda', {
        busca: filtros?.busca,
        corretor_id: filtros?.corretorId,
        etapa: filtros?.etapa,
        incluir_arquivados: filtros?.incluirArquivados || false,
      });
      // Never return undefined from a queryFn — TanStack treats it as an error
      // and the cache entry silently never populates.
      return (result.data || []) as ColunaProcessos[];
    },
    enabled: !!user,
  });
}

interface MoverProcessoData {
  processo_id: string;
  para_etapa: EtapaProcesso;
  novo_indice?: number;
}

export function useMoverProcessoEtapa() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: MoverProcessoData) => {
      const result = await api.post(
        `/api/processos-venda/${data.processo_id}/mover-etapa`,
        { para_etapa: data.para_etapa, novo_indice: data.novo_indice },
      );
      return result.data as ProcessoVenda;
    },
    onMutate: async (variables) => {
      // Optimistic move so the card lands under the cursor immediately.
      // Mirrors the Funil's optimistic shape — same board, same expectation.
      await queryClient.cancelQueries({ queryKey: ['processos-venda'] });
      const previousData = queryClient.getQueriesData({ queryKey: ['processos-venda'] });

      queryClient.setQueriesData(
        { queryKey: ['processos-venda'] },
        (old: ColunaProcessos[] | undefined) => {
          if (!old) return old;
          const processo = old
            .flatMap((c) => c.cards)
            .find((p) => p.id === variables.processo_id);
          if (!processo) return old;

          const novasColunas = old.map((coluna) => ({
            ...coluna,
            cards: coluna.cards.filter((p) => p.id !== variables.processo_id),
          }));
          const destino = novasColunas.find((c) => c.etapa === variables.para_etapa);
          if (destino) {
            const atualizado = { ...processo, etapa: variables.para_etapa };
            if (variables.novo_indice !== undefined) {
              destino.cards.splice(variables.novo_indice, 0, atualizado);
            } else {
              destino.cards.unshift(atualizado);
            }
          }
          // Recompute totals on EVERY column: the card left one and joined
          // another, so both counts changed.
          return novasColunas.map((coluna) => ({
            ...coluna,
            total: coluna.cards.length,
            valorTotal: coluna.cards.reduce((sum, p) => sum + Number(p.valor || 0), 0),
          }));
        },
      );

      return { previousData };
    },
    onError: (error: Error, _variables, context) => {
      context?.previousData?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data);
      });
      toast.error('Erro ao mover processo', { description: error.message });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['processos-venda'] });
    },
  });
}

export function useArquivarProcesso() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (processoId: string) => {
      const result = await api.post(`/api/processos-venda/${processoId}/arquivar`);
      return result.data as ProcessoVenda;
    },
    onSuccess: (processo) => {
      toast.success(processo.arquivado ? 'Processo arquivado' : 'Processo restaurado');
      queryClient.invalidateQueries({ queryKey: ['processos-venda'] });
    },
    onError: (error: Error) => {
      toast.error('Erro ao arquivar processo', { description: error.message });
    },
  });
}
