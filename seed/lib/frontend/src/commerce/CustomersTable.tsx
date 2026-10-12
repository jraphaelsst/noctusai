/**
 * `<CustomersTable/>` — searchable customer list with an in-page detail panel
 * (field-source badges per D26: `payment` > `form`, `staff` edits, plus
 * orders/consents and `<PrivacyActions/>`).
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { EmptyState, Input, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents, formatDateTime, maskCpfOrCnpj } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { OrderStatusChip } from './OrderStatusChip';
import { PrivacyActions } from './PrivacyActions';
import type { Customer, FieldSourceInfo } from './types';

export interface CustomersTableProps {
  hooks: CommerceHooks;
  locale?: string;
}

const SOURCE_FIELDS = ['name', 'email', 'doc', 'phone', 'address'] as const;

export function FieldSourceBadge({ info, locale }: { info?: FieldSourceInfo; locale?: string }) {
  const { t } = useCommerceT(locale);
  if (!info) return null;
  return (
    <Badge variant={info.source === 'payment' ? 'default' : 'outline'} data-source={info.source} title={formatDateTime(info.at)}>
      {t(`field_source.${info.source}`)}
      {info.verified ? ' ✓' : ''}
    </Badge>
  );
}

function CustomerDetail({ hooks, id, locale }: { hooks: CommerceHooks; id: string; locale?: string }) {
  const { t, locale: loc } = useCommerceT(locale);
  const c = hooks.useCustomer(id);
  if (c.showSkeleton) return <ListSkeleton rows={4} />;
  if (c.isError && !c.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(c.error)}`} onRetry={() => c.refetch()} retryLabel={t('common.retry')} />;
  }
  const d = c.data;
  if (!d) return <EmptyState message={t('customers.not_found')} />;
  return (
    <div className="space-y-4 rounded-md border p-4" aria-busy={c.isRefreshing}>
      <RefreshingBar active={c.isRefreshing} label={t('common.refreshing')} />
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        {SOURCE_FIELDS.filter((f) => f !== 'address').map((f) => (
          <div key={f} className="flex items-center gap-2">
            <dt className="w-20 text-xs text-muted-foreground">{t(`customers.field_${f}`)}</dt>
            <dd>{f === 'doc' ? maskCpfOrCnpj(d.doc) : String(d[f] ?? '—') || '—'}</dd>
            <FieldSourceBadge info={d.field_sources?.[f]} locale={locale} />
          </div>
        ))}
      </dl>
      <section>
        <h4 className="mb-1 text-sm font-semibold">{t('customers.orders')}</h4>
        {(d.orders ?? []).length === 0 ? (
          <EmptyState message={t('orders.empty')} />
        ) : (
          <ul className="space-y-1 text-sm">
            {(d.orders ?? []).map((o) => (
              <li key={o.id} className="flex items-center gap-2">
                <OrderStatusChip status={o.status} locale={locale} /> {formatCents(o.total_cents, o.currency, loc)}
                <span className="text-xs text-muted-foreground">{formatDateTime(o.created_at, loc)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <h4 className="mb-1 text-sm font-semibold">{t('customers.consents')}</h4>
        {(d.consents ?? []).length === 0 ? (
          <EmptyState message={t('customers.consents_empty')} />
        ) : (
          <ul className="space-y-1 text-sm">
            {(d.consents ?? []).map((k, i) => (
              <li key={k.id ?? i}>
                {t(`consent.${k.kind}`)} v{k.version} — {k.granted ? t('common.yes') : t('common.no')}{' '}
                <span className="text-xs text-muted-foreground">{formatDateTime(k.at, loc)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <PrivacyActions hooks={hooks} customer={d} locale={locale} />
    </div>
  );
}

export function CustomersTable({ hooks, locale }: CustomersTableProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const [q, setQ] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [page, setPage] = React.useState(1);
  const [selected, setSelected] = React.useState<string | null>(null);

  React.useEffect(() => {
    const h = setTimeout(() => {
      setDebounced(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const customers = hooks.useCustomers({ q: debounced, page });

  if (customers.showSkeleton) return <ListSkeleton rows={6} />;
  if (customers.isError && !customers.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(customers.error)}`} onRetry={() => customers.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows: Customer[] = customers.data?.data ?? [];
  const pg = customers.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  return (
    <section className="space-y-3" aria-busy={customers.isRefreshing}>
      <Input
        type="search"
        aria-label={t('customers.search')}
        placeholder={t('customers.search')}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <RefreshingBar active={customers.isRefreshing} label={t('common.refreshing')} />
      {rows.length === 0 ? (
        <EmptyState message={debounced ? t('customers.empty_search') : t('customers.empty')} />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="p-2">{t('customers.field_name')}</th>
              <th className="p-2">{t('customers.field_email')}</th>
              <th className="p-2">{t('customers.field_doc')}</th>
              <th className="p-2">{t('customers.since')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr
                key={c.id}
                className={`cursor-pointer border-b hover:bg-accent ${selected === c.id ? 'bg-accent' : ''}`}
                onClick={() => setSelected(selected === c.id ? null : c.id)}
              >
                <td className="p-2">
                  {c.name || '—'} {c.anonymized_at ? <Badge variant="muted">{t('customers.anonymized')}</Badge> : null}
                </td>
                <td className="p-2">{c.email}</td>
                <td className="p-2">{c.doc ? maskCpfOrCnpj(c.doc) : '—'}</td>
                <td className="p-2">{formatDateTime(c.created_at, loc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
          <span>{page} / {totalPages}</span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </div>
      ) : null}
      {selected ? <CustomerDetail hooks={hooks} id={selected} locale={locale} /> : null}
    </section>
  );
}
