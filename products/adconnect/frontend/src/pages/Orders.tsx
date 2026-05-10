/**
 * Orders — Phase 7 SKELETON.
 *
 * Distributor order history list. Routes to OrderDetail on click.
 */
import { useNavigate } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { useOrders } from "@/hooks/useOrders";
import type { OrderStatus } from "@/types";

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR");
}

const statusLabel: Record<OrderStatus, string> = {
  rascunho: "Rascunho",
  enviado: "Enviado",
  confirmado: "Confirmado",
  enviado_para_entrega: "Em transporte",
  entregue: "Entregue",
  cancelado: "Cancelado",
};

const statusClass: Record<OrderStatus, string> = {
  rascunho: "bg-muted text-muted-foreground",
  enviado: "bg-primary/10 text-primary",
  confirmado: "bg-primary/10 text-primary",
  enviado_para_entrega: "bg-warning/10 text-warning",
  entregue: "bg-success/10 text-success",
  cancelado: "bg-destructive/10 text-destructive",
};

export default function Orders() {
  const navigate = useNavigate();
  const { data: orders, isLoading, error } = useOrders();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ClipboardList className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Meus pedidos</h1>
          <p className="text-sm text-muted-foreground">
            Histórico de pedidos e status de entrega
          </p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Carregando…</p>}
      {error && <p className="text-sm text-destructive">Erro: {error.message}</p>}

      {!isLoading && orders.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed bg-muted/30 p-12 text-center space-y-3">
          <ClipboardList className="h-10 w-10 text-muted-foreground/40 mx-auto" />
          <p className="text-sm text-muted-foreground">
            Você ainda não fez nenhum pedido.
          </p>
          <button
            onClick={() => navigate("/catalog")}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
          >
            Ver catálogo
          </button>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Pedido</th>
                <th className="text-left px-4 py-3 font-medium">Data</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-right px-4 py-3 font-medium">Itens</th>
                <th className="text-right px-4 py-3 font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr
                  key={o.id}
                  className="border-t border-border hover:bg-muted/30 cursor-pointer"
                  onClick={() => navigate(`/orders/${o.id}`)}
                >
                  <td className="px-4 py-3 font-mono text-xs">{o.id}</td>
                  <td className="px-4 py-3">{formatDate(o.created_at)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${statusClass[o.status]}`}
                    >
                      {statusLabel[o.status]}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">{o.items.length}</td>
                  <td className="px-4 py-3 text-right font-semibold">
                    {formatBRL(o.total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
