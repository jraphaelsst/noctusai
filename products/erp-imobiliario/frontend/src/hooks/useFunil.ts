import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { NegociacaoVenda } from '@/types/negociacoes';
import { ProcessoVenda } from '@/types/processos';
import { toast } from 'sonner';

/**
 * Funil hooks — the product-specific remainder.
 *
 * The board query and the optimistic stage-move used to live here. Both are now
 * `funilPipeline` (`@/lib/pipelines`, built on `createPipelineHooks`), shared
 * with Processos de Venda — they were the same code twice.
 *
 * What stays here is genuinely Funil-specific: the accept-proposal seam between
 * the two boards, archiving, and reading one cliente's open deals.
 */

/**
 * The OPEN deals belonging to one cliente.
 *
 * Exists because `clientes.etapa_atual` stopped being the source of truth at
 * P1.5.4: any surface that used to read or write it (the cliente detail page)
 * must go through the deal instead, or it silently edits a field nothing
 * renders.
 */
export function useNegociacoesDoCliente(clienteId?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['negociacoes-venda', 'cliente', clienteId],
    queryFn: async () => {
      const result = await api.get('/api/negociacoes-venda', {
        cliente_id: clienteId,
        status: 'aberta',
      });
      return (result.data || []) as NegociacaoVenda[];
    },
    enabled: !!user && !!clienteId,
  });
}

interface AceitarPropostaResult {
  negociacao: NegociacaoVenda;
  processo: ProcessoVenda;
  /** True when the deal was already in execution — a repeat click, not an error. */
  already_accepted: boolean;
}

/**
 * The seam between the two boards: accept the proposal, close the negociação,
 * open its processo de venda. The card leaves the Funil entirely.
 */
export function useAceitarProposta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (negociacaoId: string) => {
      const result = await api.post(
        `/api/negociacoes-venda/${negociacaoId}/aceitar-proposta`,
      );
      return result.data as AceitarPropostaResult;
    },
    onSuccess: (data) => {
      if (data.already_accepted) {
        toast.info('Esta proposta já havia sido aceita', {
          description: 'O processo de venda já existe.',
        });
      } else {
        toast.success('Proposta aceita', {
          description: 'A negociação foi movida para Processos de Venda.',
        });
      }
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      queryClient.invalidateQueries({ queryKey: ['processos-venda'] });
    },
    onError: (error: Error) => {
      toast.error('Erro ao aceitar proposta', { description: error.message });
    },
  });
}

export function useArquivarNegociacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (negociacaoId: string) => {
      const result = await api.patch(`/api/negociacoes-venda/${negociacaoId}`, {
        arquivado: true,
      });
      return result.data as NegociacaoVenda;
    },
    onSuccess: () => {
      toast.success('Negociação arquivada');
      queryClient.invalidateQueries({ queryKey: ['funil'] });
    },
    onError: (error: Error) => {
      toast.error('Erro ao arquivar negociação', { description: error.message });
    },
  });
}
