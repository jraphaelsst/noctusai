import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import { ProcessoVenda } from '@/types/processos';

/**
 * Processos hooks — the product-specific remainder.
 *
 * The board query and the optimistic stage-move moved to `processosPipeline`
 * (`@/lib/pipelines`), shared with the Funil. Archiving stays: it is specific
 * to this board, where the terminal stage would otherwise grow without bound.
 */

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
