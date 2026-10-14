/**
 * `<ContractTimeline/>` — the versions / amendments of one contract, newest first, each with its `changes` diff
 * (initial terms, aditivos, reajustes, renovações, suspensões, encerramento). Append-only on the server.
 */
import * as React from 'react';
import { Badge } from '../design-system/ui/Badge';
import { EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { contractsErrorText } from './errors';
import { formatDate, bpToPercent } from './format';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import { formatCents } from '../organ-kit/money';
import type { ContractVersion } from './types';

export interface ContractTimelineProps {
  hooks: ContractsHooks;
  contractId: string;
}

const MONEY_FIELDS = new Set(['amount_cents', 'penalty_applied_cents', 'excess_rate_cents', 'penalty_cents']);

function show(field: string, value: unknown): string {
  if (value == null) return '—';
  if (MONEY_FIELDS.has(field)) return formatCents(Number(value));
  if (field === 'percent_bp') return `${bpToPercent(Number(value))}%`;
  if (field === 'end_date') return formatDate(String(value));
  return String(value);
}

function fieldLabel(field: string): string {
  const key = `field.${field}`;
  const label = t(key);
  return label === key ? field : label;
}

function Entry({ v }: { v: ContractVersion }) {
  const changes = Object.entries(v.changes ?? {});
  return (
    <li className="space-y-1 border-l-2 pl-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={v.kind === 'termination' ? 'destructive' : 'outline'}>{t(`kind.${v.kind}`)}</Badge>
        <span className="text-xs text-muted-foreground">{t('timeline.version', { n: v.version_n })}</span>
        {v.effective_on ? <span className="text-xs text-muted-foreground">{t('timeline.effective', { date: formatDate(v.effective_on) })}</span> : null}
      </div>
      {v.summary ? <p className="text-sm">{v.summary}</p> : null}
      {changes.length ? (
        <ul className="text-xs text-muted-foreground">
          {changes.map(([field, c]) => (
            <li key={field}>{t('timeline.change', { field: fieldLabel(field), from: show(field, c.from), to: show(field, c.to) })}</li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function ContractTimeline({ hooks, contractId }: ContractTimelineProps) {
  const q = hooks.useVersions(contractId);
  let body: React.ReactNode;
  if (q.showSkeleton) body = <ListSkeleton rows={3} />;
  else if (q.isError && !q.data) body = <RetryError message={`${t('common.error_loading')}: ${contractsErrorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t('common.retry')} />;
  else if (!q.data?.length) body = <EmptyState message={t('timeline.empty')} />;
  else body = <ol className="space-y-3" aria-label={t('timeline.title')}>{[...q.data].sort((a, b) => b.version_n - a.version_n).map((v) => <Entry key={v.id} v={v} />)}</ol>;
  return (
    <section className="space-y-2" aria-busy={q.isRefreshing}>
      <h3 className="text-sm font-semibold">{t('timeline.title')}</h3>
      <RefreshingBar active={q.isRefreshing} label={t('common.refreshing')} />
      {body}
    </section>
  );
}
