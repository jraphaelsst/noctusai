/** `<ItemCategoryManager/>` — category tree CRUD on one page (`/api/items/categories`). */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { errorMessage, type ItemsHooks } from './hooks';
import { itemsT as t } from './messages';
import type { ItemCategory } from './types';

export interface ItemCategoryManagerProps {
  hooks: ItemsHooks;
  /** Staff without write access (`false`) get a read-only tree. Default `true`; the server is the authority. */
  canWrite?: boolean;
}

/** Depth-first rows `[category, depth]`, siblings by name; orphans (parent not in list) become roots. */
export function flattenCategories(list: ItemCategory[]): Array<[ItemCategory, number]> {
  const ids = new Set(list.map((c) => c.id));
  const byParent = new Map<string | null, ItemCategory[]>();
  for (const c of list) {
    const key = c.parent_id && ids.has(c.parent_id) ? c.parent_id : null;
    byParent.set(key, [...(byParent.get(key) ?? []), c]);
  }
  const out: Array<[ItemCategory, number]> = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const c of (byParent.get(parent) ?? []).sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))) {
      if (seen.has(c.id)) continue;
      seen.add(c.id);
      out.push([c, depth]);
      walk(c.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

function descendantsOf(list: ItemCategory[], id: string): Set<string> {
  const out = new Set<string>([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of list) {
      if (c.parent_id && out.has(c.parent_id) && !out.has(c.id)) {
        out.add(c.id);
        grew = true;
      }
    }
  }
  return out;
}

export function ItemCategoryManager({ hooks, canWrite = true }: ItemCategoryManagerProps) {
  const cats = hooks.useItemCategories();
  const m = hooks.useItemCategoryMutations();
  const [editing, setEditing] = React.useState<ItemCategory | 'new' | null>(null);
  const [name, setName] = React.useState('');
  const [parent, setParent] = React.useState('');
  const [confirmId, setConfirmId] = React.useState<string | null>(null);

  function open(c: ItemCategory | null) {
    setEditing(c ?? 'new');
    setName(c?.name ?? '');
    setParent(c?.parent_id ?? '');
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!name.trim()) return;
    try {
      if (editing === 'new') await m.create.mutateAsync({ name: name.trim(), parent_id: parent || null });
      else if (editing) await m.update.mutateAsync({ id: editing.id, name: name.trim(), parent_id: parent || null });
      setEditing(null);
    } catch {
      // Surfaced via the mutation errors below.
    }
  }

  if (cats.showSkeleton) return <ListSkeleton />;
  if (cats.isError && !cats.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(cats.error)}`} onRetry={() => cats.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = cats.data ?? [];
  const rows = flattenCategories(list);
  const blocked = editing && editing !== 'new' ? descendantsOf(list, editing.id) : new Set<string>();
  const mutErr = m.create.error ?? m.update.error ?? m.remove.error;

  return (
    <section className="space-y-3" aria-busy={cats.isRefreshing}>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{t('category.title')}</h2>
        {canWrite ? <Button size="sm" onClick={() => open(null)}>{t('category.add')}</Button> : null}
      </div>
      <RefreshingBar active={cats.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {rows.length === 0 && editing === null ? <EmptyState message={t('category.empty')} /> : null}
      <ul className="divide-y rounded-md border">
        {rows.map(([c, depth]) => (
          <li key={c.id} className="flex items-center justify-between gap-2 p-3 text-sm">
            <span style={{ paddingLeft: depth * 16 }}>
              {c.name} {!c.is_active ? <Badge variant="muted">{t('category.archived')}</Badge> : null}
            </span>
            {canWrite ? (
              <span className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => open(c)}>{t('common.edit')}</Button>
                {confirmId === c.id ? (
                  <>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={m.remove.isPending}
                      onClick={async () => {
                        try {
                          await m.remove.mutateAsync(c.id);
                          setConfirmId(null);
                        } catch {
                          // Surfaced via `m.remove.error` above (e.g. 409 categoria_em_uso).
                        }
                      }}
                    >
                      {t('common.confirm')}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmId(null)}>{t('common.cancel')}</Button>
                  </>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => setConfirmId(c.id)}>{t('common.remove')}</Button>
                )}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {editing !== null && canWrite ? (
        <form onSubmit={submit} className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" noValidate>
          <Field label={t('category.name')} required>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t('category.parent')}>
            <Select value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">{t('category.no_parent')}</option>
              {rows.filter(([c]) => !blocked.has(c.id)).map(([c, depth]) => (
                <option key={c.id} value={c.id}>{`${'— '.repeat(depth)}${c.name}`}</option>
              ))}
            </Select>
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>
              {m.create.isPending || m.update.isPending ? t('common.saving') : t('common.save')}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
