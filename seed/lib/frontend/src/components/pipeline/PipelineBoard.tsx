/**
 * `<PipelineBoard/>` — a complete, editable kanban board from a descriptor.
 *
 * Composes the presentation organ (`KanbanBoard`) with the data mechanic
 * (`createPipelineHooks`), so a consumer supplies a descriptor and a card
 * renderer and gets: real data, drag-to-move with optimistic update and
 * rollback, column headers with per-stage totals, loading/error/empty states,
 * and — when `stagesEndpoint` is declared — a stage editor.
 *
 * Columns are DYNAMICALLY POPULATED from the stage rows the API returns, so
 * renaming, recolouring, reordering, adding or removing a stage is reflected on
 * the next refresh with no code change and no deploy.
 *
 * EDITING ON THE BOARD ITSELF (all opt-in; omit them and the board renders
 * exactly as before):
 *  - `editableHeaders` — each column title becomes a `StageHeaderMenu`
 *    (inline rename, recolour, delete with a target stage), and a trailing
 *    "+ coluna" slot adds a stage.
 *  - `reorderableColumns` — columns drag horizontally (mouse, touch
 *    press-and-hold, keyboard) and the new order persists via
 *    `useReorderStages`; pass `onColumnReorder` to handle it yourself.
 *  - `canEditStages={false}` — the viewer may not reshape the pipeline: every
 *    stage-editing affordance (the two above AND "Configurar etapas") is
 *    withheld. The server-side twin is `pipeline_stages_router(...,
 *    require_stage_admin=...)`; this prop only hides what the API would refuse.
 *
 * MOVE INTERCEPT (opt-in via `onBeforeMove`): every drag normally goes
 * straight to `useMoveCard().mutate`. Pass `onBeforeMove` and the board
 * AWAITS its decision first — a product can block a move (a stage-gate rule
 * a same-tab UI can't enforce server-side alone), or ask for a reason (see
 * `MotivoMoveDialog`) before committing.
 *
 * SNAP-BACK-UNTIL-CONFIRMED: while `onBeforeMove`'s promise is unresolved,
 * the mutation is simply never called, so the card has nothing to be
 * optimistic ABOUT yet — it renders back in its source column (dimmed, via
 * the internal pending-id set) until a decision lands, never in the target
 * column ahead of confirmation. `false` cancels outright (nothing was ever
 * mutated, so there is nothing to roll back); `true` or `{ motivo, extra }`
 * proceeds through the normal optimistic-move-then-rollback-on-error path.
 * A move the SERVER rejects (409/422) is unaffected by any of this — it
 * still rolls back via `useMoveCard`'s own `onError`; `onMoveError` (opt-in)
 * REPLACES the default toast for that case, and also fires if `onBeforeMove`
 * itself throws (nothing to roll back there either).
 *
 * Usage:
 * ```tsx
 * const pipeline = createPipelineHooks<NegociacaoVenda>({
 *   queryKey: 'funil',
 *   boardEndpoint: '/api/funil',
 *   stagesEndpoint: '/api/funil/etapas',
 *   moveEndpoint: '/api/negociacoes-venda',
 *   getCardId: (n) => n.id,
 *   getCardValue: (n) => Number(n.valor_estimado || 0),
 *   entityLabel: 'negociação',
 * }, api);
 *
 * <PipelineBoard
 *   hooks={pipeline}
 *   filtros={filtros}
 *   renderCard={(n, { isDragging }) => <NegociacaoCard negociacao={n} isDragging={isDragging} />}
 * />
 * ```
 */
import * as React from 'react';

import { KanbanBoard } from '../kanban';
import type { KanbanCardRenderState } from '../kanban';
import { Button } from '../../design-system/ui/Button';
import { AddStageColumn } from './AddStageColumn';
import { PipelineStagesManager } from './PipelineStagesManager';
import { StageHeaderMenu } from './StageHeaderMenu';
import { mergeVisibleStageOrder } from './stageOrder';
import { STAGE_ROLE_LABELS, stageColorClasses } from './stageTokens';
import type { MoveVariables, PipelineHooks } from './createPipelineHooks';
import type {
  MoveDecision,
  MoveIntentContext,
  PipelineColumn,
  PipelineStage,
  StageRoleLabels,
} from './types';

