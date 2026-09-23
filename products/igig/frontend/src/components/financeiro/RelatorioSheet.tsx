/**
 * "Relatório" — the comercial / financeiro report (wave-2 contract, Slice E1):
 * pick tipo + período, preview it on screen (json), download PDF or CSV.
 *
 * A sheet below 640px (R0). The preview is a query keyed on (tipo, período),
 * so reopening the same period is instant; the previous preview stays on
 * screen while a new period loads (`placeholderData`), dimmed — never blanked.
 */
import { useState } from "react";
import { Button, Field, Input, Select, Skeleton } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { AlertTriangle, FileDown } from "lucide-react";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import {
  margemCliente,
  taxaConversao,
  useBaixarRelatorio,
  useRelatorioPreview,
  type FormatoArquivo,
  type Relatorio,
  type TipoRelatorio,
} from "@/hooks/useRelatorios";
import { describeError } from "@/lib/errors";
import { brl, pct } from "@/lib/format";

function isoHoje(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isoInicioDoMes(): string {
  return `${isoHoje().slice(0, 8)}01`;
}

export function RelatorioSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [tipo, setTipo] = useState<TipoRelatorio>("financeiro");
  const [inicio, setInicio] = useState(isoInicioDoMes);
  const [fim, setFim] = useState(isoHoje);
  const periodoInvalido = !!inicio && !!fim && inicio > fim;
  const filtro = open ? { tipo, inicio, fim } : null;
  const { relatorio, showSkeleton, isError, error, isRefreshing } = useRelatorioPreview(filtro);
  const baixar = useBaixarRelatorio();

  function download(formato: FormatoArquivo) {
    baixar.mutate(
      { tipo, inicio, fim, formato },
      { onError: (e) => toast.error(describeError(e, "Não foi possível baixar o relatório.")) },
    );
  }

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="Relatório"
      description="Comercial (funil, ganhos/perdas, orçamentos) ou financeiro (faturamento, recebido, inadimplência, por cliente)."
      widthClassName="sm:max-w-3xl"
      testId="relatorio-sheet"
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            className="max-sm:h-10 max-sm:flex-1"
            disabled={periodoInvalido || baixar.isPending}
            onClick={() => download("csv")}
          >
            <FileDown className="mr-1 h-4 w-4" /> CSV
          </Button>
          <Button className="max-sm:h-10 max-sm:flex-1" disabled={periodoInvalido || baixar.isPending} onClick={() => download("pdf")}>
            <FileDown className="mr-1 h-4 w-4" /> {baixar.isPending ? "Baixando…" : "PDF"}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Tipo">
            <Select className="h-10 sm:h-8" aria-label="Tipo de relatório" value={tipo} onChange={(e) => setTipo(e.target.value as TipoRelatorio)}>
              <option value="financeiro">Financeiro</option>
              <option value="comercial">Comercial</option>
            </Select>
          </Field>
          <Field label="De">
            <Input className="max-sm:h-10" type="date" aria-label="Início do período" value={inicio} onChange={(e) => setInicio(e.target.value)} />
          </Field>
          <Field label="Até" error={periodoInvalido ? "O fim vem antes do início." : null}>
            <Input className="max-sm:h-10" type="date" aria-label="Fim do período" value={fim} onChange={(e) => setFim(e.target.value)} />
          </Field>
        </div>

        {periodoInvalido ? null : showSkeleton ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : isError ? (
          <p role="alert" className="text-sm text-destructive">
            {describeError(error, "Não foi possível gerar o relatório.")}
          </p>
        ) : relatorio ? (
          <div className={cn("space-y-4 transition-opacity", isRefreshing && "opacity-60")} data-testid="relatorio-preview">
            <PreviewRelatorio relatorio={relatorio} />
          </div>
        ) : null}
      </div>
    </SheetDialog>
  );
}

function Numero({ rotulo, valor, alerta }: { rotulo: string; valor: string; alerta?: boolean }) {
  return (
    <div className="min-w-0 rounded-lg border border-border p-3">
      <p className="truncate text-xs text-muted-foreground">{rotulo}</p>
      <p className={cn("truncate text-base font-semibold", alerta ? "text-destructive" : "text-foreground")}>{valor}</p>
    </div>
  );
}

