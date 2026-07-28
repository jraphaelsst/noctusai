/**
 * `createPipelineHooks(descriptor, api)` — the data layer for one board.
 *
 * WHAT THIS REPLACES
 * ------------------
 * The optimistic-move mutation was written three times in this codebase (ERP
 * Funil, ERP Processos, orbity Funil). All three were the same ~60 lines:
 * cancel in-flight queries, snapshot every matching cache entry, splice the
 * card out of its column and into the target at an index, recompute totals on
 * BOTH columns, roll back on error, invalidate on settle.
 *
 * Every one of those steps has a subtle failure mode that was rediscovered
 * independently each time — most notably `getQueriesData` vs `getQueryData`
 * (the key carries the active filters, so a bare read snapshots an empty entry
 * and the rollback silently restores nothing).
 *
 * Once is enough.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import type {
  PipelineApi,
  PipelineColumn,
  PipelineDescriptor,
  PipelineStage,
} from './types';

export interface MoveVariables {
  cardId: string;
  toStageId: string;
  toIndex?: number;
  motivo?: string;
}

export interface StageCreateInput {
  label: string;
  cor?: string;
  papel?: string | null;
}

export interface StageUpdateInput {
  label?: string;
  cor?: string;
  papel?: string | null;
  ativo?: boolean;
}

/** Unwrap `{ data }` envelopes without assuming one is present. */
function unwrap<T>(result: any, fallback: T): T {
  if (result == null) return fallback;
  if (Object.prototype.hasOwnProperty.call(result, 'data')) {
    return (result.data ?? fallback) as T;
  }
  return (result as T) ?? fallback;
}

