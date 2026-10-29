/**
 * `<LeadsBoard/>` -- the funnel: a kanban column per configured stage, drag a card to move it, click it to open the
 * detail modal. Built on the seed `KanbanBoard` (sensors / a11y / drag overlay) and `useMoveLead` (optimistic move).
 */
import { Plus } from 'lucide-react';
import * as React from 'react';

import type { DetailAction } from '../components/detail/EntityDetailDialog';
import { Button } from '../design-system/ui/Button';
import { KanbanBoard } from '../components/kanban/KanbanBoard';
import type { KanbanColumnData } from '../components/kanban/types';
import { toast } from 'sonner';
import { ErrorState, RefreshingBar } from './controls';
import { originLabel, stageOf } from './format';
import { errorMessage, type LeadsHooks } from './hooks';
import { t } from './i18n';
import { LeadCard } from './LeadCard';
import { LeadDetailModal } from './LeadDetailModal';
import { LeadFormDialog } from './LeadFormDialog';
import { LeadsFilterBar } from './LeadsFilterBar';
import type { Lead, LeadFiltersState } from './types';
import { useLeadFilters } from './useLeadFilters';

export interface LeadsBoardProps {
  hooks: LeadsHooks;
  /** Controlled filters (so the board and the list can share one search); local state when omitted. */
  filters?: LeadFiltersState;
  onFiltersChange?: (next: LeadFiltersState) => void;
  onOpenConversation?: (lead: Lead) => void;
  /** Extra detail-modal actions per lead (forwarded to `LeadDetailModal`). */
  extraActions?: (lead: Lead) => DetailAction[];
  /** Hide the "Novo lead" button. */
  readOnly?: boolean;
}

export function LeadsBoard({ hooks, filters: controlled, onFiltersChange, onOpenConversation, extraActions, readOnly }: LeadsBoardProps) {
  const [filters, setFilters] = useLeadFilters(controlled, onFiltersChange);
  const { data: config } = hooks.useLeadsConfig();
  const board = hooks.useLeadsBoard(filters);
  const move = hooks.useMoveLead();
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);

  const columns: KanbanColumnData<Lead>[] = React.useMemo(
    () => (board.data ?? []).map((c) => ({ stage: { id: c.etapa, label: c.stage.label }, cards: c.cards })),
    [board.data],
  );
  const totals = React.useMemo(() => new Map((board.data ?? []).map((c) => [c.etapa, c])), [board.data]);
  // The open lead is read from the CURRENT board, so an edit / move shows up in the modal without a second source.
  const open = React.useMemo(() => (openId ? columns.flatMap((c) => c.cards).find((l) => l.id === openId) ?? null : null), [openId, columns]);

  return (
    <div className="space-y-3" data-testid="leads-board">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0 flex-1">
          <LeadsFilterBar value={filters} onChange={setFilters} config={config} />
        </div>
        {!readOnly && (
          <Button onClick={() => setCreating(true)} data-testid="leads-new">
            <Plus className="mr-1 h-4 w-4" />
            {t('list.new')}
          </Button>
        )}
      </div>
      <RefreshingBar active={board.isRefreshing} label={t('common.refreshing')} />
      <KanbanBoard<Lead>
        columns={columns}
        getCardId={(l) => l.id}
        getCardStage={(l) => l.stage}
        // First load only (`showSkeleton`): a filter change keeps the previous columns on screen (placeholderData).
        isLoading={board.showSkeleton}
        error={board.isError && !board.data ? board.error : undefined}
        errorState={board.isError && !board.data ? <ErrorState message={`${t('board.error')} ${errorMessage(board.error)}`} /> : undefined}
        columnEmptyState={() => <p className="py-4 text-center text-xs text-muted-foreground">{t('board.empty_column')}</p>}
        renderColumnHeader={(stage, cards) => {
          const col = totals.get(stage.id);
          const hidden = col ? col.total - cards.length : 0;
          return (
            <div className="flex items-center justify-between px-1 pb-2">
              <span className="text-sm font-semibold">{stage.label}</span>
              <span className="text-xs text-muted-foreground" title={hidden > 0 ? t('board.more', { n: hidden }) : undefined}>
                {col?.total ?? cards.length}
              </span>
            </div>
          );
        }}
        renderCard={(lead) => <LeadCard lead={lead} originLabel={originLabel(config, lead.origin)} stage={stageOf(config, lead.stage)} />}
        onCardActivate={(lead) => setOpenId(lead.id)}
        onMove={(id, from, to, toIndex) => {
          move.mutate(
            { id, stage: to, toIndex },
            { onError: (err) => toast.error(t('board.move_error'), { description: errorMessage(err) }) },
          );
        }}
      />
      <LeadDetailModal hooks={hooks} lead={open} onClose={() => setOpenId(null)} onOpenConversation={onOpenConversation} extraActions={extraActions} />
      <LeadFormDialog hooks={hooks} open={creating} lead={null} onClose={() => setCreating(false)} />
    </div>
  );
}
