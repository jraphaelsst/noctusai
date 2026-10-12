/** `<CouponsEditor/>` — coupon CRUD (CONTRACT §3). `fixed` values are typed in BRL and sent as cents. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError, Select } from './controls';
import { useCommerceT } from './i18n';
import { centsToInput, formatCents, parseMoneyToCents } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import { COUPON_KINDS, type Coupon, type CouponKind } from './types';

export interface CouponsEditorProps {
  hooks: CommerceHooks;
  locale?: string;
  currency?: string;
}

const toLocalInput = (iso: string | null) => (iso ? iso.slice(0, 10) : '');
const fromDateInput = (d: string) => (d ? new Date(`${d}T00:00:00Z`).toISOString() : null);

export function CouponsEditor({ hooks, locale, currency = 'BRL' }: CouponsEditorProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const coupons = hooks.useCoupons();
  const m = hooks.useCouponMutations();

  const [editing, setEditing] = React.useState<Coupon | 'new' | null>(null);
  const [code, setCode] = React.useState('');
  const [kind, setKind] = React.useState<CouponKind>('percent');
  const [value, setValue] = React.useState('');
  const [startsAt, setStartsAt] = React.useState('');
  const [endsAt, setEndsAt] = React.useState('');
  const [maxUses, setMaxUses] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);

  function open(c: Coupon | null) {
    setEditing(c ?? 'new');
    setCode(c?.code ?? '');
    setKind(c?.kind ?? 'percent');
    setValue(c ? (c.kind === 'fixed' ? centsToInput(c.value) : String(c.value)) : '');
    setStartsAt(toLocalInput(c?.starts_at ?? null));
    setEndsAt(toLocalInput(c?.ends_at ?? null));
    setMaxUses(c?.max_uses != null ? String(c.max_uses) : '');
    setErr(null);
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    let v: number | null;
    if (kind === 'percent') {
      v = /^[0-9]+$/.test(value) ? Number(value) : null;
      if (v === null || v < 1 || v > 100) {
        setErr(t('coupon.percent_invalid'));
        return;
      }
    } else {
      v = parseMoneyToCents(value);
      if (v === null || v <= 0) {
        setErr(t('offer.price_invalid'));
        return;
      }
    }
    if (!code.trim()) {
      setErr(t('common.required'));
      return;
    }
    setErr(null);
    const body = {
      code: code.trim().toUpperCase(),
      kind,
      value: v,
      starts_at: fromDateInput(startsAt),
      ends_at: fromDateInput(endsAt),
      max_uses: maxUses ? Number(maxUses) : null,
    };
    try {
      if (editing === 'new') await m.create.mutateAsync(body);
      else if (editing) await m.update.mutateAsync({ id: editing.id, ...body });
      setEditing(null);
    } catch {
      // Surfaced via mutation errors below.
    }
  }

  if (coupons.showSkeleton) return <ListSkeleton />;
  if (coupons.isError && !coupons.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(coupons.error)}`} onRetry={() => coupons.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = coupons.data ?? [];
  const mutErr = m.create.error ?? m.update.error ?? m.remove.error;

  return (
    <section className="space-y-3" aria-busy={coupons.isRefreshing}>
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{t('coupon.title')}</h2>
        <Button size="sm" onClick={() => open(null)}>{t('coupon.add')}</Button>
      </div>
      <RefreshingBar active={coupons.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />
      {list.length === 0 && editing === null ? <EmptyState message={t('coupon.empty')} /> : null}
      <ul className="divide-y rounded-md border">
        {list.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <span>
              <span className="font-mono font-medium">{c.code}</span>{' '}
              {c.kind === 'percent' ? `${c.value}%` : formatCents(c.value, currency, loc)}{' '}
              <span className="text-xs text-muted-foreground">
                {c.uses_count}/{c.max_uses ?? '∞'}
              </span>{' '}
              <Badge variant={c.active ? 'default' : 'muted'}>{c.active ? t('common.active') : t('common.inactive')}</Badge>
            </span>
            <span className="flex gap-1">
              <Button size="sm" variant="ghost" onClick={() => open(c)}>{t('common.edit')}</Button>
              <Button size="sm" variant="ghost" disabled={m.update.isPending} onClick={() => m.update.mutate({ id: c.id, active: !c.active })}>
                {c.active ? t('offer.deactivate') : t('offer.activate')}
              </Button>
              <Button size="sm" variant="ghost" disabled={m.remove.isPending} onClick={() => m.remove.mutate(c.id)}>{t('common.remove')}</Button>
            </span>
          </li>
        ))}
      </ul>
      {editing !== null ? (
        <form onSubmit={submit} className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" noValidate>
          <Field label={t('coupon.code')} required>
            <Input value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <Field label={t('coupon.kind')}>
            <Select value={kind} onChange={(e) => setKind(e.target.value as CouponKind)}>
              {COUPON_KINDS.map((k) => (
                <option key={k} value={k}>{t(`coupon_kind.${k}`)}</option>
              ))}
            </Select>
          </Field>
          <Field label={kind === 'percent' ? t('coupon.value_percent') : t('coupon.value_fixed')} required error={err}>
            <Input inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
          <Field label={t('coupon.starts_at')}>
            <Input type="date" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          </Field>
          <Field label={t('coupon.ends_at')}>
            <Input type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          </Field>
          <Field label={t('coupon.max_uses')}>
            <Input inputMode="numeric" value={maxUses} onChange={(e) => setMaxUses(e.target.value.replace(/\D/g, ''))} />
          </Field>
          <div className="flex gap-2 sm:col-span-3">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>{t('common.save')}</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