export interface PipelineBoardProps<TCard> {
  hooks: PipelineHooks<TCard>;
  renderCard: (card: TCard, state: KanbanCardRenderState) => React.ReactNode;
  /**
   * A genuine card click — press and release without a drag. The usual
   * consumer is "open this card's detail modal". Buttons rendered inside the
   * card must still `stopPropagation`, since a button click is not a card
   * click.
   */
  onCardClick?: (card: TCard) => void;
  /** Server-side filters, forwarded to the board endpoint and the query key. */
  filtros?: Record<string, any>;
  /** Format a column's monetary total. Defaults to a plain number. */
  formatValue?: (value: number) => string;
  /** Text for an empty column. */
  emptyColumnLabel?: string;
  /** Show the "Configurar etapas" control. Default: true when editable. */
  allowStageEditing?: boolean;
  loadingState?: React.ReactNode;
  className?: string;
  columnClassName?: string;
  /** Extra controls rendered beside the stage-editor toggle. */
  toolbar?: React.ReactNode;
  /**
   * Ask the board endpoint for more cards per column.
   *
   * Rendered ONLY while some column is actually truncated (`exibidos < total`).
   * A "load more" that is always visible is a control that lies half the time,
   * and the board already knows which half it is in — the consumer does not.
   */
  onLoadMore?: () => void;
  /** Label for the load-more control. */
  loadMoreLabel?: string;
  /**
   * Opt-in: edit stages from the column headers (rename / recolour / delete)
   * and add one from a trailing "+ coluna" slot. Needs `stagesEndpoint`.
   */
  editableHeaders?: boolean;
  /**
   * Opt-in: drag columns to reorder the stages. Persists through
   * `useReorderStages` unless `onColumnReorder` is given. Needs
   * `stagesEndpoint` (or `onColumnReorder`).
   */
  reorderableColumns?: boolean;
  /**
   * Take over a column reorder. Receives the new order of the VISIBLE
   * (active) stage ids. Implies `reorderableColumns`.
   */
  onColumnReorder?: (orderedStageIds: string[]) => void;
  /**
   * May this viewer reshape the pipeline? Default `true`. `false` withholds
   * every stage-editing affordance — header editing, column drag, the
   * trailing add slot and "Configurar etapas".
   */
  canEditStages?: boolean;
  /** Role → label descriptor for the stage editors. Default: seed defaults. */
  roleLabels?: StageRoleLabels;
  /**
   * Opt-in async gate on every drag, cross-column OR same-column, before it
   * mutates. See the module doc's MOVE INTERCEPT / SNAP-BACK-UNTIL-CONFIRMED
   * sections. Sync returns work too (`Promise.resolve` wraps them).
   */
  onBeforeMove?: (ctx: MoveIntentContext<TCard>) => Promise<MoveDecision> | MoveDecision;
  /**
   * Fires when a move does not land — the SERVER rejects it (409/422; the
   * optimistic update is already rolled back by the time this runs) OR
   * `onBeforeMove` itself throws (nothing was ever mutated). Omit and the
   * existing `sonner` toast (`Erro ao mover ${entityLabel}`) fires instead —
   * this prop REPLACES that default, it does not add to it.
   */
  onMoveError?: (error: Error, vars: MoveVariables) => void;
}

const DEFAULT_COLUMN_CLASS =
  'flex-shrink-0 w-80 rounded-lg border bg-card text-card-foreground shadow-sm h-full flex flex-col overflow-hidden ' +
  '[&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto';

