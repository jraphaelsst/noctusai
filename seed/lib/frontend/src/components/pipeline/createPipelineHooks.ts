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
import { keepPreviousData, useQuery, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';

import { boardOps, listOps, useCacheWriteMutation } from '../../cache-writes';

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
  /**
   * Extra fields merged into the `mover-etapa` POST body verbatim. Set by
   * `PipelineBoard`'s opt-in `onBeforeMove` intercept (`MoveDecision`'s
   * object form) — never populated by the board's own drag handling.
   */
  extra?: Record<string, unknown>;
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

  /**
   * `options.onError` REPLACES the default `sonner` toast (never adds to
   * it) — `PipelineBoard` passes it through from its own `onMoveError` prop
   * so a product wiring its own rejection UX (e.g. re-opening
   * `MotivoMoveDialog` with a server-supplied message) never double-toasts.
   * Omit it and this hook's behaviour is byte-identical to before.
   */
  function useMoveCard(options?: { onError?: (error: Error, vars: MoveVariables) => void }) {
    return useCacheWriteMutation<TCard | null, MoveVariables>({
      mutationFn: async (vars) => {
        const result = await api.post(`${moveEndpoint}/${vars.cardId}/mover-etapa`, {
          para_etapa_id: vars.toStageId,
          novo_indice: vars.toIndex,
          motivo: vars.motivo,
          ...vars.extra,
        });
        return unwrap<TCard | null>(result, null);
      },

      // Optimistic move so the card lands under the cursor immediately. `match: 'prefix'` (not the bare
      // key): the board key carries the active filters (`[queryKey, filtros]`), so a bare read would
      // snapshot an empty entry and the rollback would silently restore nothing. The server's answer is
      // only the moved card (totals/ordering are the server's), so there is no commit: settle refetches.
      targets: [
        {
          queryKey: [queryKey],
          match: 'prefix',
          optimistic: (old: PipelineColumn<TCard>[] | undefined, vars) =>
            boardOps<TCard>(getCardValue, getCardId).moveCard(old, vars.cardId, vars.toStageId, vars.toIndex),
        },
      ],
      invalidate: invalidateOnSettle.map((k) => [k]),

      onError: (error, vars) => {
        if (options?.onError) {
          options.onError(error, vars);
        } else {
          toast.error(`Erro ao mover ${entityLabel}`, { description: error.message });
        }
      },
    });
  }

  // ---- Stage CRUD -------------------------------------------------------

  /**
   * The board is invalidated too, not just the stage list.
   *
   * A rename changes what every COLUMN HEADER says, and column definitions
   * arrive with the board payload. Refreshing only the stage list leaves the
   * board rendering the old label until something else happens to refetch it,
   * which reads as "the rename didn't work".
   */
  const boardKey: QueryKey[] = [[queryKey]];

  function useCreateStage() {
    return useCacheWriteMutation<PipelineStage | null, StageCreateInput>({
      mutationFn: async (input) => {
        const result = await api.post(stagesEndpoint!, input);
        return unwrap<PipelineStage | null>(result, null);
      },
      // The server assigns id + posicao: commit the created stage into the list (no stand-in).
      targets: [
        {
          queryKey: stagesKey,
          commit: (old: PipelineStage[] | undefined, stage) =>
            stage ? listOps.replace(old, stage.id, stage) : old,
        },
      ],
      invalidate: boardKey,
      onSuccess: (stage) => {
        toast.success(`Etapa "${stage?.label ?? ''}" criada`);
      },
      onError: (error) =>
        toast.error('Erro ao criar etapa', { description: error.message }),
    });
  }

  function useUpdateStage() {
    // Optimistic: a rename in `PipelineStagesManager` is cheap + exactly rollbackable (we know precisely
    // what changed), so waiting a round trip to see the new label reads as unresponsive.
    //
    // `StageUpdateInput.cor` is a plain `string` (the raw value out of a colour picker, unvalidated) while
    // `PipelineStage.cor` is the narrower `StageColor` union — the cast is safe because this merge is a
    // TRANSIENT optimistic snapshot, confirmed by the server's row on answer or rolled back on error.
    const patch = (s: PipelineStage, id: string, input: StageUpdateInput) =>
      s.id === id ? ({ ...s, ...input } as PipelineStage) : s;
    return useCacheWriteMutation<PipelineStage | null, { id: string; input: StageUpdateInput }>({
      mutationFn: async (vars) => {
        const result = await api.patch(`${stagesEndpoint}/${vars.id}`, vars.input);
        return unwrap<PipelineStage | null>(result, null);
      },
      targets: ({ id, input }) => [
        {
          queryKey: stagesKey,
          optimistic: (old: PipelineStage[] | undefined) => old?.map((s) => patch(s, id, input)),
          commit: (old: PipelineStage[] | undefined, stage) =>
            stage ? listOps.patch(old, id, stage) : old,
        },
        // The BOARD too: column headers read `coluna.stage`, so a rename or recolour made from a column
        // header (`editableHeaders`) must land on the header immediately, not one round trip later.
        // `match: 'prefix'` for the same reason as `useMoveCard` — the board key carries the filters.
        {
          queryKey: [queryKey],
          match: 'prefix',
          optimistic: (old: PipelineColumn<TCard>[] | undefined) =>
            Array.isArray(old)
              ? old.map((coluna) =>
                  coluna.stage && coluna.stage.id === id
                    ? { ...coluna, stage: patch(coluna.stage, id, input) }
                    : coluna,
                )
              : old,
          commit: (old: PipelineColumn<TCard>[] | undefined, stage) =>
            Array.isArray(old) && stage
              ? old.map((coluna) =>
                  coluna.stage && coluna.stage.id === id ? { ...coluna, stage: { ...coluna.stage, ...stage } } : coluna,
                )
              : old,
        },
      ],
      onError: (error) => {
        toast.error('Erro ao atualizar etapa', { description: error.message });
      },
      onSuccess: (stage) => {
        toast.success(`Etapa "${stage?.label ?? ''}" atualizada`);
      },
    });
  }

  function useDeleteStage() {
    return useCacheWriteMutation<{ cards_movidos?: number } | null, { id: string; reassignTo?: string }>({
      mutationFn: async (vars) => {
        const result = await api.delete(
          `${stagesEndpoint}/${vars.id}`,
          vars.reassignTo ? { reassign_to: vars.reassignTo } : undefined,
        );
        return unwrap<{ cards_movidos?: number } | null>(result, null);
      },
      // The stage leaves the list on click; where its cards went is the server's call, so the board refetches.
      targets: ({ id }) => [
        {
          queryKey: stagesKey,
          optimistic: (old: PipelineStage[] | undefined) => listOps.remove(old, id),
        },
      ],
      invalidate: boardKey,
      onSuccess: (result) => {
        const moved = result?.cards_movidos ?? 0;
        toast.success(
          moved
            ? `Etapa excluída — ${moved} ${entityLabel}${moved === 1 ? '' : 's'} movida${
                moved === 1 ? '' : 's'
              }`
            : 'Etapa excluída',
        );
      },
      onError: (error) =>
        toast.error('Erro ao excluir etapa', { description: error.message }),
    });
  }

  function useReorderStages() {
    return useCacheWriteMutation<PipelineStage[], string[]>({
      mutationFn: async (ordem) => {
        const result = await api.post(`${stagesEndpoint}/reordenar`, { ordem });
        return unwrap<PipelineStage[]>(result, []);
      },
      // Optimistic: `PipelineStagesManager`'s up/down buttons should move the row on click, not on
      // round-trip. `ordem` (the full new id order) IS the exact new `posicao` assignment, so the
      // snapshot restore on error is exact, not a guess.
      targets: (ordem) => {
        const posicaoById = new Map(ordem.map((id, index) => [id, index]));
        return [
          {
            queryKey: stagesKey,
            optimistic: (old: PipelineStage[] | undefined) =>
              old?.map((s) =>
                posicaoById.has(s.id) ? { ...s, posicao: posicaoById.get(s.id)! } : s,
              ),
          },
          // The BOARD's column order too, so a column dragged on the board (`PipelineBoard
          // reorderableColumns`) stays where it was dropped instead of snapping back until the refetch
          // lands. Columns the order does not mention keep their relative place at the end.
          {
            queryKey: [queryKey],
            match: 'prefix' as const,
            optimistic: (old: PipelineColumn<TCard>[] | undefined) => {
              if (!Array.isArray(old)) return old;
              const rank = (c: PipelineColumn<TCard>) =>
                posicaoById.get(c.etapa) ?? Number.MAX_SAFE_INTEGER;
              return old
                .map((coluna, index) => ({ coluna, index }))
                .sort((a, b) => rank(a.coluna) - rank(b.coluna) || a.index - b.index)
                .map(({ coluna }) => coluna);
            },
          },
        ];
      },
      onError: (error) => {
        toast.error('Erro ao reordenar etapas', { description: error.message });
      },
      onSuccess: () => {
        toast.success('Ordem das etapas atualizada');
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
