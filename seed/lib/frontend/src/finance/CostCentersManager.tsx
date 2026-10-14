/** `<CostCentersManager/>` — centros de custo (code unique per org) with create / edit / deactivate. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Field, FormError, Input, ListSkeleton, PageHeader, RefreshingBar, RetryError } from './controls';
import { errorMessage, type FinanceHooks } from './hooks';
import { t } from './i18n';
import type { CostCenter } from './types';

export interface CostCentersManagerProps {
  hooks: FinanceHooks;
  isAdmin?: boolean;
}

export function CostCentersManager({ hooks, isAdmin = false }: CostCentersManagerProps) {
  const list = hooks.useCostCenters();
  const m = hooks.useCostCenterMutations();
  const [editing, setEditing] = React.useState<CostCenter | 'new' | null>(null);
  const [code, setCode] = React.useState('');
  const [name, setName] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  function open(c: CostCenter | null) {
    setEditing(c ?? 'new');
    setCode(c?.code ?? '');
    setName(c?.name ?? '');
    setErrors({});
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const next: Record<string, string> = {};
    if (!code.trim()) next.code = t('common.required');
    if (!name.trim()) next.name = t('common.required');
    setErrors(next);
    if (Object.keys(next).length) return;
    try {
      if (editing === 'new') await m.create.mutateAsync({ code: code.trim(), name: name.trim() });
      else if (editing) await m.update.mutateAsync({ id: editing.id, code: code.trim(), name: name.trim() });
      setEditing(null);
    } catch {
      // Surfaced below.
    }
  }

  if (list.showSkeleton) return <ListSkeleton />;
  if (list.isError && !list.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(list.error)}`} onRetry={() => list.refetch()} retryLabel={t('common.retry')} />;
  }
  const rows = list.data ?? [];
  const mutErr = m.create.error ?? m.update.error;

  return (
    <section className="space-y-3" aria-busy={list.isRefreshing}>
      <PageHeader
        title={t('cost_centers.title')}
        subtitle={t('cost_centers.subtitle')}
        actions={isAdmin ? <Button size="sm" onClick={() => open(null)}>{t('cost_centers.add')}</Button> : undefined}
      />
      <RefreshingBar active={list.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {rows.length === 0 && editing === null ? <EmptyState message={t('cost_centers.empty')} /> : null}
      <ul className="divide-y rounded-md border">
        {rows.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-2 p-3 text-sm">
            <span className={c.active ? '' : 'text-muted-foreground line-through'}>
              <strong>{c.code}</strong> · {c.name}
            </span>
            {isAdmin ? (
              <span className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => open(c)}>{t('common.edit')}</Button>
                <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => m.update.mutate({ id: c.id, active: !c.active })}>
                  {c.active ? t('common.deactivate') : t('common.activate')}
                </Button>
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {isAdmin && editing !== null ? (
        <form onSubmit={submit} noValidate className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" aria-label={t('cost_centers.form')}>
          <Field label={t('cost_centers.code')} required error={errors.code}>
            <Input value={code} onChange={(e) => setCode(e.target.value)} maxLength={30} />
          </Field>
          <Field label={t('cost_centers.name')} required error={errors.name}>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>{t('common.save')}</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
