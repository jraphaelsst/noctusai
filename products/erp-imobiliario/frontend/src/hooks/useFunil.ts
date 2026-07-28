import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { EtapaFunil } from '@/types/clientes';
import { ColunaNegociacoes, NegociacaoVenda } from '@/types/negociacoes';
import { ProcessoVenda } from '@/types/processos';
import { toast } from 'sonner';

/**
 * Funil hooks — RESHAPED (roadmap P1.5.4).
 *
 * The board's cards are NEGOCIAÇÕES, not clientes: one cliente can hold
 * several concurrent deals at different stages, which `clientes.etapa_atual`
 * (one stage per cliente) could not represent. Stage moves now hit
 * `/api/negociacoes-venda/{id}/mover-etapa`, which also writes the transition
 * to `erp.funil_movimentos` — the cliente-level endpoint never did.
 */

interface FiltrosFunil {
  busca?: string;
  responsavelId?: string;
  origem?: string;
  etapa?: EtapaFunil;
  incluirArquivados?: boolean;
  // `string`, not `Date`: `funilFiltrosStore` holds these as ISO strings, and
  // declaring `Date` here made every call site a type error (pre-existing —
  // invisible because `tsc --noEmit` on the solution-style tsconfig checks
  // zero files; see the P1.5.4 commit message).
  dataInicio?: string;
  dataFim?: string;
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
      return (result.data || []) as ColunaNegociacoes[];
    },
    enabled: !!user,
  });
}

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

interface MoverNegociacaoData {
  negociacao_id: string;
  para_etapa: EtapaFunil;
  motivo?: string;
  novo_indice?: number;
}

export function useMoverNegociacaoEtapa() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: MoverNegociacaoData) => {
      const result = await api.post(
        `/api/negociacoes-venda/${data.negociacao_id}/mover-etapa`,
        {
          para_etapa: data.para_etapa,
          motivo: data.motivo,
          novo_indice: data.novo_indice,
        },
      );
      return result.data as NegociacaoVenda;
    },
    onMutate: async (variables) => {
      // Optimistic update (UI only)
      await queryClient.cancelQueries({ queryKey: ['funil'] });
      // Match ALL ['funil', …filtros] entries, not the bare ['funil'] key —
      // the query key carries the active filters, so a bare getQueryData reads
      // an entry that is usually empty and the optimistic move appears to do
      // nothing until the refetch lands.
      const previousData = queryClient.getQueriesData({ queryKey: ['funil'] });

      queryClient.setQueriesData(
        { queryKey: ['funil'] },
        (old: ColunaNegociacoes[] | undefined) => {
          if (!old) return old;
          const negociacao = old
            .flatMap((c) => c.cards)
            .find((n) => n.id === variables.negociacao_id);
          if (!negociacao) return old;

          const novasColunas = old.map((coluna) => ({
            ...coluna,
            cards: coluna.cards.filter((n) => n.id !== variables.negociacao_id),
          }));
          const colunaDestino = novasColunas.find((c) => c.etapa === variables.para_etapa);
          if (colunaDestino) {
            const atualizada = { ...negociacao, etapa: variables.para_etapa };
            if (variables.novo_indice !== undefined) {
              colunaDestino.cards.splice(variables.novo_indice, 0, atualizada);
            } else {
              colunaDestino.cards.unshift(atualizada);
            }
          }
          // Recompute on EVERY column — the card left one and joined another,
          // so the source column's count changed too.
          return novasColunas.map((coluna) => ({
            ...coluna,
            total: coluna.cards.length,
            valorTotal: coluna.cards.reduce(
              (sum, n) => sum + Number(n.valor_estimado || 0),
              0,
            ),
          }));
        },
      );

      return { previousData };
    },
    onError: (error: Error, _variables, context) => {
      context?.previousData?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data);
      });
      toast.error('Erro ao mover negociação', { description: error.message });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['funil'] });
      queryClient.invalidateQueries({ queryKey: ['clientes'] });
    },
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
