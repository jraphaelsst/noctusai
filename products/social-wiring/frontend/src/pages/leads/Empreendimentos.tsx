/**
 * Empreendimentos — Leads "Empreendimentos" subtab (§6 of
 * leads-module-PROJECT.md). Leads por empreendimento / região, toggled
 * locally between the two dimensions · ranked bars · drill-in (click a row
 * to fold that value into the shared `useLeadsFilters()` state).
 */
import { useState } from "react";
import {
  BarChart,
  ChartCard,
  formatPercent,
  formatPercentDelta,
} from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";
import { useLeadsFilters, type LeadsMultiKey } from "@/hooks/useLeadsFilters";
import { useLeadsByDimension } from "@/hooks/useLeadsAnalytics";

type Dim = "empreendimento" | "regiao";

export default function Empreendimentos() {
  const { filters, toggleMulti } = useLeadsFilters();
  const [dim, setDim] = useState<Dim>("empreendimento");
  const filterKey: LeadsMultiKey = dim;

  const byDimQ = useLeadsByDimension(filters, { dim, limit: 20 });
  const buckets = byDimQ.data?.buckets ?? [];
  const rankedBuckets = [...buckets].sort((a, b) => b.total - a.total);

  return (
    <div className="space-y-4" data-testid="leads-empreendimentos-success">
      <div className="inline-flex rounded-md border border-border bg-muted/30 p-1" role="group" aria-label="Dimensão">
        <Button
          variant={dim === "empreendimento" ? "default" : "ghost"}
          size="sm"
          onClick={() => setDim("empreendimento")}
          data-testid="leads-dim-empreendimento"
        >
          Empreendimento
        </Button>
        <Button
          variant={dim === "regiao" ? "default" : "ghost"}
          size="sm"
          onClick={() => setDim("regiao")}
          data-testid="leads-dim-regiao"
        >
          Região
        </Button>
      </div>

      <ChartCard
        title={dim === "empreendimento" ? "Leads por empreendimento" : "Leads por região"}
        subtitle="Ranking do período selecionado."
        loading={byDimQ.isLoading}
        error={byDimQ.isError ? "Erro ao carregar o ranking." : null}
        isEmpty={rankedBuckets.length === 0}
      >
        <BarChart
          data={rankedBuckets}
          xKey="label"
          series={[{ key: "total", label: "Leads" }]}
          horizontal
          height={360}
        />
      </ChartCard>

      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border p-4">
          <h3 className="font-semibold">
            {dim === "empreendimento" ? "Empreendimentos" : "Regiões"} no período
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Clique numa linha para filtrar todas as abas por ela (drill-in).
          </p>
        </div>
        {byDimQ.isLoading && (
          <div className="p-4 text-sm text-muted-foreground" data-testid="leads-empreendimentos-table-loading">
            Carregando...
          </div>
        )}
        {byDimQ.isError && (
          <div className="p-4 text-sm text-destructive" data-testid="leads-empreendimentos-table-error">
            Erro ao carregar dados.
          </div>
        )}
        {!byDimQ.isLoading && !byDimQ.isError && rankedBuckets.length === 0 && (
          <div
            className="p-4 text-center text-sm text-muted-foreground"
            data-testid="leads-empreendimentos-table-empty"
          >
            Sem dados para o período selecionado.
          </div>
        )}
        {!byDimQ.isLoading && !byDimQ.isError && rankedBuckets.length > 0 && (
          <div className="overflow-x-auto" data-testid="leads-empreendimentos-table">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                  <th className="px-4 py-2">{dim === "empreendimento" ? "Empreendimento" : "Região"}</th>
                  <th className="px-4 py-2 text-right">Total</th>
                  <th className="px-4 py-2 text-right">Participação</th>
                  <th className="px-4 py-2 text-right">Variação</th>
                </tr>
              </thead>
              <tbody>
                {rankedBuckets.map((b) => {
                  const isActive = filters[filterKey].includes(b.key);
                  return (
                    <tr
                      key={b.key}
                      onClick={() => toggleMulti(filterKey, b.key)}
                      className={`cursor-pointer border-b last:border-0 hover:bg-muted/30 ${
                        isActive ? "bg-primary/5" : ""
                      }`}
                      data-testid={`leads-${dim}-row-${b.key}`}
                    >
                      <td className="px-4 py-2">{b.label}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.total}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{formatPercent(b.share_pct)}</td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {b.variacao_pct === null ? "—" : formatPercentDelta(b.variacao_pct)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
