/**
 * Corretores — Leads "Corretores" subtab (§6 of leads-module-PROJECT.md).
 *
 * Ranking bars · share donut · per-broker evolution · table — same
 * drill-in-by-click convention as `Origens.tsx`, toggling `corretor_id`
 * into the shared `useLeadsFilters()` state.
 */
import {
  AreaChart,
  BarChart,
  ChartCard,
  DonutChart,
  TableSkeleton,
  formatPercent,
  formatPercentDelta,
} from "@noctusai/lib/design-system";
import { useLeadsFilters } from "@/hooks/useLeadsFilters";
import { useLeadsByDimension, useLeadsTimeseries } from "@/hooks/useLeadsAnalytics";

export default function Corretores() {
  const { filters, toggleMulti } = useLeadsFilters();

  const byDimQ = useLeadsByDimension(filters, { dim: "corretor", limit: 50 });
  const timeseriesQ = useLeadsTimeseries(filters, { grain: "mes", split: "corretor" });

  const buckets = byDimQ.data?.buckets ?? [];
  const rankedBuckets = [...buckets].sort((a, b) => b.total - a.total).slice(0, 15);

  const areaData = (timeseriesQ.data?.points ?? []).map((p) => ({
    label: p.label,
    ...p.series,
  }));
  const areaSeries = (timeseriesQ.data?.series_meta ?? []).map((m) => ({
    key: m.key,
    label: m.label,
    color: m.cor ?? undefined,
  }));

  return (
    <div className="space-y-4" data-testid="leads-corretores-success">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Ranking de corretores"
          subtitle="Total de leads no período selecionado."
          loading={byDimQ.isLoading}
          error={byDimQ.isError ? "Erro ao carregar o ranking." : null}
          isEmpty={rankedBuckets.length === 0}
        >
          <BarChart
            data={rankedBuckets}
            xKey="label"
            series={[{ key: "total", label: "Leads" }]}
            horizontal
          />
        </ChartCard>

        <ChartCard
          title="Participação por corretor"
          subtitle="Distribuição do total de leads."
          loading={byDimQ.isLoading}
          error={byDimQ.isError ? "Erro ao carregar a participação." : null}
          isEmpty={buckets.length === 0}
        >
          <DonutChart data={buckets} nameKey="label" valueKey="total" colorKey="cor" />
        </ChartCard>
      </div>

      <ChartCard
        title="Evolução por corretor"
        subtitle="Total de leads por mês, cada corretor em sua própria série."
        loading={timeseriesQ.isLoading}
        error={timeseriesQ.isError ? "Erro ao carregar a evolução por corretor." : null}
        isEmpty={areaData.length === 0}
      >
        <AreaChart data={areaData} xKey="label" series={areaSeries} height={320} />
      </ChartCard>

      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border p-4">
          <h3 className="font-semibold">Corretores no período</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Clique num corretor para filtrar todas as abas por ele (drill-in).
          </p>
        </div>
        {byDimQ.isPending && (
          <div className="p-4" data-testid="leads-corretores-table-loading">
            <TableSkeleton rows={8} columns={6} />
          </div>
        )}
        {byDimQ.isError && (
          <div className="p-4 text-sm text-destructive" data-testid="leads-corretores-table-error">
            Erro ao carregar corretores.
          </div>
        )}
        {!byDimQ.isPending && !byDimQ.isFetching && !byDimQ.isError && buckets.length === 0 && (
          <div
            className="p-4 text-center text-sm text-muted-foreground"
            data-testid="leads-corretores-table-empty"
          >
            Sem dados para o período selecionado.
          </div>
        )}
        {!byDimQ.isPending && !byDimQ.isError && buckets.length > 0 && (
          <div className="overflow-x-auto" data-testid="leads-corretores-table">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                  <th className="px-4 py-2">Corretor</th>
                  <th className="px-4 py-2 text-right">Total</th>
                  <th className="px-4 py-2 text-right">Novos</th>
                  <th className="px-4 py-2 text-right">Retornos</th>
                  <th className="px-4 py-2 text-right">Participação</th>
                  <th className="px-4 py-2 text-right">Variação</th>
                </tr>
              </thead>
              <tbody>
                {buckets.map((b) => {
                  const isActive = filters.corretor_id.includes(b.key);
                  return (
                    <tr
                      key={b.key}
                      onClick={() => toggleMulti("corretor_id", b.key)}
                      className={`cursor-pointer border-b last:border-0 hover:bg-muted/30 ${
                        isActive ? "bg-primary/5" : ""
                      }`}
                      data-testid={`leads-corretor-row-${b.key}`}
                    >
                      <td className="px-4 py-2">
                        <span className="inline-flex items-center gap-1.5">
                          {b.cor && <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: b.cor }} />}
                          {b.label}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.total}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.novos}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{b.retornos}</td>
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
