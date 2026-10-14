/** `<ErpContractsTiles/>` — active contracts, expiring contracts and the next billings. Needs the contracts hooks. */
import * as React from 'react';
import { formatCents } from '../organ-kit/money';
import type { ContractsHooks } from '../contracts/hooks';
import { daysUntil, ErpStat, ErpTileSection, type ErpTileGroupProps } from './shared';

export interface ErpContractsTilesProps extends ErpTileGroupProps {
  hooks: ContractsHooks;
}

const WINDOW_DAYS = 30;

export function ErpContractsTiles({ hooks, t, now }: ErpContractsTilesProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const active = hooks.useContracts({ status: 'active', page: 1, page_size: 100 });
  const expiring = hooks.useContracts({ status: 'active', expiring_within_days: WINDOW_DAYS, page: 1, page_size: 1 });

  const rows = active.data?.data ?? [];
  const activeTotal = active.data?.pagination.total ?? 0;
  const cycleTotal = rows.reduce((s, c) => s + c.amount_cents, 0);
  const billing = rows.filter((c) => {
    const d = daysUntil(c.next_period_on, base);
    return d !== null && d >= 0 && d <= WINDOW_DAYS;
  });

  return (
    <ErpTileSection title={t('contracts.title')} testId="erp-contracts">
      <ErpStat testId="erp-contracts-active" t={t} query={active} label={t('contracts.active')}
        hint={active.data ? t('contracts.active_hint', { amount: formatCents(cycleTotal) }) : undefined}
        value={active.data ? String(activeTotal) : '—'} />
      <ErpStat testId="erp-contracts-expiring" t={t} query={expiring} label={t('contracts.expiring')} hint={t('contracts.expiring_hint')}
        value={expiring.data ? String(expiring.data.pagination.total) : '—'} />
      <ErpStat testId="erp-contracts-billings" t={t} query={active} label={t('contracts.next_billings')}
        hint={active.data ? t('contracts.next_billings_hint', { n: billing.length }) : undefined}
        value={active.data ? formatCents(billing.reduce((s, c) => s + c.amount_cents, 0)) : '—'} />
    </ErpTileSection>
  );
}
