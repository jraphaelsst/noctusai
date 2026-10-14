/** `<WarehousesManager/>` — warehouses CRUD: create, rename, make default, deactivate (never delete). */
import * as React from 'react';
import { Badge, Button, EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { errorMessage, inventoryErrorMessage } from './hooks';
import { defaultInventoryT } from './i18n';
import type { InventoryOrganProps } from './shared';

export interface WarehousesManagerProps extends InventoryOrganProps {
  canWrite?: boolean;
}

export function WarehousesManager({ hooks, t = defaultInventoryT, canWrite = false }: WarehousesManagerProps) {
  const warehouses = hooks.useWarehouses();
  const m = hooks.useWarehouseMutations();
  const [name, setName] = React.useState('');
  const [code, setCode] = React.useState('');
  const [city, setCity] = React.useState('');
  const [uf, setUf] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);

  if (warehouses.showSkeleton) return <ListSkeleton rows={3} />;
  if (warehouses.isError && !warehouses.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(warehouses.error)}`} onRetry={() => warehouses.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = warehouses.data ?? [];

  async function run(p: Promise<unknown>) {
    setErr(null);
    try {
      await p;
    } catch (e) {
      setErr(inventoryErrorMessage(e, t));
    }
  }

  async function create(ev: React.FormEvent) {
    ev.preventDefault();
    if (!name.trim() || !code.trim()) {
      setErr(t('warehouses.invalid'));
      return;
    }
    await run(
      m.create
        .mutateAsync({ name: name.trim(), code: code.trim(), address: { city: city.trim() || null, state: uf.trim().toUpperCase() || null } })
        .then(() => { setName(''); setCode(''); setCity(''); setUf(''); }),
    );
  }

  return (
    <section className="space-y-3" aria-busy={warehouses.isRefreshing} aria-label={t('warehouses.title')}>
      <RefreshingBar active={warehouses.isRefreshing} label={t('common.refreshing')} />
      {rows.length === 0 ? (
        <EmptyState message={t('warehouses.empty')} />
      ) : (
        <ul className="divide-y rounded-md border">
          {rows.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-2 p-3 text-sm" data-testid="warehouse-row">
              <strong>{w.name}</strong>
              <span className="text-xs text-muted-foreground">{w.code}</span>
              {w.address?.city ? <span className="text-xs text-muted-foreground">{w.address.city}{w.address.state ? `/${w.address.state}` : ''}</span> : null}
              {w.is_default ? <Badge>{t('warehouses.default')}</Badge> : null}
              {!w.active ? <Badge variant="muted">{t('common.inactive')}</Badge> : null}
              {canWrite ? (
                <span className="ml-auto space-x-1">
                  {!w.is_default && w.active ? (
                    <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => run(m.update.mutateAsync({ id: w.id, is_default: true }))}>
                      {t('warehouses.make_default')}
                    </Button>
                  ) : null}
                  {!w.is_default ? (
                    <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => run(m.update.mutateAsync({ id: w.id, active: !w.active }))}>
                      {w.active ? t('warehouses.deactivate') : t('warehouses.activate')}
                    </Button>
                  ) : null}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      <FormError message={err} />
      {canWrite ? (
        <form onSubmit={create} className="grid gap-2 rounded-md border p-3 sm:grid-cols-5" aria-label={t('warehouses.new')}>
          <Field label={t('warehouses.name')} required><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label={t('warehouses.code')} required><Input value={code} onChange={(e) => setCode(e.target.value)} /></Field>
          <Field label={t('warehouses.city')}><Input value={city} onChange={(e) => setCity(e.target.value)} /></Field>
          <Field label={t('warehouses.state')}><Input value={uf} maxLength={2} onChange={(e) => setUf(e.target.value)} /></Field>
          <div className="flex items-end">
            <Button type="submit" variant="primary" disabled={m.create.isPending}>{m.create.isPending ? t('common.saving') : t('warehouses.new')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
