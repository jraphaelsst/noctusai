/**
 * OrderDetail — Phase 7 SKELETON.
 *
 * Single order view: header status, line items, totals.
 */
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ClipboardList } from "lucide-react";
import { useOrder } from "@/hooks/useOrders";
import type { OrderStatus } from "@/types";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

const statusLabel: Record<OrderStatus, string> = {
  rascunho: "Rascunho",
  enviado: "Enviado",
  confirmado: "Confirmado",
  enviado_para_entrega: "Em transporte",
  entregue: "Entregue",
  cancelado: "Cancelado",
};

export default function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: order, isPending, error } = useOrder(id);

  if (isPending && !order) return <p className="text-sm text-muted-foreground">Carregando…</p>;
  if (error) return <p className="text-sm text-destructive">Erro: {error.message}</p>;

  if (!order) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate("/orders")}
          className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-4 w-4" /> Voltar
        </button>
        <p className="text-sm text-muted-foreground">Pedido não encontrado.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate("/orders")}
        className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
      >
        <ArrowLeft className="h-4 w-4" /> Voltar para pedidos
      </button>

      <div className="flex items-center gap-3">
        <ClipboardList className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground font-mono">{order.id}</h1>
          <p className="text-sm text-muted-foreground">
            {statusLabel[order.status]} · {new Date(order.created_at).toLocaleString("pt-BR")}
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-3 font-medium">Produto</th>
              <th className="text-right px-4 py-3 font-medium">Qtd.</th>
              <th className="text-right px-4 py-3 font-medium">Preço unit.</th>
              <th className="text-right px-4 py-3 font-medium">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {order.items.map((item) => (
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
                <td className="px-4 py-3 text-right">{item.quantity}</td>
                <td className="px-4 py-3 text-right">
                  {formatBRL(item.price_at_order)}
                </td>
                <td className="px-4 py-3 text-right font-semibold">
                  {formatBRL(item.price_at_order * item.quantity)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-muted/30 font-semibold">
            <tr>
              <td className="px-4 py-3" colSpan={3}>
                Total
              </td>
              <td className="px-4 py-3 text-right">{formatBRL(order.total)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
