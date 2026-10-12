/** `<ProductGrid/>` — the public catalog (search + pagination) over `GET /api/storefront/catalog`. */
import * as React from 'react';
import { Button } from '../design-system/ui/Button';
import { Skeleton } from '../design-system/ui/Skeleton';
import { EmptyState, Input, RefreshingBar, RetryError } from './controls';
import { useCommerceT } from './i18n';
import { errorMessage, type CommerceHooks } from './hooks';
import { ProductCard } from './ProductCard';
import type { CatalogItem } from './types';

export interface ProductGridProps {
  hooks: CommerceHooks;
  locale?: string;
  category?: string;
  onOpen?: (item: CatalogItem) => void;
}

export function ProductGrid({ hooks, locale, category, onOpen }: ProductGridProps) {
  const { t } = useCommerceT(locale);
  const [q, setQ] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [page, setPage] = React.useState(1);
  React.useEffect(() => {
    const h = setTimeout(() => {
      setDebounced(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const catalog = hooks.useCatalog({ category, q: debounced, page });

  if (catalog.showSkeleton) {
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4" data-testid="catalog-loading">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} height={220} width="100%" announce={i === 0} />
        ))}
      </div>
    );
  }
  if (catalog.isError && !catalog.data) {
    return <RetryError message={`${t('common.error_loading')}: ${errorMessage(catalog.error)}`} onRetry={() => catalog.refetch()} retryLabel={t('common.retry')} />;
  }
  const items = catalog.data?.data ?? [];
  const pg = catalog.data?.pagination;
  const totalPages = pg ? (pg.total_pages ?? Math.max(1, Math.ceil(pg.total / pg.page_size))) : 1;

  return (
    <section className="space-y-4" aria-busy={catalog.isRefreshing}>
      <Input type="search" aria-label={t('catalog.search')} placeholder={t('catalog.search')} value={q} onChange={(e) => setQ(e.target.value)} />
      <RefreshingBar active={catalog.isRefreshing} label={t('common.refreshing')} />
      {items.length === 0 ? (
        <EmptyState message={debounced ? t('catalog.empty_search') : t('catalog.empty')} />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {items.map((it) => (
            <ProductCard key={it.id} item={it} onOpen={onOpen} locale={locale} />
          ))}
        </div>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-center gap-2 text-sm">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
          <span>{page} / {totalPages}</span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </div>
      ) : null}
    </section>
  );
}
