/** `<ErpFinanceTiles/>` — month result (DRE), cash position, open AR/AP and what is overdue. Needs the finance hooks. */
import * as React from 'react';
import { formatCents } from '../organ-kit/money';
import { monthEndIso, monthStartIso, remainingCents } from '../finance/format';
import type { FinanceHooks } from '../finance/hooks';
import { ErpStat, ErpTileSection, type ErpTileGroupProps } from './shared';

export interface ErpFinanceTilesProps extends ErpTileGroupProps {
  hooks: FinanceHooks;
}

export function ErpFinanceTiles({ hooks, t, now }: ErpFinanceTilesProps) {
  const base = React.useMemo(() => now ?? new Date(), [now]);
  const dre = hooks.useDre({ from: monthStartIso(base), to: monthEndIso(base), view: 'statement' });
  const cash = hooks.useCashflow({ from: monthStartIso(base), to: monthEndIso(base, 5) });
  const aging = hooks.useAging();
  const overduePayable = hooks.useEntries({ direction: 'payable', overdue: true, page: 1, page_size: 100 });

  const apRows = overduePayable.data?.data ?? [];
  const apTotal = apRows.reduce((s, e) => s + remainingCents(e), 0);
  const apCount = overduePayable.data?.pagination.total ?? 0;

  return (
    <ErpTileSection title={t('finance.title')} testId="erp-finance">
      <ErpStat testId="erp-month-result" t={t} query={dre} label={t('finance.month_result')} hint={t('finance.month_result_hint')}
        value={dre.data ? formatCents(dre.data.net_result_cents) : '—'} />
      <ErpStat testId="erp-cash" t={t} query={cash} label={t('finance.cash')} hint={t('finance.cash_hint')}
        value={cash.data ? formatCents(cash.data.closing_realized_balance_cents) : '—'} />
      <ErpStat testId="erp-open-receivable" t={t} query={cash} label={t('finance.open_receivable')} hint={t('finance.window_hint')}
        value={cash.data ? formatCents(cash.data.totals.projected_in_cents) : '—'} />
      <ErpStat testId="erp-open-payable" t={t} query={cash} label={t('finance.open_payable')} hint={t('finance.window_hint')}
        value={cash.data ? formatCents(cash.data.totals.projected_out_cents) : '—'} />
      <ErpStat testId="erp-overdue-receivable" t={t} query={aging} label={t('finance.overdue_receivable')}
        hint={aging.data ? t('finance.overdue_receivable_hint', { n: aging.data.counterparties.length }) : undefined}
        value={aging.data ? formatCents(aging.data.totals.total_cents) : '—'} />
      <ErpStat testId="erp-overdue-payable" t={t} query={overduePayable} label={t('finance.overdue_payable')}
        hint={overduePayable.data
          ? (apCount > apRows.length ? t('finance.overdue_payable_partial', { n: apRows.length, total: apCount }) : t('finance.overdue_payable_hint', { n: apCount }))
          : undefined}
        value={overduePayable.data ? formatCents(apTotal) : '—'} />
    </ErpTileSection>
  );
}