export function PipelineBoard<TCard>({
  hooks,
  renderCard,
  onCardClick,
  filtros,
  formatValue = (v) => String(v),
  emptyColumnLabel = 'Nenhuma carta nesta etapa',
  allowStageEditing,
  loadingState,
  className,
  columnClassName = DEFAULT_COLUMN_CLASS,
  toolbar,
  onLoadMore,
  loadMoreLabel = 'Carregar mais',
  editableHeaders = false,
  reorderableColumns = false,
  onColumnReorder,
  canEditStages = true,
  roleLabels = STAGE_ROLE_LABELS,
  onBeforeMove,
  onMoveError,
}: PipelineBoardProps<TCard>) {
  const { descriptor } = hooks;
  const { data: colunas, isPending, isFetching, error } = hooks.useBoard(filtros);
  const moveCard = hooks.useMoveCard(
    onMoveError ? { onError: (error, vars) => onMoveError(error, vars) } : undefined,
  );
  const [configurando, setConfigurando] = React.useState(false);
  // Cards awaiting an `onBeforeMove` decision — see SNAP-BACK-UNTIL-CONFIRMED
  // in the module doc. Dimmed via `renderCard`'s wrapper below; the card
  // itself never leaves its source column because `moveCard.mutate` is only
  // called once the decision resolves.
  const [pendingMoveIds, setPendingMoveIds] = React.useState<ReadonlySet<string>>(new Set());

  const hasStagesApi = Boolean(descriptor.stagesEndpoint);
  const editable = canEditStages && (allowStageEditing ?? hasStagesApi);
  const headersEditable = canEditStages && editableHeaders && hasStagesApi;
  const columnsReorderable =
    canEditStages && (Boolean(onColumnReorder) || (reorderableColumns && hasStagesApi));
  const columns = React.useMemo(() => colunas ?? [], [colunas]);

  // Stage mutations are idle hooks (no request until `.mutate`), so calling
  // them unconditionally costs nothing on a board that never edits. The stage
  // LIST is only fetched when a column reorder needs it (the API wants the
  // full order, inactive stages included — see `mergeVisibleStageOrder`).
  const { data: allStages } = hooks.useStages({
    enabled: columnsReorderable && !onColumnReorder && hasStagesApi,
  });
  const createStage = hooks.useCreateStage();
  const updateStage = hooks.useUpdateStage();
  const deleteStage = hooks.useDeleteStage();
  const reorderStages = hooks.useReorderStages();
  const stageBusy =
    createStage.isPending ||
    updateStage.isPending ||
    deleteStage.isPending ||
    reorderStages.isPending;

  // Delete targets offered from a header: the stages the user can SEE.
  const boardStages = React.useMemo(
    () =>
      columns
        .map((c) => c.stage)
        .filter((stage): stage is PipelineStage => Boolean(stage)),
    [columns],
  );

  const handleColumnReorder = React.useCallback(
    (visibleOrder: string[]) => {
      if (onColumnReorder) {
        onColumnReorder(visibleOrder);
        return;
      }
      reorderStages.mutate(mergeVisibleStageOrder(allStages ?? [], visibleOrder));
    },
    [allStages, onColumnReorder, reorderStages],
  );

  // Card counts per stage, so the stage editor can warn before a delete that
  // would strand cards.
  const cardCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    columns.forEach((c) => {
      counts[c.etapa] = c.total ?? c.cards.length;
    });
    return counts;
  }, [columns]);

  // Some column is showing fewer cards than it has.
  const algumaTruncada = columns.some(
    (c) => c.exibidos !== undefined && c.exibidos < (c.total ?? 0),
  );

  const runMove = React.useCallback(
    (
      cardId: string,
      toStageId: string,
      toIndex: number,
      decision?: { motivo?: string; extra?: Record<string, unknown> },
    ) => {
      moveCard.mutate({ cardId, toStageId, toIndex, motivo: decision?.motivo, extra: decision?.extra });
    },
    [moveCard],
  );

  const handleMove = React.useCallback(
    (cardId: string, fromStageId: string, toStageId: string, toIndex: number) => {
      if (!onBeforeMove) {
        runMove(cardId, toStageId, toIndex);
        return;
      }

      const fromCol = columns.find((c) => c.etapa === fromStageId);
      const toCol = columns.find((c) => c.etapa === toStageId);
      const card =
        fromCol?.cards.find((c) => descriptor.getCardId(c) === cardId) ??
        columns.flatMap((c) => c.cards).find((c) => descriptor.getCardId(c) === cardId);

      // Should never happen — `KanbanBoard` only reports moves for cards and
      // stages it was itself handed — but a resolution failure here must
      // fail OPEN (the drag still completes) rather than silently eating the
      // user's drag because `onBeforeMove`'s ctx could not be built.
      if (!fromCol?.stage || !toCol?.stage || !card) {
        runMove(cardId, toStageId, toIndex);
        return;
      }

      const fromIndex = columns.indexOf(fromCol);
      const toColIndex = columns.indexOf(toCol);
      const direction: MoveIntentContext<TCard>['direction'] =
        toColIndex === fromIndex ? 'same' : toColIndex > fromIndex ? 'forward' : 'backward';
      const stepDistance = Math.abs(toColIndex - fromIndex);

      setPendingMoveIds((prev) => new Set(prev).add(cardId));

      Promise.resolve(
        onBeforeMove({
          card,
          fromStage: fromCol.stage,
          toStage: toCol.stage,
          toIndex,
          direction,
          stepDistance,
        }),
      )
        .then((decision: MoveDecision) => {
          if (decision === false) return; // cancelled — never mutated, nothing to roll back
          if (decision === true) {
            runMove(cardId, toStageId, toIndex);
            return;
          }
          runMove(cardId, toStageId, toIndex, decision);
        })
        .catch((error: unknown) => {
          onMoveError?.(
            error instanceof Error ? error : new Error(String(error)),
            { cardId, toStageId, toIndex },
          );
        })
        .finally(() => {
          setPendingMoveIds((prev) => {
            if (!prev.has(cardId)) return prev;
            const next = new Set(prev);
            next.delete(cardId);
            return next;
          });
        });
    },
    [columns, descriptor, onBeforeMove, onMoveError, runMove],
  );

  return (
    <div className={className}>
      {(editable || toolbar || (onLoadMore && algumaTruncada)) && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {toolbar}
          {onLoadMore && algumaTruncada && (
            <Button
              variant="outline"
              size="sm"
              onClick={onLoadMore}
              data-testid="pipeline-load-more"
            >
              {loadMoreLabel}
            </Button>
          )}
          {editable && (
            <Button
              variant={configurando ? 'primary' : 'outline'}
              size="sm"
              className="ml-auto"
              onClick={() => setConfigurando((v) => !v)}
            >
              {configurando ? 'Fechar configuração' : 'Configurar etapas'}
            </Button>
          )}
        </div>
      )}

      {configurando && editable && (
        <div className="mb-6 rounded-lg border p-4">
          <PipelineStagesManager
            hooks={hooks}
            cardCounts={cardCounts}
            onClose={() => setConfigurando(false)}
          />
        </div>
      )}

      {/*
        No explicit JSX type arguments (`<KanbanBoard<TCard, string> …>`) here.
        They typecheck fine, but the component-tagger dev plugin rewrites JSX
        opening elements by splicing `data-*` attributes in BEFORE the type
        argument list, producing `<KanbanBoard data-...="..."<TCard, string>` —
        which fails the esbuild transform with `Expected ">" but found "<"`.
        `columns`/`getCardId`/`renderCard` pin `TCard` by inference anyway.
      */}
      <KanbanBoard
        // Scoped to the empty case — never bare `isPending || isFetching` —
        // matching the canonical `Funil.tsx` pattern
        // (`KB § PATTERNS/frontend/lying-loading-state.md`). `useMoveCard` is
        // optimistic, so its `onSettled` flips `isFetching` true on every
        // drag; an unscoped `isLoading` here would blank + re-mount the whole
        // board on every card move. `KanbanBoard` itself now also ignores
        // `isLoading` once `columns` is non-empty (defense in depth), so this
        // scoping is belt-and-braces, not the only thing standing between the
        // consumer and a flicker.
        isLoading={isPending || (isFetching && columns.length === 0)}
        error={error}
        loadingState={loadingState}
        columns={columns.map((coluna: PipelineColumn<TCard>) => ({
          stage: { id: coluna.etapa, label: coluna.stage?.label ?? '' },
          cards: coluna.cards,
        }))}
        getCardId={descriptor.getCardId}
        // The card's own stage. Columns are pre-grouped server-side, so this is
        // only consulted to compute a drag's origin.
        getCardStage={(card) =>
          columns.find((c) => c.cards.some((x) => descriptor.getCardId(x) === descriptor.getCardId(card)))
            ?.etapa ?? ''
        }
        renderCard={(card, state) => {
          const node = renderCard(card, state);
          // Snap-back-until-confirmed visual: dim the card while its
          // `onBeforeMove` decision is unresolved (see module doc). No-op
          // (renders `node` untouched) when `onBeforeMove` is not set, since
          // `pendingMoveIds` is then never populated.
          if (!pendingMoveIds.has(descriptor.getCardId(card))) return node;
          return (
            <div className="opacity-60 pointer-events-none transition-opacity" aria-busy="true">
              {node}
            </div>
          );
        }}
        onCardActivate={onCardClick}
        renderColumnHeader={(stage) => {
          const coluna = columns.find((c) => c.etapa === stage.id);
          const classes = stageColorClasses(coluna?.stage?.cor);
          const truncada =
            coluna?.exibidos !== undefined && coluna.exibidos < (coluna.total ?? 0);
          const colunaStage = coluna?.stage;
          return (
            <div className={`p-4 border-b ${classes.bgColor} ${classes.borderColor}`}>
              <div className="flex items-center justify-between mb-2 gap-2">
                {headersEditable && colunaStage ? (
                  <StageHeaderMenu
                    stage={colunaStage}
                    stages={boardStages}
                    cardCount={coluna?.total ?? coluna?.cards.length ?? 0}
                    busy={stageBusy}
                    roleLabels={roleLabels}
                    titleClassName={classes.color}
                    onRename={(label) =>
                      updateStage.mutate({ id: colunaStage.id, input: { label } })
                    }
                    onRecolor={(cor) =>
                      updateStage.mutate({ id: colunaStage.id, input: { cor } })
                    }
                    onDelete={(reassignTo) =>
                      deleteStage.mutate({ id: colunaStage.id, reassignTo })
                    }
                  />
                ) : (
                  <h3 className={`font-semibold text-sm min-w-0 truncate ${classes.color}`}>
                    {coluna?.stage?.label ?? stage.label}
                  </h3>
                )}
                <span
                  className="text-xs rounded-full bg-background/60 px-2 py-0.5 whitespace-nowrap"
                  title={
                    truncada
                      ? `Mostrando ${coluna!.exibidos} de ${coluna!.total} cartões`
                      : undefined
                  }
                >
                  {/* 🔴 A capped column must SAY it is capped. Showing the true
                      total beside 50 rendered cards reads as a bug; showing
                      only 50 under-reports the pipeline. Both numbers, always. */}
                  {truncada
                    ? `${coluna!.exibidos} de ${coluna!.total}`
                    : (coluna?.total ?? 0)}
                </span>
              </div>
              <p className="text-sm font-medium">{formatValue(coluna?.valorTotal ?? 0)}</p>
            </div>
          );
        }}
        columnEmptyState={() => (
          <div className="text-center text-muted-foreground text-sm py-8">
            {emptyColumnLabel}
          </div>
        )}
        emptyState={
          <div className="text-center text-muted-foreground text-sm py-12">
            Nenhuma etapa configurada.
            {editable && ' Use "Configurar etapas" para criar a primeira.'}
          </div>
        }
        onMove={(cardId, fromStage, toStage, toIndex) => {
          // Same-column reordering PERSISTS. It used to early-return here, so
          // dragging a card up its own column animated and then snapped back
          // on the next refetch — the board looked reorderable and was not.
          //
          // A same-stage drop still goes through `mover-etapa`: the server
          // treats it as a position-only change (no history row, no stage
          // gate), so there is no second endpoint that could drift from this
          // one. `handleMove` routes through `onBeforeMove` when the consumer
          // set one (fires for same-stage moves too — `direction: 'same'`);
          // otherwise it mutates directly, byte-identical to before.
          handleMove(cardId, fromStage, toStage, toIndex);
        }}
        columnClassName={columnClassName}
        onColumnReorder={columnsReorderable ? handleColumnReorder : undefined}
        renderTrailingColumn={
          headersEditable
            ? () => (
                <AddStageColumn
                  busy={stageBusy}
                  onCreate={(label) => createStage.mutate({ label })}
                />
              )
            : undefined
        }
      />
    </div>
  );
}
