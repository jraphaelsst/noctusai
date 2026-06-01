/**
 * Cart — Phase 7 SKELETON.
 *
 * Cart line items + edit (qty change / remove). Checkout button routes to
 * /checkout. Mock data renders the empty-state path.
 */
import { useNavigate } from "react-router-dom";
import { ShoppingCart, Trash2 } from "lucide-react";
import { useCart, useCartMutations } from "@/hooks/useCart";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

export default function Cart() {
  const navigate = useNavigate();
  const { data: cart, isLoading, error } = useCart();
  const { updateItem, removeItem } = useCartMutations();

  if (isLoading) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (error) return <p className="text-sm text-destructive">Erro: {error.message}</p>;

  const items = cart?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ShoppingCart className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Carrinho</h1>
          <p className="text-sm text-muted-foreground">
            Revise os itens antes de finalizar o pedido
          </p>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed bg-muted/30 p-12 text-center space-y-3">
          <ShoppingCart className="h-10 w-10 text-muted-foreground/40 mx-auto" />
          <p className="text-sm text-muted-foreground">Seu carrinho está vazio.</p>
          <button
            onClick={() => navigate("/catalog")}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
          >
            Ver catálogo
          </button>
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border bg-card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">Produto</th>
                  <th className="text-right px-4 py-3 font-medium">Preço unit.</th>
                  <th className="text-center px-4 py-3 font-medium">Quantidade</th>
                  <th className="text-right px-4 py-3 font-medium">Subtotal</th>
                  <th className="px-4 py-3 w-10" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-border">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">
                        {item.product?.name ?? item.product_id}
                      </div>
                      {item.product?.sku && (
                        <div className="text-xs font-mono text-muted-foreground">
                          {item.product.sku}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {formatBRL(item.price_at_add)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <input
                        type="number"
                        min={1}
                        value={item.quantity}
                        onChange={(e) =>
                          updateItem.mutate({ id: item.id, quantidade: Number(e.target.value) })
                        }
                        className="w-20 px-2 py-1 rounded-md border border-border bg-background text-center text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </td>
                    <td className="px-4 py-3 text-right font-semibold">
                      {formatBRL(item.price_at_add * item.quantity)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        type="button"
                        onClick={() => removeItem.mutate(item.id)}
                        className="p-1 rounded hover:bg-destructive/10 text-destructive"
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-6">
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Total</p>
              <p className="text-2xl font-bold text-foreground">
                {formatBRL(cart?.total ?? 0)}
              </p>
            </div>
            <button
              onClick={() => navigate("/checkout")}
              className="px-6 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90"
            >
              Finalizar pedido
            </button>
          </div>
        </>
      )}
    </div>
  );
}
