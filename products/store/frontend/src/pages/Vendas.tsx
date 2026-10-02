/** `/admin/vendas` — orders table (GET /api/admin/pedidos) + "Reenviar e-mail". */
import { toast } from "sonner";
import { Badge, Button, EmptyState, ErrorState, TableSkeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AccessDenied, isForbidden } from "@/components/AccessDenied";
import { usePedidosAdmin, useReenviar } from "@/hooks/useStore";
import { formatBRL, type PedidoStatus } from "@/lib/api";

const STATUS: Record<PedidoStatus, { label: string; variant: BadgeVariant }> = {
  pago: { label: "Pago", variant: "default" },
  pendente: { label: "Pendente", variant: "muted" },
  reembolsado: { label: "Reembolsado", variant: "outline" },
  falhou: { label: "Falhou", variant: "destructive" },
};

const fmtDate = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

export default function Vendas() {
  const { data, error, showSkeleton, isRefreshing, isError } = usePedidosAdmin();
  const reenviar = useReenviar();

  if (isForbidden(error)) return <AccessDenied />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Vendas</h1>
          <p className="text-sm text-muted-foreground">Pedidos mais recentes primeiro.</p>
        </div>
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>

      {showSkeleton ? (
        <TableSkeleton rows={6} columns={7} />
      ) : isError && !data ? (
        <ErrorState message="Não foi possível carregar as vendas." />
      ) : !data || data.length === 0 ? (
        <EmptyState message="Nenhuma venda ainda." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                {["Data", "Nome", "E-mail", "Valor", "Status", "E-mail enviado", "Downloads", ""].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} className="border-t border-border">
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDate(p.created_at)}</td>
                  <td className="px-3 py-2">{p.nome}</td>
                  <td className="px-3 py-2 break-all">{p.email}</td>
                  <td className="px-3 py-2 tabular-nums whitespace-nowrap">{formatBRL(p.valor_cents)}</td>
                  <td className="px-3 py-2"><Badge variant={STATUS[p.status]?.variant ?? "muted"}>{STATUS[p.status]?.label ?? p.status}</Badge></td>
                  <td className="px-3 py-2 whitespace-nowrap">{fmtDate(p.email_enviado_em)}</td>
                  <td className="px-3 py-2 tabular-nums">{p.downloads}</td>
                  <td className="px-3 py-2">
                    {p.status === "pago" && (
                      <Button variant="outline" size="sm" disabled={reenviar.isPending && reenviar.variables === p.id}
                        onClick={() => reenviar.mutate(p.id, {
                          onSuccess: () => toast.success(`E-mail reenviado para ${p.email}.`),
                          onError: () => toast.error("Não foi possível reenviar o e-mail."),
                        })}>
                        Reenviar e-mail
                      </Button>
                    )}
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
