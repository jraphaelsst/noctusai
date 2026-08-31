/**
 * Catalog — Phase 7 SKELETON.
 *
 * Distributor product browse page. Filter / search / sort UI placeholders
 * wired to local state (controlled inputs). Hook returns mock data via
 * `useCatalog` until Phase 7 PROPER swaps in real /api/products integration.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Package, Search, SlidersHorizontal } from "lucide-react";
import { useCatalog, useCategorias } from "@/hooks/useCatalog";
import type { CatalogFilters, Product } from "@/types";

const inputClass =
  "w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

export default function Catalog() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("");
  const [sortBy, setSortBy] = useState<CatalogFilters["sort_by"]>("name");
  const [inStockOnly, setInStockOnly] = useState(false);

  const { data: products, isPending, error } = useCatalog({
    search,
    category: category || undefined,
    in_stock_only: inStockOnly,
    sort_by: sortBy,
  });
  // Categorias live in their own hook (separate query), not on useCatalog.
  const { data: categorias = [] } = useCategorias();

  const filtered = useMemo<Product[]>(() => {
    let list = products;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)
      );
    }
    if (category) list = list.filter((p) => p.category === category);
    if (inStockOnly) list = list.filter((p) => p.in_stock);
    return list;
  }, [products, search, category, inStockOnly]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Package className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Catálogo</h1>
          <p className="text-sm text-muted-foreground">
            Navegue pelos produtos disponíveis com seu preço preferencial
          </p>
        </div>
      </div>

      {/* Filter / search / sort bar */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="grid gap-3 grid-cols-1 md:grid-cols-4">
          <div className="md:col-span-2 relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              type="search"
              placeholder="Buscar por nome ou SKU"
              className={`${inputClass} pl-9`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className={inputClass}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">Todas as categorias</option>
            {categorias.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
          <select
            className={inputClass}
            value={sortBy}
            onChange={(e) =>
              setSortBy(e.target.value as CatalogFilters["sort_by"])
            }
          >
            <option value="name">Nome (A-Z)</option>
            <option value="price_asc">Preço (menor)</option>
            <option value="price_desc">Preço (maior)</option>
            <option value="cashback_desc">Maior cashback</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(e) => setInStockOnly(e.target.checked)}
            className="rounded"
          />
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Somente em estoque
        </label>
      </div>

      {/* Product grid */}
      {isPending && !products && (
        <p className="text-sm text-muted-foreground">Carregando produtos…</p>
      )}
      {error && (
        <p className="text-sm text-destructive">Erro ao carregar: {error.message}</p>
      )}
      {!isPending && filtered.length === 0 && (
        <div className="rounded-lg border border-border border-dashed bg-muted/30 p-12 text-center">
          <p className="text-sm text-muted-foreground">
            Nenhum produto encontrado para os filtros aplicados.
          </p>
        </div>
      )}

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {filtered.map((p) => (
          <button
            key={p.id}
            onClick={() => navigate(`/catalog/${p.id}`)}
            className="text-left rounded-lg border border-border bg-card p-4 hover:shadow-md transition-shadow space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-muted-foreground">{p.sku}</span>
              {!p.in_stock && (
                <span className="text-xs px-2 py-0.5 rounded bg-destructive/10 text-destructive">
                  Indisponível
                </span>
              )}
            </div>
            <h3 className="font-semibold text-foreground line-clamp-2">{p.name}</h3>
            <div className="flex items-end justify-between pt-2">
              <div>
                <p className="text-xs text-muted-foreground">Seu preço</p>
                <p className="text-lg font-bold text-primary">
                  {formatBRL(p.preferential_price ?? p.base_price)}
                </p>
              </div>
              {p.cashback_percent && (
                <span className="text-xs px-2 py-1 rounded bg-success/10 text-success font-medium">
                  {p.cashback_percent}% cashback
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
