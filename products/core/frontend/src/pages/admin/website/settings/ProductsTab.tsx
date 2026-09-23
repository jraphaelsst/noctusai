/**
 * Produtos tab — order (up/down buttons — dnd-kit is available but a11y-free
 * buttons are the more testable, more accessible choice for a short list),
 * visible, state, pt/EN tagline override (contract §2 `products[]` / §6
 * "Produtos (curated)").
 */
import { ArrowDown, ArrowUp } from 'lucide-react';
import { Input } from '@noctusai/lib/design-system';
import type { ProductState, WebsiteProductEntry } from '../../../../lib/website';
import type { SettingsTabProps } from './types';

const STATE_LABEL: Record<ProductState, string> = {
  disponivel: 'Disponível',
  lista_de_espera: 'Lista de espera',
  em_breve: 'Em breve',
};

function sortedByOrder(products: WebsiteProductEntry[]): WebsiteProductEntry[] {
  return [...products].sort((a, b) => a.order - b.order);
}

/** Re-numbers `order` 0..n-1 after a swap, so `order` always matches array
 * position — the backend validates shape only (contract §2), never
 * gap-fills, so the FE must keep it dense. */
function renumber(products: WebsiteProductEntry[]): WebsiteProductEntry[] {
  return products.map((p, i) => ({ ...p, order: i }));
}

export function ProductsTab({ draft, onChange }: SettingsTabProps) {
  const products = sortedByOrder(draft.products);

  function move(slug: string, direction: -1 | 1) {
    onChange((prev) => {
      const list = sortedByOrder(prev.products);
      const index = list.findIndex((p) => p.slug === slug);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= list.length) return prev;
      const swapped = [...list];
      [swapped[index], swapped[target]] = [swapped[target], swapped[index]];
      return { ...prev, products: renumber(swapped) };
    });
  }

  function patch(slug: string, patchFn: (p: WebsiteProductEntry) => WebsiteProductEntry) {
    onChange((prev) => ({
      ...prev,
      products: prev.products.map((p) => (p.slug === slug ? patchFn(p) : p)),
    }));
  }

  if (products.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Nenhum produto configurado.</p>;
  }

  return (
    <div className="space-y-3">
      {products.map((product, i) => (
        <div key={product.slug} className="rounded-lg border border-border bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="flex flex-col">
                <button
                  type="button"
                  aria-label={`Mover ${product.slug} para cima`}
                  disabled={i === 0}
                  onClick={() => move(product.slug, -1)}
                  className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
                >
                  <ArrowUp className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  aria-label={`Mover ${product.slug} para baixo`}
                  disabled={i === products.length - 1}
                  onClick={() => move(product.slug, 1)}
                  className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
                >
                  <ArrowDown className="h-3.5 w-3.5" />
                </button>
              </div>
              <span className="font-medium text-foreground">{product.slug}</span>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                aria-label={`Visível: ${product.slug}`}
                checked={product.visible}
                onChange={(e) => patch(product.slug, (p) => ({ ...p, visible: e.target.checked }))}
              />
              Visível
            </label>
            <select
              aria-label={`Estado: ${product.slug}`}
              className="rounded-md border border-input bg-background px-2 py-1 text-sm"
              value={product.state}
              onChange={(e) => patch(product.slug, (p) => ({ ...p, state: e.target.value as ProductState }))}
            >
              {(Object.keys(STATE_LABEL) as ProductState[]).map((s) => (
                <option key={s} value={s}>{STATE_LABEL[s]}</option>
              ))}
            </select>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Input
              aria-label={`Tagline pt-BR: ${product.slug}`}
              placeholder="Tagline (pt-BR) — opcional"
              value={product.tagline?.pt ?? ''}
              onChange={(e) =>
                patch(product.slug, (p) => ({
                  ...p,
                  tagline: { pt: e.target.value, en: p.tagline?.en ?? '' },
                }))
              }
            />
            <Input
              aria-label={`Tagline EN: ${product.slug}`}
              placeholder="Tagline (EN) — opcional"
              value={product.tagline?.en ?? ''}
              onChange={(e) =>
                patch(product.slug, (p) => ({
                  ...p,
                  tagline: { pt: p.tagline?.pt ?? '', en: e.target.value },
                }))
              }
            />
          </div>
        </div>
      ))}
    </div>
  );
}
