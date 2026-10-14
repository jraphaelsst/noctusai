/**
 * `<ItemsTable/>` — searchable, filterable, paginated item list with archive / restore and CSV export.
 *
 * Reads `GET /api/items`. Selecting a row calls `onSelect(item)` (the host opens `<ItemEditor/>`);
 * `onCreate` renders the "new item" button. `canWrite` hides the write controls for staff (server stays
 * the authority). Money is integer cents, formatted only via `formatCents`.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { formatCents } from '../commerce/format';
import { EmptyState, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { errorMessage, type ItemListParams, type ItemsHooks } from './hooks';
import { itemsT as t } from './messages';
import { flattenCategories } from './ItemCategoryManager';
import { ITEM_TYPES, type Item } from './types';

export interface ItemsTableProps {
  hooks: ItemsHooks;
  onSelect?: (item: Item) => void;
  onCreate?: () => void;
  /** Show archive / restore controls (default `true`). */
  canWrite?: boolean;
  /** Trigger the browser download of the exported blob. Default: an object-URL anchor click. */
  saveBlob?: (blob: Blob, filename: string) => void;
}

function defaultSaveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function ItemsTable({ hooks, onSelect, onCreate, canWrite = true, saveBlob = defaultSaveBlob }: ItemsTableProps) {
  const [q, setQ] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [page, setPage] = React.useState(1);
  const [itemType, setItemType] = React.useState('');
  const [active, setActive] = React.useState<'' | 'true' | 'false'>('true');
  const [categoryId, setCategoryId] = React.useState('');

  React.useEffect(() => {
    const h = setTimeout(() => {
      setDebounced(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const params: ItemListParams = { page, q: debounced, item_type: itemType, active, category_id: categoryId };
  const items = hooks.useItems(params);
  const categories = hooks.useItemCategories();
  const m = hooks.useItemMutations();
  const exporter = hooks.useExportItems();

  async function doExport() {
    try {
      const blob = await exporter.mutateAsync({ q: debounced, item_type: itemType, active, category_id: categoryId });
      saveBlob(blob, 'itens.csv');
    } catch {
      // Surfaced below via `exporter.error`.
    }
  }

  const filters = (
    <div className="grid gap-2 sm:grid-cols-5">
      <Input
        type="search"
        aria-label={t('items.search')}
        placeholder={t('items.search')}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <Select aria-label={t('items.filter_type')} value={itemType} onChange={(e) => { setItemType(e.target.value); setPage(1); }}>
        <option value="">{t('items.filter_type')}: {t('common.all')}</option>
        {ITEM_TYPES.map((x) => (
          <option key={x} value={x}>{t(`type.${x}`)}</option>
        ))}
      </Select>
      <Select aria-label={t('items.filter_status')} value={active} onChange={(e) => { setActive(e.target.value as '' | 'true' | 'false'); setPage(1); }}>
        <option value="true">{t('items.status_active')}</option>
        <option value="false">{t('items.status_archived')}</option>
        <option value="">{t('common.all')}</option>
      </Select>
      <Select aria-label={t('items.filter_category')} value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setPage(1); }}>
        <option value="">{t('items.filter_category')}: {t('common.all')}</option>
        {flattenCategories(categories.data ?? []).map(([c, depth]) => (
          <option key={c.id} value={c.id}>{`${'— '.repeat(depth)}${c.name}`}</option>
        ))}
      </Select>
      <div className="flex items-center justify-end gap-2">
        <Button size="sm" variant="outline" disabled={exporter.isPending} onClick={doExport}>
          {exporter.isPending ? t('items.exporting') : t('items.export')}
        </Button>
        {onCreate && canWrite ? <Button size="sm" onClick={onCreate}>{t('items.new')}</Button> : null}
      </div>
    </div>
  );

  if (items.showSkeleton) return <ListSkeleton rows={6} />;
  if (items.isError && !items.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(items.error)}`} onRetry={() => items.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows: Item[] = items.data?.data ?? [];
  const pg = items.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;
  const mutErr = m.archive.error ?? m.unarchive.error;
  const filtered = debounced !== '' || itemType !== '' || categoryId !== '' || active !== 'true';

  return (
    <section className="space-y-3" aria-busy={items.isRefreshing}>
      {filters}
      <RefreshingBar active={items.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : exporter.error ? `${t('items.export_failed')}: ${errorMessage(exporter.error)}` : null} />
      {rows.length === 0 ? (
        <EmptyState message={filtered ? t('items.empty_search') : t('items.empty')} />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('items.col_sku')}</th>
              <th className="p-2">{t('items.col_name')}</th>
              <th className="p-2">{t('items.col_type')}</th>
              <th className="p-2">{t('items.col_unit')}</th>
              <th className="p-2 text-right">{t('items.col_cost')}</th>
              <th className="p-2 text-right">{t('items.col_price')}</th>
              <th className="p-2">{t('items.col_status')}</th>
              {canWrite ? <th className="p-2" /> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((it) => (
              <tr key={it.id} className={`border-b hover:bg-accent ${onSelect ? 'cursor-pointer' : ''}`} onClick={() => onSelect?.(it)}>
                <td className="p-2 font-mono text-xs">{it.sku}</td>
                <td className="p-2">{it.name}</td>
                <td className="p-2">{t(`type.${it.item_type}`)}</td>
                <td className="p-2">{it.unit}</td>
                <td className="p-2 text-right">{formatCents(it.cost_cents)}</td>
                <td className="p-2 text-right">{it.price_cents == null ? '—' : formatCents(it.price_cents)}</td>
                <td className="p-2">
                  {it.is_active ? <Badge variant="outline">{t('items.active')}</Badge> : <Badge variant="muted">{t('items.archived')}</Badge>}
                </td>
                {canWrite ? (
                  <td className="p-2 text-right" onClick={(e) => e.stopPropagation()}>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={m.archive.isPending || m.unarchive.isPending}
                      onClick={() => (it.is_active ? m.archive.mutate(it.id) : m.unarchive.mutate(it.id))}
                    >
                      {it.is_active ? t('items.archive') : t('items.unarchive')}
                    </Button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {totalPages > 1 ? (
        <nav className="flex items-center justify-between text-sm" aria-label={t('items.title')}>
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            {t('common.previous')}
          </Button>
          <span>{t('items.page', { page, pages: totalPages })}</span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            {t('common.next')}
          </Button>
        </nav>
      ) : null}
    </section>
  );
}