export function createPipelineHooks<TCard>(
  descriptor: PipelineDescriptor<TCard>,
  api: PipelineApi,
) {
  const {
    queryKey,
    boardEndpoint,
    stagesEndpoint,
    moveEndpoint,
    getCardId,
    getCardValue,
    entityLabel,
    invalidateOnSettle = [],
  } = descriptor;

  const stagesKey = [`${queryKey}-stages`];

  function useStages(options?: { enabled?: boolean }) {
    return useQuery({
      queryKey: stagesKey,
      queryFn: async () => {
        if (!stagesEndpoint) return [] as PipelineStage[];
        const result = await api.get(stagesEndpoint);
        // Never return undefined from a queryFn — TanStack treats it as an
        // error and the cache entry silently never populates.
        return unwrap<PipelineStage[]>(result, []);
      },
      enabled: options?.enabled ?? true,
    });
  }

  function useBoard(filtros?: Record<string, any>, options?: { enabled?: boolean }) {
    return useQuery({
      queryKey: [queryKey, filtros ?? {}],
      queryFn: async () => {
        const result = await api.get(boardEndpoint, filtros);
        return unwrap<PipelineColumn<TCard>[]>(result, []);
      },
      enabled: options?.enabled ?? true,
    });
  }

  function useMoveCard() {
    const queryClient = useQueryClient();

    return useMutation({
      mutationFn: async (vars: MoveVariables) => {
        const result = await api.post(`${moveEndpoint}/${vars.cardId}/mover-etapa`, {
          para_etapa_id: vars.toStageId,
          novo_indice: vars.toIndex,
          motivo: vars.motivo,
        });
        return unwrap<TCard | null>(result, null);
      },

      onMutate: async (vars) => {
        // Optimistic move so the card lands under the cursor immediately.
        await queryClient.cancelQueries({ queryKey: [queryKey] });

        // getQueriesData, NOT getQueryData: the key carries the active filters
        // (`[queryKey, filtros]`), so reading the bare key returns an entry
        // that is usually empty — the optimistic move would appear to do
        // nothing until the refetch landed, and the rollback would restore a
        // snapshot of nothing.
        const previous = queryClient.getQueriesData({ queryKey: [queryKey] });

        queryClient.setQueriesData(
          { queryKey: [queryKey] },
          (old: PipelineColumn<TCard>[] | undefined) => {
            if (!old) return old;

            const card = old
              .flatMap((c) => c.cards)
              .find((c) => getCardId(c) === vars.cardId);
            if (!card) return old;

            const withoutCard = old.map((coluna) => ({
              ...coluna,
              cards: coluna.cards.filter((c) => getCardId(c) !== vars.cardId),
            }));

            const destino = withoutCard.find((c) => c.etapa === vars.toStageId);
            if (destino) {
              if (vars.toIndex !== undefined) {
                destino.cards.splice(vars.toIndex, 0, card);
              } else {
                destino.cards.unshift(card);
              }
            }

            // Recompute on EVERY column: the card left one and joined another,
            // so the source column's count and total changed too.
            return withoutCard.map((coluna) => ({
              ...coluna,
              total: coluna.cards.length,
              valorTotal: coluna.cards.reduce(
                (sum, c) => sum + Number(getCardValue(c) || 0),
                0,
              ),
            }));
          },
        );

        return { previous };
      },

      onError: (error: Error, _vars, context) => {
        context?.previous?.forEach(([key, data]) => {
          queryClient.setQueryData(key, data);
        });
        toast.error(`Erro ao mover ${entityLabel}`, { description: error.message });
      },

      onSettled: () => {
        queryClient.invalidateQueries({ queryKey: [queryKey] });
        invalidateOnSettle.forEach((k) =>
          queryClient.invalidateQueries({ queryKey: [k] }),
        );
      },
    });
  }

  // ---- Stage CRUD -------------------------------------------------------

  /**
   * Invalidate the board too, not just the stage list.
   *
   * A rename changes what every COLUMN HEADER says, and column definitions
   * arrive with the board payload. Refreshing only the stage list leaves the
   * board rendering the old label until something else happens to refetch it,
   * which reads as "the rename didn't work".
   */
  function useStageRefresh() {
    const queryClient = useQueryClient();
    return () => {
      queryClient.invalidateQueries({ queryKey: stagesKey });
      queryClient.invalidateQueries({ queryKey: [queryKey] });
    };
  }

  function useCreateStage() {
    const refresh = useStageRefresh();
    return useMutation({
      mutationFn: async (input: StageCreateInput) => {
        const result = await api.post(stagesEndpoint!, input);
        return unwrap<PipelineStage | null>(result, null);
      },
      onSuccess: (stage) => {
        toast.success(`Etapa "${stage?.label ?? ''}" criada`);
        refresh();
      },
      onError: (error: Error) =>
        toast.error('Erro ao criar etapa', { description: error.message }),
    });
  }

  function useUpdateStage() {
    const refresh = useStageRefresh();
    return useMutation({
      mutationFn: async (vars: { id: string; input: StageUpdateInput }) => {
        const result = await api.patch(`${stagesEndpoint}/${vars.id}`, vars.input);
        return unwrap<PipelineStage | null>(result, null);
      },
      onSuccess: (stage) => {
        toast.success(`Etapa "${stage?.label ?? ''}" atualizada`);
        refresh();
      },
      onError: (error: Error) =>
        toast.error('Erro ao atualizar etapa', { description: error.message }),
    });
  }

  function useDeleteStage() {
    const refresh = useStageRefresh();
    return useMutation({
      mutationFn: async (vars: { id: string; reassignTo?: string }) => {
        const result = await api.delete(
          `${stagesEndpoint}/${vars.id}`,
          vars.reassignTo ? { reassign_to: vars.reassignTo } : undefined,
        );
        return unwrap<{ cards_movidos?: number } | null>(result, null);
      },
      onSuccess: (result) => {
        const moved = result?.cards_movidos ?? 0;
        toast.success(
          moved
            ? `Etapa excluída — ${moved} ${entityLabel}${moved === 1 ? '' : 's'} movida${
                moved === 1 ? '' : 's'
              }`
            : 'Etapa excluída',
        );
        refresh();
      },
      onError: (error: Error) =>
        toast.error('Erro ao excluir etapa', { description: error.message }),
    });
  }

  function useReorderStages() {
    const refresh = useStageRefresh();
    return useMutation({
      mutationFn: async (ordem: string[]) => {
        const result = await api.post(`${stagesEndpoint}/reordenar`, { ordem });
        return unwrap<PipelineStage[]>(result, []);
      },
      onSuccess: () => {
        toast.success('Ordem das etapas atualizada');
        refresh();
      },
      onError: (error: Error) =>
        toast.error('Erro ao reordenar etapas', { description: error.message }),
    });
  }

  return {
    descriptor,
    useBoard,
    useStages,
    useMoveCard,
    useCreateStage,
    useUpdateStage,
    useDeleteStage,
    useReorderStages,
  };
}

export type PipelineHooks<TCard> = ReturnType<typeof createPipelineHooks<TCard>>;
