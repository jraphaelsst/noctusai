/** `<ProductCard/>` — one catalog tile: media, title, "from" price. */
import { formatCents } from './format';
import { useCommerceT } from './i18n';
import type { CatalogItem } from './types';

export interface ProductCardProps {
  item: CatalogItem;
  onOpen?: (item: CatalogItem) => void;
  locale?: string;
}

export function ProductCard({ item, onOpen, locale }: ProductCardProps) {
  const { t, locale: loc } = useCommerceT(locale);
  const prices = item.offers.map((o) => o.price_cents);
  const from = prices.length ? Math.min(...prices) : null;
  const currency = item.offers[0]?.currency ?? 'BRL';
  return (
    <button
      type="button"
      onClick={() => onOpen?.(item)}
      className="flex flex-col overflow-hidden rounded-lg border text-left transition hover:shadow-md"
      style={{ borderColor: 'var(--commerce-secondary, #e2e8f0)' }}
    >
      {item.media_url ? (
        <img src={item.media_url} alt={item.title} className="aspect-square w-full object-cover" loading="lazy" />
      ) : (
        <div className="flex aspect-square w-full items-center justify-center bg-muted text-xs text-muted-foreground">{t('product.no_image')}</div>
      )}
      <div className="space-y-1 p-3">
        <h3 className="text-sm font-medium">{item.title}</h3>
        <p className="text-sm" style={{ color: 'var(--commerce-primary, #4f46e5)' }}>
          {from === null ? t('product.unavailable') : `${prices.length > 1 ? t('product.from') + ' ' : ''}${formatCents(from, currency, loc)}`}
        </p>
      </div>
    </button>
  );
}
