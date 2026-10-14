/** `<ErpQuotesTiles/>` — open quotes (sent/viewed) and those expiring within a week. Needs the quotes hooks. */
import * as React from 'react';
import { formatCents } from '../organ-kit/money';
import type { QuotesHooks } from '../quotes/hooks';
import { daysUntil, ErpStat, ErpTileSection, type ErpTileGroupProps } from './shared';

export interface ErpQuotesTilesProps extends ErpTileGroupProps {
  hooks: QuotesHooks;
}

const WINDOW_DAYS = 7;

export function ErpQuotesTiles({ hooks, t, now, onNavigate }: ErpQuotesTilesProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const sent = hooks.useQuotes({ status: 'sent', page: 1, page_size: 100 });
  const viewed = hooks.useQuotes({ status: 'viewed', page: 1, page_size: 100 });
  const queries = [sent, viewed];
  const ready = queries.every((q) => q.data);
  const open = queries.flatMap((q) => q.data?.data ?? []);
  const openTotal = queries.reduce((s, q) => s + (q.data?.pagination.total ?? 0), 0);
  const expiring = open.filter((q) => {
    const d = daysUntil(q.valid_until, base);
    return d !== null && d >= 0 && d <= WINDOW_DAYS;
  });
  const query = {
    showSkeleton: queries.some((q) => q.showSkeleton),
    isRefreshing: queries.some((q) => q.isRefreshing),
    isError: queries.some((q) => q.isError && !q.data),
    error: queries.find((q) => q.isError)?.error,
    refetch: () => Promise.all(queries.map((q) => q.refetch())),
  };
  return (
    <ErpTileSection title={t('quotes.title')} testId="erp-quotes" openLabel={t('common.open')} onOpen={onNavigate ? () => onNavigate('quotes') : undefined}>
      <ErpStat testId="erp-quotes-open" t={t} query={query} label={t('quotes.open')}
        hint={ready ? t('quotes.open_hint', { amount: formatCents(open.reduce((s, q) => s + q.total_cents, 0)) }) : undefined}
        value={ready ? String(openTotal) : '—'} />
      <ErpStat testId="erp-quotes-expiring" t={t} query={query} label={t('quotes.expiring')} hint={t('quotes.expiring_hint')}
        value={ready ? String(expiring.length) : '—'} />
    </ErpTileSection>
  );
}