function Alertas({ alertas }: { alertas: string[] }) {
  if (!alertas.length) return null;
  return (
    <ul className="space-y-1 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
      {alertas.map((a) => (
        <li key={a} className="flex items-start gap-1">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {a}
        </li>
      ))}
    </ul>
  );
}

function PreviewRelatorio({ relatorio }: { relatorio: Relatorio }) {
  if (relatorio.tipo === "comercial" && relatorio.comercial) {
    const c = relatorio.comercial;
    return (
      <>
        <Alertas alertas={c.alertas} />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Numero rotulo="Ganhos" valor={`${c.negocios_ganhos} · ${brl(c.negocios_ganhos_valor)}`} />
          <Numero rotulo="Perdidos" valor={`${c.negocios_perdidos} · ${brl(c.negocios_perdidos_valor)}`} />
          <Numero rotulo="Orçamentos env./aceit./recus." valor={`${c.orcamentos_enviados}/${c.orcamentos_aceitos}/${c.orcamentos_recusados}`} />
          <Numero rotulo="Ticket médio" valor={brl(c.ticket_medio)} />
        </div>
        <section className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">Funil</h3>
          {c.funil.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma movimentação no período.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border text-sm">
              {c.funil.map((e) => (
                <li key={e.etapa_id} className="flex flex-wrap items-center gap-2 p-2">
                  <span className="min-w-0 flex-1 truncate text-foreground">{e.etapa_label}</span>
                  <span className="text-xs text-muted-foreground">
                    {e.entradas} entradas · {e.saidas} saídas
                  </span>
                  <span className="w-14 text-right font-medium text-foreground">{pct(taxaConversao(e))}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">
            Motivos de perda <span className="font-normal text-muted-foreground">· tempo médio parado {c.dwell_time_medio_dias.toLocaleString("pt-BR")} dias</span>
          </h3>
          {c.motivos_perda.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma perda no período.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border text-sm">
              {c.motivos_perda.map((m) => (
                <li key={`${m.motivo}-${m.etapa_label}`} className="flex flex-wrap items-center gap-2 p-2">
                  <span className="min-w-0 flex-1 text-foreground">{m.motivo}</span>
                  <span className="text-xs text-muted-foreground">em {m.etapa_label}</span>
                  <span className="text-xs text-foreground">
                    {m.quantidade}× · {brl(m.valor_total)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </>
    );
  }
  if (relatorio.tipo === "financeiro" && relatorio.financeiro) {
    const f = relatorio.financeiro;
    return (
      <>
        <Alertas alertas={f.alertas} />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Numero rotulo="Faturamento" valor={brl(f.faturamento)} />
          <Numero rotulo="Recebido" valor={brl(f.recebido)} />
          <Numero rotulo="A receber" valor={brl(f.a_receber)} />
          <Numero
            rotulo={`Inadimplência (${f.inadimplencia_qtd})`}
            valor={brl(f.inadimplencia_valor)}
            alerta={f.inadimplencia_qtd > 0}
          />
        </div>
        <section className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">Por cliente</h3>
          {f.clientes.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum faturamento no período.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border text-sm">
              {f.clientes.map((c) => {
                const m = margemCliente(c);
                return (
                  <li key={c.cliente_id} className="grid grid-cols-2 gap-1 p-2 sm:grid-cols-5 sm:items-center">
                    <span className="col-span-2 truncate font-medium text-foreground sm:col-span-1">{c.cliente_nome}</span>
                    <span className="text-xs text-muted-foreground">fat. {brl(c.faturamento)}</span>
                    <span className="text-xs text-muted-foreground">receb. {brl(c.recebido)}</span>
                    <span className="text-xs text-muted-foreground">custo {brl(c.custo)}</span>
                    <span className={cn("text-xs font-medium", m.margem < 0 ? "text-destructive" : "text-foreground")}>
                      margem {brl(m.margem)} ({pct(m.percentual)})
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="text-[11px] text-muted-foreground">Custo por cliente é o custo medido total (não só do período).</p>
        </section>
      </>
    );
  }
  return <p className="text-sm text-muted-foreground">Relatório vazio.</p>;
}
