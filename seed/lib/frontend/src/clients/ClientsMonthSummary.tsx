/**
 * `<ClientsMonthSummary/>` -- the month at a glance (`GET /api/clients/summary?month=YYYY-MM`): sessions held and
 * missed, what was charged, received and is still open (over the sessions DATED in the month). Previous / next month;
 * the previous month stays on screen while the next one loads.
 */
import { ChevronLeft, ChevronRight } from 'lucide-react';
import * as React from 'react';

import { Button } from '../design-system/ui/Button';
import { formatCents } from '../organ-kit/money';
import { EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { addMonths, formatMonth } from './format';
import { errorMessage, type ClientsHooks } from './hooks';
import { t } from './i18n';
import { StatTile } from './parts';

export interface ClientsMonthSummaryProps {
  hooks: ClientsHooks;
  /** The month shown first (`YYYY-MM`). */
  month: string;
}

export function ClientsMonthSummary({ hooks, month: initial }: ClientsMonthSummaryProps) {
  const { data: config } = hooks.useClientsConfig();
  const [month, setMonth] = React.useState(initial);
  const summary = hooks.useMonthSummary(month);
  const s = summary.data;
  const absence = new Set(config?.absence_statuses ?? ['falta']);
  const absences = s ? Object.entries(s.by_status).reduce((n, [slug, count]) => (absence.has(slug) ? n + count : n), 0) : 0;
  const money = config?.finance_enabled !== false;

  return (
    <section className="space-y-2 rounded-md border p-3" data-testid="month-summary">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t('month.title')}</h3>
        <Button variant="outline" size="sm" onClick={() => setMonth(addMonths(month, -1))} aria-label={t('month.prev')} data-testid="month-prev">
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-[10rem] text-center text-sm font-medium" data-testid="month-label">
          {formatMonth(month)}
        </span>
        <Button variant="outline" size="sm" onClick={() => setMonth(addMonths(month, 1))} aria-label={t('month.next')} data-testid="month-next">
          <ChevronRight className="h-4 w-4" />
        </Button>
        <RefreshingBar active={summary.isRefreshing} label={t('common.refreshing')} />
      </div>
      {summary.showSkeleton ? (
        <ListSkeleton rows={2} />
      ) : summary.isError && !s ? (
        <RetryError message={`${t('month.error')} ${errorMessage(summary.error)}`} onRetry={() => void summary.refetch()} retryLabel={t('common.retry')} />
      ) : s && s.sessions === 0 ? (
        <EmptyState message={t('month.empty')} />
      ) : s ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <StatTile label={t('month.sessions')} value={s.sessions} testId="month-sessions" />
          <StatTile label={t('month.done')} value={s.by_status[config?.done_session_status ?? 'realizada'] ?? 0} testId="month-done" />
          <StatTile label={t('month.absences')} value={absences} testId="month-absences" />
          {money && <StatTile label={t('month.charged')} value={formatCents(s.charged_cents)} testId="month-charged" />}
          {money && <StatTile label={t('month.received')} value={formatCents(s.received_cents)} tone="success" testId="month-received" />}
          {money && <StatTile label={t('month.open')} value={formatCents(s.open_cents)} tone={s.overdue_cents > 0 ? 'destructive' : undefined} testId="month-open" />}
        </div>
      ) : null}
    </section>
  );
}
