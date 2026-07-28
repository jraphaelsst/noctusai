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
import { PipelineStagesManager } from './PipelineStagesManager';
import { stageColorClasses } from './stageTokens';
import type { PipelineHooks } from './createPipelineHooks';
import type { PipelineColumn } from './types';

export interface PipelineBoardProps<TCard> {
  hooks: PipelineHooks<TCard>;
  renderCard: (card: TCard, state: KanbanCardRenderState) => React.ReactNode;
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
}

const DEFAULT_COLUMN_CLASS =
  'flex-shrink-0 w-80 rounded-lg border bg-card text-card-foreground shadow-sm h-full flex flex-col overflow-hidden ' +
  '[&>[data-kanban-column-id]]:flex-1 [&>[data-kanban-column-id]]:p-3 [&>[data-kanban-column-id]]:overflow-y-auto';

export function PipelineBoard<TCard>({
  hooks,
  renderCard,
  filtros,
  formatValue = (v) => String(v),
  emptyColumnLabel = 'Nenhuma carta nesta etapa',
  allowStageEditing,
  loadingState,
  className,
  columnClassName = DEFAULT_COLUMN_CLASS,
  toolbar,
}: PipelineBoardProps<TCard>) {
  const { descriptor } = hooks;
  const { data: colunas, isPending, isFetching, error } = hooks.useBoard(filtros);
  const moveCard = hooks.useMoveCard();
  const [configurando, setConfigurando] = React.useState(false);

  const editable = allowStageEditing ?? Boolean(descriptor.stagesEndpoint);
  const columns = React.useMemo(() => colunas ?? [], [colunas]);

  // Card counts per stage, so the stage editor can warn before a delete that
  // would strand cards.
  const cardCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    columns.forEach((c) => {
      counts[c.etapa] = c.total ?? c.cards.length;
    });
    return counts;
  }, [columns]);

  return (
    <div className={className}>
      {(editable || toolbar) && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {toolbar}
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
        // Gate on `isPending || isFetching`, never bare `isLoading`: during a
        // background refetch `isLoading` is false, so the empty branch would
        // render an empty board over data that exists.
        isLoading={isPending || isFetching}
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
        renderCard={renderCard}
        renderColumnHeader={(stage) => {
          const coluna = columns.find((c) => c.etapa === stage.id);
          const classes = stageColorClasses(coluna?.stage?.cor);
          return (
            <div className={`p-4 border-b ${classes.bgColor} ${classes.borderColor}`}>
              <div className="flex items-center justify-between mb-2 gap-2">
                <h3 className={`font-semibold text-sm min-w-0 truncate ${classes.color}`}>
                  {coluna?.stage?.label ?? stage.label}
                </h3>
                <span className="text-xs rounded-full bg-background/60 px-2 py-0.5">
                  {coluna?.total ?? 0}
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
          // Only cross-stage drops mutate; reordering within a column is a
          // client-side no-op, matching the pre-organ behaviour.
          if (fromStage === toStage) return;
          moveCard.mutate({ cardId, toStageId: toStage, toIndex });
        }}
        columnClassName={columnClassName}
      />
    </div>
  );
}
