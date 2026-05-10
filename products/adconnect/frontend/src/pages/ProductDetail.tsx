/**
 * ProductDetail — Phase 7 SKELETON.
 *
 * Single-product detail with quantity selector + add-to-cart placeholder.
 */
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Package, ShoppingCart } from "lucide-react";
import { useProduct } from "@/hooks/useCatalog";
import { useCartMutations } from "@/hooks/useCart";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

export default function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: product, isLoading, error } = useProduct(id);
  const { addItem } = useCartMutations();
  const [quantity, setQuantity] = useState(1);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Carregando…</p>;
  }
  if (error) {
    return <p className="text-sm text-destructive">Erro: {error.message}</p>;
  }
  if (!product) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-4 w-4" /> Voltar
        </button>
        <p className="text-sm text-muted-foreground">Produto não encontrado.</p>
      </div>
    );
  }

  const minOrder = product.min_order ?? 1;
  const multiple = product.multiple ?? 1;
  const unitPrice = product.preferential_price ?? product.base_price;

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate(-1)}
        className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
      >
        <ArrowLeft className="h-4 w-4" /> Voltar para o catálogo
      </button>

      <div className="grid gap-6 grid-cols-1 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-8 flex items-center justify-center">
          <Package className="h-32 w-32 text-muted-foreground/40" />
        </div>

        <div className="space-y-4">
          <div>
            <p className="text-xs font-mono text-muted-foreground">{product.sku}</p>
            <h1 className="text-2xl font-bold text-foreground">{product.name}</h1>
            {product.brand && (
              <p className="text-sm text-muted-foreground">{product.brand}</p>
            )}
          </div>

          {product.description && (
            <p className="text-sm text-muted-foreground">{product.description}</p>
          )}

          <div className="rounded-md border border-border bg-muted/30 p-4 space-y-2">
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-muted-foreground">Seu preço</span>
              <span className="text-2xl font-bold text-primary">
                {formatBRL(unitPrice)}
              </span>
            </div>
            {product.preferential_price &&
              product.preferential_price < product.base_price && (
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground">Preço de tabela</span>
                  <span className="text-sm line-through text-muted-foreground">
                    {formatBRL(product.base_price)}
                  </span>
                </div>
              )}
            {product.cashback_percent && (
              <div className="text-xs text-success">
                Cashback: {product.cashback_percent}%
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Quantidade (mínimo {minOrder}, múltiplo de {multiple})
            </label>
            <input
              type="number"
              min={minOrder}
              step={multiple}
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="w-32 px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <button
            type="button"
            disabled={!product.in_stock}
            onClick={() => addItem(product.id, quantity)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ShoppingCart className="h-4 w-4" />
            Adicionar ao carrinho
          </button>
        </div>
      </div>
    </div>
  );
}
