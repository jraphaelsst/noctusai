/**
 * `<LeadsList/>` -- the table subpage: every lead, filterable by stage / origin / first-contact range / text,
 * newest first contact first, "Carregar mais" pages (cursor). A row opens the same detail modal as a card.
 */
import { Plus } from 'lucide-react';
import * as React from 'react';

import type { DetailAction } from '../components/detail/EntityDetailDialog';
import { Badge } from '../design-system/ui/Badge';
import { Button } from '../design-system/ui/Button';
import { EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { displayPhone, firstContactLabel, hasActiveFilters, originLabel, stageLabel, stageOf } from './format';
import { stageTagClasses } from '../components/pipeline/stageTokens';
import { errorMessage, type LeadsHooks } from './hooks';
import { t } from './i18n';
import { LeadDetailModal } from './LeadDetailModal';
import { LeadFormDialog } from './LeadFormDialog';
import { LeadsFilterBar } from './LeadsFilterBar';
import type { Lead, LeadFiltersState } from './types';
import { useLeadFilters } from './useLeadFilters';

export interface LeadsListProps {
  hooks: LeadsHooks;
  filters?: LeadFiltersState;
  onFiltersChange?: (next: LeadFiltersState) => void;
  onOpenConversation?: (lead: Lead) => void;
  /** Extra detail-modal actions per lead (forwarded to `LeadDetailModal`). */
  extraActions?: (lead: Lead) => DetailAction[];
  readOnly?: boolean;
}

export function LeadsList({ hooks, filters: controlled, onFiltersChange, onOpenConversation, extraActions, readOnly }: LeadsListProps) {
  const [filters, setFilters] = useLeadFilters(controlled, onFiltersChange);
  const { data: config } = hooks.useLeadsConfig();
  const list = hooks.useLeadsList(filters);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const rows = list.data ?? [];
  const open = openId ? rows.find((l) => l.id === openId) ?? null : null;

  return (
    <div className="space-y-3" data-testid="leads-list">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0 flex-1">
          <LeadsFilterBar value={filters} onChange={setFilters} config={config} showStage />
        </div>
        {!readOnly && (
          <Button onClick={() => setCreating(true)}>
            <Plus className="mr-1 h-4 w-4" />
            {t('list.new')}
          </Button>
        )}
      </div>
      <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      {list.showSkeleton ? (
        <ListSkeleton />
      ) : list.isError && !list.data ? (
        <RetryError message={`${t('list.error')} ${errorMessage(list.error)}`} onRetry={() => void list.refetch()} retryLabel={t('common.retry')} />
      ) : rows.length === 0 ? (
        <EmptyState message={hasActiveFilters(filters) ? t('list.empty_filtered') : t('list.empty')} />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                {['name', 'phone', 'origin', 'stage', 'first_contact', 'last_message'].map((c) => (
                  <th key={c} className="px-3 py-2 font-medium">
                    {t(`list.col_${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((lead) => (
                <tr
                  key={lead.id}
                  className="cursor-pointer border-t hover:bg-muted/40"
                  onClick={() => setOpenId(lead.id)}
                  data-testid={`lead-row-${lead.id}`}
                >
                  <td className="px-3 py-2 font-medium">{lead.name}</td>
                  <td className="px-3 py-2 text-muted-foreground">{displayPhone(lead.phone) || '—'}</td>
                  <td className="px-3 py-2">
                    <Badge variant="outline">{originLabel(config, lead.origin)}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="outline" className={stageTagClasses(stageOf(config, lead.stage)?.color)}>
                      {stageLabel(config, lead.stage)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{firstContactLabel(lead)}</td>
                  <td className="max-w-xs truncate px-3 py-2 text-muted-foreground">{lead.last_message_preview ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {list.hasNextPage && (
        <div className="text-center">
          <Button variant="outline" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>
            {list.isFetchingNextPage ? t('list.loading_more') : t('list.more')}
          </Button>
        </div>
      )}
      <LeadDetailModal hooks={hooks} lead={open} onClose={() => setOpenId(null)} onOpenConversation={onOpenConversation} extraActions={extraActions} />
      <LeadFormDialog hooks={hooks} open={creating} lead={null} onClose={() => setCreating(false)} />
    </div>
  );
}
