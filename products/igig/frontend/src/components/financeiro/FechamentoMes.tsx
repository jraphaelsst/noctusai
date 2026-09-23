/**
 * Financeiro → the month at a glance + "Gerar competência" (wave-2 contract,
 * Slice E1).
 *
 * Resumo cards: MRR (the CURRENT active book — not month-scoped, labelled so),
 * a receber / recebido / inadimplente for the selected competência.
 * "Gerar competência" opens one invoice per active contract (retainer +
 * that month's excedentes); re-running is safe — already-billed contracts
 * come back as `existentes`, and the result says how many of each.
 */
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { FilePlus2 } from "lucide-react";
import { toast } from "sonner";

import { useGerarCompetencia, useResumoFinanceiro } from "@/hooks/useFinanceiro";
import { describeError } from "@/lib/errors";
import { brl } from "@/lib/format";

function Cartao({ rotulo, valor, detalhe, alerta }: { rotulo: string; valor: string; detalhe?: string; alerta?: boolean }) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-card p-3">
      <p className="truncate text-xs text-muted-foreground">{rotulo}</p>
      <p className={`truncate text-lg font-semibold ${alerta ? "text-destructive" : "text-foreground"}`}>{valor}</p>
      {detalhe ? <p className="truncate text-[11px] text-muted-foreground">{detalhe}</p> : null}
    </div>
  );
}

export function FechamentoMes({ competencia }: { competencia: string }) {
  const { resumo, showSkeleton, isError, error, isRefreshing } = useResumoFinanceiro(competencia);
  const gerar = useGerarCompetencia();

  return (
    <section className="space-y-3" aria-label="Resumo da competência" data-testid="fechamento-mes">
      {showSkeleton ? (
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error, "Não foi possível carregar o resumo.")}
        </p>
      ) : resumo ? (
        <div className={`grid grid-cols-2 gap-2 lg:grid-cols-4 ${isRefreshing ? "opacity-70" : ""}`}>
          <Cartao rotulo="MRR" valor={brl(resumo.mrr)} detalhe="contratos ativos hoje" />
          <Cartao rotulo="A receber" valor={brl(resumo.a_receber)} detalhe={competencia} />
          <Cartao rotulo="Recebido" valor={brl(resumo.recebido)} detalhe={competencia} />
          <Cartao
            rotulo="Inadimplente"
            valor={brl(resumo.inadimplente_valor)}
            detalhe={`${resumo.inadimplente_qtd} fatura(s)`}
            alerta={resumo.inadimplente_qtd > 0}
          />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-border p-3">
        <p className="min-w-0 flex-1 text-sm text-muted-foreground">
          Fechar {competencia}: uma fatura por contrato ativo (mensalidade + excedentes do mês).
        </p>
        <Button
          className="max-sm:h-10 max-sm:w-full"
          disabled={gerar.isPending || !/^\d{4}-\d{2}$/.test(competencia)}
          data-testid="gerar-competencia"
          onClick={() =>
            gerar.mutate(competencia, {
              onSuccess: (r) =>
                toast.success(
                  `${r.criadas.length} fatura(s) criada(s)` +
                    (r.existentes.length ? ` · ${r.existentes.length} já existia(m)` : "") +
                    ` em ${competencia}.`,
                ),
              onError: (e) => toast.error(describeError(e, "Não foi possível gerar a competência.")),
            })
          }
        >
          <FilePlus2 className="mr-1 h-4 w-4" />
          {gerar.isPending ? "Gerando…" : "Gerar competência"}
        </Button>
      </div>
    </section>
  );
}
