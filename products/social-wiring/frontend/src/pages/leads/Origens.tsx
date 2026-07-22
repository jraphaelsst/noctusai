/**
 * Origens — Leads "Origens" subtab (§6 of leads-module-PROJECT.md).
 *
 * Stacked-area over time per source · table with share % + variação vs. the
 * preceding window · drill-in to a single source (clicking a row toggles
 * that `origem_id` into the SHARED `useLeadsFilters()` state, so every
 * other subtab narrows to it too — the same filter set drives every chart).
 */
import {
  AreaChart,
  ChartCard,
  TableSkeleton,
  formatPercent,
  formatPercentDelta,
} from "@noctusai/lib/design-system";
import { useLeadsFilters } from "@/hooks/useLeadsFilters";
import { useLeadsByDimension, useLeadsTimeseries } from "@/hooks/useLeadsAnalytics";

export default function Origens() {
  const { filters, toggleMulti } = useLeadsFilters();

  const timeseriesQ = useLeadsTimeseries(filters, { grain: "mes", split: "origem" });
  const byDimQ = useLeadsByDimension(filters, { dim: "origem", limit: 50 });

  const areaData = (timeseriesQ.data?.points ?? []).map((p) => ({
    label: p.label,
    ...p.series,
  }));
  const areaSeries = (timeseriesQ.data?.series_meta ?? []).map((m) => ({
    key: m.key,
    label: m.label,
    color: m.cor ?? undefined,
  }));

  const buckets = byDimQ.data?.buckets ?? [];

  return (
    <div className="space-y-4" data-testid="leads-origens-success">
      <ChartCard
        title="Evolução por origem"
        subtitle="Total de leads por mês, cada origem em sua própria série."
        loading={timeseriesQ.isLoading}
        error={timeseriesQ.isError ? "Erro ao carregar a evolução por origem." : null}
        isEmpty={areaData.length === 0}
      >
        <AreaChart data={areaData} xKey="label" series={areaSeries} stacked height={320} />
      </ChartCard>

      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border p-4">
          <h3 className="font-semibold">Origens no período</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Clique numa origem para filtrar todas as abas por ela (drill-in).
          </p>
        </div>

        {byDimQ.isPending && (
          <div className="p-4" data-testid="leads-origens-table-loading">
            <TableSkeleton rows={8} columns={6} />
          </div>
        )}
        {byDimQ.isError && (
          <div className="p-4 text-sm text-destructive" data-testid="leads-origens-table-error">
            Erro ao carregar origens.
          </div>
        )}
        {!byDimQ.isPending && !byDimQ.isFetching && !byDimQ.isError && buckets.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-foreground" data-testid="leads-origens-table-empty">
            Sem dados para o período selecionado.
          </div>
        )}
        {!byDimQ.isPending && !byDimQ.isError && buckets.length > 0 && (
          <div className="overflow-x-auto" data-testid="leads-origens-table">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                  <th className="px-4 py-2">Origem</th>
                  <th className="px-4 py-2 text-right">Total</th>
                  <th className="px-4 py-2 text-right">Novos</th>
                  <th className="px-4 py-2 text-right">Retornos</th>
                  <th className="px-4 py-2 text-right">Participação</th>
                  <th className="px-4 py-2 text-right">Variação</th>
                </tr>
              </thead>
              <tbody>
                {buckets.map((b) => {
                  const isActive = filters.origem_id.includes(b.key);
                  return (
                    <tr
                      key={b.key}
                      onClick={() => toggleMulti("origem_id", b.key)}
                      className={`cursor-pointer border-b last:border-0 hover:bg-muted/30 ${
                        isActive ? "bg-primary/5" : ""
                      }`}
                      data-testid={`leads-origem-row-${b.key}`}
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
