/** Building blocks every dashboard tile group shares (not exported from the barrel). */
import * as React from 'react';
import { StatTile } from '../design-system/charts/StatTile';
import { RefreshingBar, RetryError } from '../organ-kit/controls';
import { errorMessage } from '../organ-kit/query';
import type { ErpDashboardTranslate } from './i18n';

/** The slice of an organ read (`signals()` output) a tile needs. */
export interface TileQuery {
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
}

export interface ErpTileGroupProps {
  t: ErpDashboardTranslate;
  /** Reference date (tests inject it); default: now. */
  now?: Date;
  /** Optional deep link: the host maps the organ key to its route. */
  onNavigate?: (target: string) => void;
}

/** One KPI tile: skeleton on first load, retryable error when nothing to show, value otherwise. */
export function ErpStat({ label, value, hint, query, t, testId }: {
  label: string;
  value: string;
  hint?: string;
  query: TileQuery;
  t: ErpDashboardTranslate;
  testId: string;
}) {
  if (query.isError && !query.showSkeleton && value === '—') {
    return (
      <div data-testid={`${testId}-error`} className="space-y-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <RetryError
          message={`${t('common.error_loading')}: ${errorMessage(query.error)}`}
          onRetry={() => void query.refetch()}
          retryLabel={t('common.retry')}
        />
      </div>
    );
  }
  return (
    <div data-testid={testId} aria-busy={query.isRefreshing}>
      <StatTile label={label} value={value} hint={hint} loading={query.showSkeleton} />
      <RefreshingBar active={query.isRefreshing} label={t('common.refreshing')} />
    </div>
  );
}

export function ErpTileSection({ title, testId, children }: { title: string; testId: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2" data-testid={testId} aria-label={title}>
      <h2 className="text-sm font-semibold text-muted-foreground">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>
    </section>
  );
}

/** Whole days from `from` to the ISO date `iso` (negative when past). */
export function daysUntil(iso: string | null | undefined, from: Date): number | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const target = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const base = Date.UTC(from.getFullYear(), from.getMonth(), from.getDate());
  return Math.round((target - base) / 86_400_000);
}
