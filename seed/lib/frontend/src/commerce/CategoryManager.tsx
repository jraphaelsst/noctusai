/** `<CategoryManager/>` — flat/nested category CRUD on one page (CONTRACT §3 categories API). */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { useCommerceT } from './i18n';
import { slugify } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import type { Category } from './types';

export interface CategoryManagerProps {
  hooks: CommerceHooks;
  locale?: string;
}

export function CategoryManager({ hooks, locale }: CategoryManagerProps) {
  const { t } = useCommerceT(locale);
  const cats = hooks.useCategories();
  const m = hooks.useCategoryMutations();

  const [editing, setEditing] = React.useState<Category | 'new' | null>(null);
  const [name, setName] = React.useState('');
  const [slug, setSlug] = React.useState('');
  const [parent, setParent] = React.useState('');
  const [confirmId, setConfirmId] = React.useState<string | null>(null);

  function open(c: Category | null) {
    setEditing(c ?? 'new');
    setName(c?.name ?? '');
    setSlug(c?.slug ?? '');
    setParent(c?.parent_id ?? '');
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!name.trim() || !slug.trim()) return;
    const body = { name: name.trim(), slug: slug.trim(), parent_id: parent || null };
    try {
      if (editing === 'new') await m.create.mutateAsync(body);
      else if (editing) await m.update.mutateAsync({ id: editing.id, ...body });
      setEditing(null);
    } catch {
      // Surfaced via mutation errors below.
    }
  }

  if (cats.showSkeleton) return <ListSkeleton />;
  if (cats.isError && !cats.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(cats.error)}`} onRetry={() => cats.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = cats.data ?? [];
  const nameOf = (id: string | null) => list.find((c) => c.id === id)?.name;
  const mutErr = m.create.error ?? m.update.error ?? m.remove.error;

  return (
    <section className="space-y-3" aria-busy={cats.isRefreshing}>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{t('category.title')}</h2>
        <Button size="sm" onClick={() => open(null)}>{t('category.add')}</Button>
      </div>
      <RefreshingBar active={cats.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {list.length === 0 && editing === null ? <EmptyState message={t('category.empty')} /> : null}
      <ul className="divide-y rounded-md border">
        {list.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-2 p-3 text-sm">
            <span>
              {c.name} <span className="text-xs text-muted-foreground">/{c.slug}{c.parent_id ? ` · ${nameOf(c.parent_id) ?? ''}` : ''}</span>
            </span>
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
                        // Surfaced via `m.remove.error` above.
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
          </li>
        ))}
      </ul>
      {editing !== null ? (
        <form onSubmit={submit} className="grid gap-3 rounded-md border p-3 sm:grid-cols-4" noValidate>
          <Field label={t('category.name')} required>
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (editing === 'new') setSlug(slugify(e.target.value));
              }}
            />
          </Field>
          <Field label={t('category.slug')} required>
            <Input value={slug} onChange={(e) => setSlug(e.target.value)} />
          </Field>
          <Field label={t('category.parent')}>
            <Select value={parent} onChange={(e) => setParent(e.target.value)}>
              <option value="">{t('category.no_parent')}</option>
              {list.filter((c) => editing === 'new' || c.id !== editing.id).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
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
