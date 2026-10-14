/** `<KardexView/>` — an item's append-only history with the running balance and average cost after each move. */
import * as React from 'react';
import { Button, EmptyState, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { formatCents, formatDateTime, formatQty, shortId } from './format';
import { errorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';
import type { MoveKind } from './types';

export interface KardexViewProps extends InventoryOrganProps {
  itemId: string;
  warehouseId?: string;
}

const OUTWARD: ReadonlySet<MoveKind> = new Set(['out', 'transfer_out', 'commit']);

export function KardexView({ hooks, t = defaultInventoryT, locale, itemLabel = shortId, itemId, warehouseId: initialWarehouse }: KardexViewProps) {
  const [warehouseId, setWarehouseId] = React.useState(initialWarehouse ?? '');
  const [page, setPage] = React.useState(1);
  const warehouses = hooks.useWarehouses();
  const kardex = hooks.useKardex({ item_id: itemId, warehouse_id: warehouseId || undefined, page });
  const whName = React.useMemo(() => new Map((warehouses.data ?? []).map((w) => [w.id, w.name])), [warehouses.data]);

  if (kardex.showSkeleton) return <ListSkeleton rows={6} />;
  if (kardex.isError && !kardex.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(kardex.error)}`} onRetry={() => kardex.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = kardex.data?.data ?? [];
  const pg = kardex.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  return (
    <section className="space-y-3" aria-busy={kardex.isRefreshing} aria-label={t('kardex.title')}>
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold">{t('kardex.title')} · {itemLabel(itemId)}</h3>
        <Select aria-label={t('balances.warehouse')} value={warehouseId} onChange={(e) => { setWarehouseId(e.target.value); setPage(1); }} className="w-56">
          <option value="">{t('common.all_warehouses')}</option>
          {(warehouses.data ?? []).map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </Select>
        <RefreshingBar active={kardex.isRefreshing} label={t('common.refreshing')} />
      </div>
      {rows.length === 0 ? (
        <EmptyState message={t('kardex.empty')} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2">{t('kardex.when')}</th>
                <th>{t('kardex.kind')}</th>
                <th>{t('balances.warehouse')}</th>
                <th className="text-right">{t('kardex.qty')}</th>
                <th className="text-right">{t('kardex.unit_cost')}</th>
                <th className="text-right">{t('kardex.on_hand_after')}</th>
                <th className="text-right">{t('kardex.reserved_after')}</th>
                <th className="text-right">{t('kardex.avg_after')}</th>
                <th>{t('kardex.origin')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => {
                const signed = m.kind === 'adjust' ? m.qty : OUTWARD.has(m.kind) ? -m.qty : m.qty;
                const neutral = m.kind === 'reserve' || m.kind === 'release';
                return (
                  <tr key={m.id} className="border-b" data-testid="kardex-row" data-kind={m.kind}>
                    <td className="py-2">{formatDateTime(m.occurred_at, locale)}</td>
                    <td>{t(`kind.${m.kind}`)}</td>
                    <td>{whName.get(m.warehouse_id) ?? shortId(m.warehouse_id)}</td>
                    <td className="text-right">{neutral ? formatQty(m.qty, locale) : `${signed > 0 ? '+' : ''}${formatQty(signed, locale)}`}</td>
                    <td className="text-right">{formatCents(m.unit_cost_cents, 'BRL', locale)}</td>
                    <td className="text-right font-medium">{formatQty(m.on_hand_after, locale)}</td>
                    <td className="text-right">{formatQty(m.reserved_after, locale)}</td>
                    <td className="text-right">{formatCents(m.avg_cost_after_cents, 'BRL', locale)}</td>
                    <td className="text-xs text-muted-foreground">{m.source_ref ? `${m.source} · ${m.source_ref}` : m.source}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-xs">
          <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
          <span>{t('common.page', { page, pages: totalPages })}</span>
          <Button size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </div>
      ) : null}
    </section>
  );
}
