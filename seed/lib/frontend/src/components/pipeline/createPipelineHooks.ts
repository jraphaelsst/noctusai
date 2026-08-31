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
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
      // The query key is keyed on `filtros`, so a filter change is a KEY
      // change, not a background refetch of the same key — TanStack treats
      // it as a brand-new query and `data` goes `undefined` for one tick.
      // Without this, `PipelineBoard` blanks to its loading/empty state on
      // every filter edit (compounding the Category-A unmount bug above:
      // even with `KanbanBoard`'s `columns.length === 0` guard, a genuine
      // key change makes `columns` genuinely empty for that tick).
      // `keepPreviousData` carries the OLD key's rows forward until the new
      // key's response lands, so the board never blanks on a filter change.
      placeholderData: keepPreviousData,
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
    const queryClient = useQueryClient();
    const refresh = useStageRefresh();
    return useMutation({
      mutationFn: async (vars: { id: string; input: StageUpdateInput }) => {
        const result = await api.patch(`${stagesEndpoint}/${vars.id}`, vars.input);
        return unwrap<PipelineStage | null>(result, null);
      },
      // Optimistic: a rename in `PipelineStagesManager` is cheap + exactly
      // rollbackable (we know precisely what changed), so waiting a round
      // trip to see the new label reads as unresponsive. Rollback discipline
      // mirrors `products/social-wiring/frontend/src/hooks/useCardHub.ts`'s
      // `useSetClienteTagsMutation`: cancel in-flight reads of this key,
      // snapshot, patch, restore the snapshot on error.
      onMutate: async (vars) => {
        await queryClient.cancelQueries({ queryKey: stagesKey });
        const previous = queryClient.getQueryData<PipelineStage[]>(stagesKey);
        if (previous) {
          queryClient.setQueryData<PipelineStage[]>(
            stagesKey,
            previous.map((s) =>
              // `StageUpdateInput.cor` is a plain `string` (the raw value out
              // of a colour picker, unvalidated) while `PipelineStage.cor` is
              // the narrower `StageColor` union — the cast is safe because
              // this merge is a TRANSIENT optimistic snapshot, immediately
              // either confirmed by the settle-time refetch or rolled back
              // via `context.previous` on error; it never persists as-is.
              s.id === vars.id ? ({ ...s, ...vars.input } as PipelineStage) : s,
            ),
          );
        }
        return { previous };
      },
      onError: (error: Error, _vars, context) => {
        if (context?.previous) {
          queryClient.setQueryData(stagesKey, context.previous);
        }
        toast.error('Erro ao atualizar etapa', { description: error.message });
      },
      onSuccess: (stage) => {
        toast.success(`Etapa "${stage?.label ?? ''}" atualizada`);
        refresh();
      },
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
    const queryClient = useQueryClient();
    const refresh = useStageRefresh();
    return useMutation({
      mutationFn: async (ordem: string[]) => {
        const result = await api.post(`${stagesEndpoint}/reordenar`, { ordem });
        return unwrap<PipelineStage[]>(result, []);
      },
      // Optimistic: `PipelineStagesManager`'s up/down buttons should move
      // the row on click, not on round-trip. `ordem` (the full new id
      // order) IS the exact new `posicao` assignment, so — same rollback
      // discipline as `useUpdateStage` above — the snapshot restore on
      // error is exact, not a guess.
      onMutate: async (ordem: string[]) => {
        await queryClient.cancelQueries({ queryKey: stagesKey });
        const previous = queryClient.getQueryData<PipelineStage[]>(stagesKey);
        if (previous) {
          const posicaoById = new Map(ordem.map((id, index) => [id, index]));
          queryClient.setQueryData<PipelineStage[]>(
            stagesKey,
            previous.map((s) =>
              posicaoById.has(s.id) ? { ...s, posicao: posicaoById.get(s.id)! } : s,
            ),
          );
        }
        return { previous };
      },
      onError: (error: Error, _vars, context) => {
        if (context?.previous) {
          queryClient.setQueryData(stagesKey, context.previous);
        }
        toast.error('Erro ao reordenar etapas', { description: error.message });
      },
      onSuccess: () => {
        toast.success('Ordem das etapas atualizada');
        refresh();
      },
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
