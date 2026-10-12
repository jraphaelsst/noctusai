/** `<StorefrontProductPage/>` — one public product: gallery, description, offer picker, add to cart. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { EmptyState, ListSkeleton, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { formatCents } from './format';
import { apiErrorStatus, errorMessage, type CommerceHooks } from './hooks';
import type { CartApi } from './cartState';

export interface StorefrontProductPageProps {
  hooks: CommerceHooks;
  slug: string;
  cart: Pick<CartApi, 'add'>;
  locale?: string;
  /** Called after "add to cart" (e.g. open the cart). */
  onAdded?: () => void;
}

export function StorefrontProductPage({ hooks, slug, cart, locale, onAdded }: StorefrontProductPageProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const product = hooks.useStorefrontProduct(slug);
  const [offerId, setOfferId] = React.useState<string | null>(null);
  const [imgIdx, setImgIdx] = React.useState(0);

  const p = product.data;
  React.useEffect(() => {
    if (p && !p.offers.some((o) => o.id === offerId)) setOfferId(p.offers[0]?.id ?? null);
  }, [p, offerId]);

  if (product.showSkeleton) return <ListSkeleton rows={4} />;
  if (apiErrorStatus(product.error) === 404) return <EmptyState message={t('product.not_found')} />;
  if (product.isError && !p) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(product.error)}`} onRetry={() => product.refetch()} retryLabel={t('common.retry')} />;
  }
  if (!p) return <EmptyState message={t('product.not_found')} />;

  const offer = p.offers.find((o) => o.id === offerId) ?? p.offers[0];
  const images = p.media.filter((m) => m.kind === 'image');
  const main = images[Math.min(imgIdx, Math.max(images.length - 1, 0))];

  return (
    <article className="grid gap-6 md:grid-cols-2" aria-busy={product.isRefreshing}>
      <div className="space-y-2">
        {main ? <img src={main.url} alt={main.alt || p.title} className="w-full rounded-lg object-cover" /> : <div className="flex aspect-square items-center justify-center rounded-lg bg-muted text-sm">{t('product.no_image')}</div>}
        {images.length > 1 ? (
          <div className="flex gap-2">
            {images.map((m, i) => (
              <button key={m.id} type="button" aria-label={`${t('product.image')} ${i + 1}`} onClick={() => setImgIdx(i)}>
                <img src={m.url} alt="" className="h-14 w-14 rounded object-cover" />
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">{p.title}</h1>
        {p.description ? <p className="whitespace-pre-line text-sm">{p.description}</p> : null}
        {p.offers.length === 0 ? (
          <EmptyState message={t('product.unavailable')} />
        ) : (
          <>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">{t('product.choose_offer')}</legend>
              {p.offers.map((o) => (
                <label key={o.id} className="flex cursor-pointer items-center gap-2 rounded-md border p-2 text-sm">
                  <input type="radio" name="offer" checked={offer?.id === o.id} onChange={() => setOfferId(o.id)} />
                  <span className="flex-1">{o.name}</span>
                  <span className="font-medium">{formatCents(o.price_cents, o.currency, loc)}</span>
                </label>
              ))}
            </fieldset>
            <Button
              disabled={!offer}
              onClick={() => {
                if (!offer) return;
                cart.add({
                  offer_id: offer.id,
                  product_slug: p.slug,
                  title: p.title,
                  offer_name: offer.name,
                  unit_price_cents: offer.price_cents,
                  currency: offer.currency,
                });
                onAdded?.();
              }}
            >
              {t('cart.add')}
            </Button>
          </>
        )}
      </div>
    </article>
  );
}
