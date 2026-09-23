/**
 * Clientes card → "Financeiro": this cliente's faturas
 * (`GET /api/financeiro/faturas?cliente_id=`), newest competência first,
 * with the totals that matter at a glance (em aberto / pago) and the
 * "Marcar como paga" action the Financeiro page also offers.
 */
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { useFaturas, useMarcarPaga, type StatusFatura } from "@/hooks/useFinanceiro";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";

const STATUS_VARIANT: Record<StatusFatura, BadgeVariant> = {
  aberta: "muted",
  enviada: "outline",
  paga: "default",
  vencida: "destructive",
  cancelada: "outline",
};

export function ClienteFinanceiro({ clienteId }: { clienteId: string }) {
  const { faturas, loading, isError, error } = useFaturas(undefined, { clienteId });
  const marcarPaga = useMarcarPaga();

  const ordenadas = [...faturas].sort((a, b) => b.competencia.localeCompare(a.competencia));
  const emAberto = faturas
    .filter((f) => f.status !== "paga" && f.status !== "cancelada")
    .reduce((s, f) => s + Number(f.valor_total || 0), 0);
  const pago = faturas.filter((f) => f.status === "paga").reduce((s, f) => s + Number(f.valor_total || 0), 0);

  if (loading) return <Skeleton className="h-32 w-full" />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {describeError(error, "Não foi possível carregar as faturas.")}
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="cliente-financeiro">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-border p-3">
          <p className="text-xs text-muted-foreground">Em aberto</p>
          <p className="text-base font-semibold text-foreground">{brl(emAberto)}</p>
        </div>
        <div className="rounded-lg border border-border p-3">
          <p className="text-xs text-muted-foreground">Recebido</p>
          <p className="text-base font-semibold text-foreground">{brl(pago)}</p>
        </div>
      </div>
      {ordenadas.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          Nenhuma fatura para este cliente. Faturas saem de "Gerar competência" no Financeiro.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {ordenadas.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-foreground">{f.competencia}</p>
                <p className="text-xs text-muted-foreground">
                  {f.vencimento ? `vence ${dataBR(f.vencimento)}` : "sem vencimento"}
                  {f.pago_em ? ` · paga em ${dataBR(f.pago_em)}` : ""}
                </p>
              </div>
              <span className="font-medium text-foreground">{brl(f.valor_total)}</span>
              <Badge variant={STATUS_VARIANT[f.status] ?? "outline"}>{f.status}</Badge>
              {f.status !== "paga" && f.status !== "cancelada" ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="max-sm:h-10"
                  disabled={marcarPaga.isPending}
                  onClick={() =>
                    marcarPaga.mutate(f.id, {
                      onSuccess: () => toast.success("Fatura marcada como paga."),
                      onError: (e) => toast.error(describeError(e, "Não foi possível marcar como paga.")),
                    })
                  }
                >
                  <CheckCircle2 className="mr-1 h-3 w-3" /> Paga
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
