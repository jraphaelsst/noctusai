/**
 * Origens — Leads "Origens" subtab (§6 of leads-module-PROJECT.md).
 *
 * Stacked-area over time per source · table with share % + variação vs. the
 * preceding window · drill-in to a single source (clicking a row toggles
 * that `origem_id` into the SHARED `useLeadsFilters()` state, so every
 * other subtab narrows to it too — the same filter set drives every chart).
 *
 * `by-dimension?dim=origem` buckets are keyed by the source SLUG (see
 * `_split_key_label_cor` in analytics_service.py — `source["slug"]`), but
 * `origem_id` is a typed-UUID filter param. The row click resolves
 * slug→id via `useLeadSources()` (already loaded fleet-wide for the filter
 * bar) BEFORE toggling the filter — toggling the raw slug 422s every
 * endpoint sharing `get_lead_filters` (leads-p0-frontend-ux finding #1).
 */
import { useMemo } from "react";
import {
  AreaChart,
  ChartCard,
  TableSkeleton,
  formatPercent,
  formatPercentDelta,
} from "@noctusai/lib/design-system";
import { useLeadsFilters } from "@/hooks/useLeadsFilters";
import { useLeadSources } from "@/hooks/useLeadsSources";
import { useLeadsByDimension, useLeadsSummary, useLeadsTimeseries } from "@/hooks/useLeadsAnalytics";
import { ClearFiltersButton } from "./components/ClearFiltersButton";
import { attributionSubtitle, isOutrosBucket } from "./utils";

export default function Origens() {
  const { filters, toggleMulti, clearAll } = useLeadsFilters();
  const { data: sources } = useLeadSources();

  const timeseriesQ = useLeadsTimeseries(filters, { grain: "mes", split: "origem" });
  const byDimQ = useLeadsByDimension(filters, { dim: "origem", limit: 50 });
  const summaryQ = useLeadsSummary(filters);

  const areaData = (timeseriesQ.data?.points ?? []).map((p) => ({
    label: p.label,
    ...p.series,
  }));
  const areaSeries = (timeseriesQ.data?.series_meta ?? []).map((m) => ({
    key: m.key,
    label: m.label,
    color: m.cor ?? undefined,
  }));

  // slug -> id: the by-dimension bucket `key` is a slug; `origem_id` filters
  // (and `filters.origem_id`) are ids. Resolved once per sources fetch.
  const idBySlug = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of sources ?? []) map.set(s.slug, s.id);
    return map;
  }, [sources]);

  const buckets = byDimQ.data?.buckets ?? [];

  const attribution = attributionSubtitle({
    dimTotal: byDimQ.data?.total,
    grandTotal: summaryQ.data?.total,
    dimensionLabel: "com origem identificada",
    missingLabel: "sem origem",
  });

  return (
    <div className="space-y-4" data-testid="leads-origens-success">
      <ChartCard
        title="Evolução por origem"
        subtitle="Total de leads por mês, cada origem em sua própria série."
        loading={timeseriesQ.isPending || timeseriesQ.isFetching}
        error={timeseriesQ.isError ? "Erro ao carregar a evolução por origem." : null}
        isEmpty={areaData.length === 0}
        actions={timeseriesQ.isError ? <ClearFiltersButton onClick={clearAll} /> : undefined}
      >
        <AreaChart data={areaData} xKey="label" series={areaSeries} stacked height={320} />
      </ChartCard>

      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border p-4">
          <h3 className="font-semibold">Origens no período</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Clique numa origem para filtrar todas as abas por ela.
          </p>
          {attribution && (
            <p className="mt-0.5 text-xs text-muted-foreground" data-testid="leads-origens-attribution">
              {attribution}
            </p>
          )}
        </div>

        {byDimQ.isPending && (
          <div className="p-4" data-testid="leads-origens-table-loading">
            <TableSkeleton rows={8} columns={6} />
          </div>
        )}
        {byDimQ.isError && (
          <div
            className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm text-destructive"
            data-testid="leads-origens-table-error"
          >
            <span>Erro ao carregar origens.</span>
            <ClearFiltersButton onClick={clearAll} />
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
                  const outros = isOutrosBucket(b.key);
                  const origemId = outros ? undefined : idBySlug.get(b.key);
                  const isActive = !!origemId && filters.origem_id.includes(origemId);
                  const clickable = !outros && !!origemId;
                  return (
                    <tr
                      key={b.key}
                      onClick={clickable ? () => toggleMulti("origem_id", origemId) : undefined}
                      className={`border-b last:border-0 ${
                        clickable ? "cursor-pointer hover:bg-muted/30" : "cursor-default"
                      } ${isActive ? "bg-primary/5" : ""}`}
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
