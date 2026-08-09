/**
 * Financeiro — Módulo 6: DRE, excedentes, faturas e régua de cobrança.
 *
 * The DRE is the screen the agency makes decisions on, so two things are
 * deliberate:
 *   - `alertas` render as a visible row. When hours could not be costed the
 *     margin is OVERSTATED, and a number that looks precise while being
 *     optimistic is the worst possible output here.
 *   - negative margin is coloured, because "we lost money on this account" is
 *     the single most actionable thing this table can say.
 */
import { Fragment, useState } from "react";
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

import {
  useDRE,
  useExcedentes,
  useFaturas,
  useInadimplentes,
  useMarcarPaga,
  type StatusFatura,
} from "@/hooks/useFinanceiro";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const STATUS_VARIANT: Record<StatusFatura, BadgeVariant> = {
  aberta: "muted",
  enviada: "outline",
  paga: "default",
  vencida: "destructive",
  cancelada: "outline",
};

/** Current month as 'YYYY-MM'. */
function competenciaAtual(): string {
  const hoje = new Date();
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
}

export default function Financeiro() {
  const [competencia, setCompetencia] = useState(competenciaAtual);
  const { linhas, loading: carregandoDRE } = useDRE();
  const { excedentes, loading: carregandoExc } = useExcedentes(competencia);
  const { faturas, loading: carregandoFat } = useFaturas();
  const { atrasadas } = useInadimplentes();
  const marcarPaga = useMarcarPaga();

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Financeiro</h1>
          <p className="text-sm text-muted-foreground">
            Margem por conta, excedentes e cobrança.
          </p>
        </div>
        <label className="text-xs text-muted-foreground">
          Competência
          <input
            type="month"
            value={competencia}
            onChange={(e) => setCompetencia(e.target.value)}
            className="ml-2 h-9 rounded border border-border bg-card px-2 text-sm text-foreground"
          />
        </label>
      </header>

      {atrasadas.length > 0 && (
        <div className="rounded-lg border border-destructive/40 bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-destructive">
            <AlertTriangle className="h-4 w-4" />
            {atrasadas.length} fatura(s) em atraso
          </h2>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {atrasadas.slice(0, 5).map((f) => (
              <li key={f.fatura_id}>
                {f.competencia} · {BRL.format(f.valor_total)} ·{" "}
                <span className="text-destructive">{f.dias_atraso} dias</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── DRE ────────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">DRE por conta</h2>
        {carregandoDRE ? (
          <Skeleton className="h-24 w-full" />
        ) : linhas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum cliente ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2">Cliente</th>
                  <th className="py-2 text-right">Receita</th>
                  <th className="py-2 text-right">Custo real</th>
                  <th className="py-2 text-right">Margem</th>
                  <th className="py-2 text-right">%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {linhas.map((l) => (
                  <Fragment key={l.cliente_id}>
                    <tr>
                      <td className="py-2 text-foreground">{l.cliente_nome}</td>
                      <td className="py-2 text-right text-foreground">{BRL.format(l.receita)}</td>
                      <td className="py-2 text-right text-foreground">{BRL.format(l.custo)}</td>
                      <td
                        className={`py-2 text-right ${
                          l.margem < 0 ? "text-destructive" : "text-foreground"
                        }`}
                      >
                        {BRL.format(l.margem)}
                      </td>
                      <td
                        className={`py-2 text-right ${
                          l.margem < 0 ? "text-destructive" : "text-foreground"
                        }`}
                      >
                        {l.margem_percentual.toFixed(1)}%
                      </td>
                    </tr>
                    {l.alertas.length > 0 && (
                      <tr>
                        <td colSpan={5} className="pb-2 text-xs text-destructive">
                          <AlertTriangle className="mr-1 inline h-3 w-3" />
                          {l.alertas.join(" · ")}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Excedentes ─────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-1 text-sm font-semibold text-foreground">
          Itens excedentes — {competencia}
        </h2>
        <p className="mb-3 text-xs text-muted-foreground">
          Cobrados na fatura do mês seguinte.
        </p>
        {carregandoExc ? (
          <Skeleton className="h-20 w-full" />
        ) : excedentes.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum contrato ativo com pacote definido nesta competência.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {excedentes.map((e) => (
              <li key={e.contrato_id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                  {e.cliente_nome}
                </span>
                <span className="text-xs text-muted-foreground">
                  {e.entregues} / {e.contratados} entregues
                </span>
                {e.excedentes > 0 ? (
                  <>
                    <Badge variant="destructive">+{e.excedentes}</Badge>
                    <span className="text-sm text-foreground">{BRL.format(e.valor_total)}</span>
                    <span className="text-xs text-muted-foreground">
                      → {e.competencia_cobranca}
                    </span>
                  </>
                ) : (
                  <Badge variant="muted">dentro do pacote</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Faturas ────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Faturas</h2>
        {carregandoFat ? (
          <Skeleton className="h-20 w-full" />
        ) : faturas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma fatura emitida.</p>
        ) : (
          <ul className="divide-y divide-border">
            {faturas.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-3 py-2">
                <Badge variant={STATUS_VARIANT[f.status]}>{f.status}</Badge>
                <span className="text-sm text-foreground">{f.competencia}</span>
                <span className="min-w-0 flex-1 text-sm text-foreground">
                  {BRL.format(f.valor_total)}
                </span>
                {f.vencimento && (
                  <span className="text-xs text-muted-foreground">vence {f.vencimento}</span>
                )}
                {f.status !== "paga" && f.status !== "cancelada" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={marcarPaga.isPending}
                    onClick={() => marcarPaga.mutate(f.id)}
                  >
                    <CheckCircle2 className="mr-2 h-3 w-3" />
                    Marcar paga
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          Baixa manual: o webhook do gateway (Asaas/Iugu) e a emissão de NFS-e
          dependem de credenciais e homologação ainda não configuradas.
        </p>
      </section>
    </div>
  );
}
