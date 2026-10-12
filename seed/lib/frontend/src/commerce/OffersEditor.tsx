/**
 * `<OffersEditor/>` — a product's offers (CONTRACT §3 offers API).
 *
 * The price is typed in BRL (`12,50`) and sent as integer cents. Each offer
 * shows the server's `fee_estimate` (Asaas list prices per method), always
 * labelled an ESTIMATE — never a promise of the actual fee.
 */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Badge } from '../design-system/ui/Badge';
import { EmptyState, Field, FormError, Input, ListSkeleton, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { centsToInput, formatCents, parseMoneyToCents } from './format';
import { errorMessage, type CommerceHooks } from './hooks';
import type { Offer } from './types';

export interface OffersEditorProps {
  hooks: CommerceHooks;
  productId: string;
  locale?: string;
}

export function OffersEditor({ hooks, productId, locale }: OffersEditorProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const offers = hooks.useOffers(productId);
  const m = hooks.useOfferMutations(productId);

  const [editingId, setEditingId] = React.useState<string | 'new' | null>(null);
  const [name, setName] = React.useState('');
  const [price, setPrice] = React.useState('');
  const [priceError, setPriceError] = React.useState<string | null>(null);

  function startEdit(o: Offer | null) {
    setEditingId(o ? o.id : 'new');
    setName(o?.name ?? '');
    setPrice(o ? centsToInput(o.price_cents) : '');
    setPriceError(null);
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    const cents = parseMoneyToCents(price);
    if (cents === null || cents <= 0) {
      setPriceError(t('offer.price_invalid'));
      return;
    }
    if (!name.trim()) {
      setPriceError(null);
      return;
    }
    setPriceError(null);
    try {
      if (editingId === 'new') await m.create.mutateAsync({ name: name.trim(), price_cents: cents });
      else if (editingId) await m.update.mutateAsync({ id: editingId, name: name.trim(), price_cents: cents });
      setEditingId(null);
    } catch {
      // Surfaced via mutation errors below.
    }
  }

  if (offers.showSkeleton) return <ListSkeleton rows={2} />;
  if (offers.isError && !offers.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(offers.error)}`} onRetry={() => offers.refetch()} retryLabel={t('common.retry')} />;
  }
  const list = offers.data ?? [];
  const mutErr = m.create.error ?? m.update.error ?? m.remove.error;

  return (
    <section className="space-y-3" aria-label={t('offer.title')} aria-busy={offers.isRefreshing}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t('offer.title')}</h3>
        <Button size="sm" variant="outline" onClick={() => startEdit(null)}>{t('offer.add')}</Button>
      </div>
      <RefreshingBar active={offers.isRefreshing} label={t('common.refreshing')} />
      <FormError message={mutErr ? errorMessage(mutErr) : null} />

      {list.length === 0 && editingId === null ? <EmptyState message={t('offer.empty')} /> : null}
      <ul className="space-y-2">
        {list.map((o) => (
          <li key={o.id} className="rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-medium">{o.name}</span>{' '}
                <span>{formatCents(o.price_cents, o.currency, loc)}</span>{' '}
                <Badge variant={o.active ? 'default' : 'muted'}>{o.active ? t('common.active') : t('common.inactive')}</Badge>
              </div>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => startEdit(o)}>{t('common.edit')}</Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={m.update.isPending}
                  onClick={() => m.update.mutate({ id: o.id, active: !o.active })}
                >
                  {o.active ? t('offer.deactivate') : t('offer.activate')}
                </Button>
                <Button size="sm" variant="ghost" disabled={m.remove.isPending} onClick={() => m.remove.mutate(o.id)}>
                  {t('common.remove')}
                </Button>
              </div>
            </div>
            {o.fee_estimate ? (
              <p className="mt-1 text-xs text-muted-foreground" data-testid="fee-estimate">
                {t('offer.fee_estimate')}: Pix {formatCents(o.fee_estimate.pix_cents, o.currency, loc)} · Boleto{' '}
                {formatCents(o.fee_estimate.boleto_cents, o.currency, loc)} · {t('payment.credit_card')}{' '}
                {formatCents(o.fee_estimate.card_cents, o.currency, loc)}
              </p>
            ) : null}
          </li>
        ))}
      </ul>

      {editingId !== null ? (
        <form onSubmit={submit} className="grid gap-3 rounded-md border p-3 sm:grid-cols-3" noValidate>
          <Field label={t('offer.name')} required>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t('offer.price')} required error={priceError}>
            <Input inputMode="decimal" placeholder="0,00" value={price} onChange={(e) => setPrice(e.target.value)} />
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit" disabled={m.create.isPending || m.update.isPending}>{t('common.save')}</Button>
            <Button type="button" variant="ghost" onClick={() => setEditingId(null)}>{t('common.cancel')}</Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
