/** `<ContractBillingPreview/>` — the next N receivables the contract will bill (and the running month's retainer excess). */
import * as React from 'react';
import { EmptyState, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { contractsErrorText } from './errors';
import { formatDate } from './format';
import type { ContractsHooks } from './hooks';
import { t } from './i18n';
import { formatCents } from '../organ-kit/money';

export interface ContractBillingPreviewProps {
  hooks: ContractsHooks;
  contractId: string;
  /** How many upcoming receivables to list. Default 6. */
  count?: number;
}

export function ContractBillingPreview({ hooks, contractId, count = 6 }: ContractBillingPreviewProps) {
  const q = hooks.useBillingPreview(contractId, count);
  let body: React.ReactNode;
  if (q.showSkeleton) body = <ListSkeleton rows={3} />;
  else if (q.isError && !q.data) body = <RetryError message={`${t('common.error_loading')}: ${contractsErrorText(q.error)}`} onRetry={() => q.refetch()} retryLabel={t('common.retry')} />;
  else {
    const items = q.data?.items ?? [];
    const running = q.data?.running_month;
    body = (
      <>
        {items.length === 0 ? (
          <EmptyState message={t('preview.empty')} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="p-2">{t('preview.col_due')}</th>
                <th className="p-2">{t('preview.col_desc')}</th>
                <th className="p-2 text-right">{t('preview.col_amount')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={`${i.period_key}:${i.kind}`} className="border-b">
                  <td className="p-2 tabular-nums">{formatDate(i.due_date)}</td>
                  <td className="p-2">{i.description}</td>
                  <td className="p-2 text-right tabular-nums">{formatCents(i.amount_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {q.data && q.data.billed > 0 ? <p className="text-xs text-muted-foreground">{t('preview.billed', { n: q.data.billed })}</p> : null}
        {running ? (
          <p className="text-xs text-muted-foreground">
            {t('preview.running', {
              used: +(running.minutes / 60).toFixed(2), included: +((running.included_minutes ?? 0) / 60).toFixed(2), excess: formatCents(running.excess_cents),
            })}
          </p>
        ) : null}
      </>
    );
  }
  return (
    <section className="space-y-2" aria-busy={q.isRefreshing}>
      <h3 className="text-sm font-semibold">{t('preview.title')}</h3>
      <RefreshingBar active={q.isRefreshing} label={t('common.refreshing')} />
      {body}
    </section>
  );
}
