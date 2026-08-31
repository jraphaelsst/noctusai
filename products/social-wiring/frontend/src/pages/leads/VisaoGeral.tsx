/**
 * VisaoGeral — Leads "Visão geral" subtab (§6 of leads-module-PROJECT.md).
 *
 * KPI row (total w/ variação · novos vs retornos · média diária · top
 * origem · variação) · evolução mensal (stacked area, split by origem) ·
 * donut por origem · barras top-10 corretores · heatmap ano×mês.
 *
 * Reads the shared `useLeadsFilters()` state (mirrored to the URL by
 * `LeadsFilterBar`, mounted once in `Leads.tsx`) — no local filter UI here.
 */
import { AlertCircle } from "lucide-react";
import {
  AreaChart,
  BarChart,
  ChartCard,
  DonutChart,
  Heatmap,
  StatTile,
  StatTileRow,
  formatCompactNumber,
  formatPercent,
} from "@noctusai/lib/design-system";
import { useLeadsFilters } from "@/hooks/useLeadsFilters";
import {
  useLeadsByDimension,
  useLeadsHeatmap,
  useLeadsSummary,
  useLeadsTimeseries,
} from "@/hooks/useLeadsAnalytics";
import { ClearFiltersButton } from "./components/ClearFiltersButton";
import { attributionSubtitle } from "./utils";

export default function VisaoGeral() {
  const { filters, setNeedsReview, clearAll } = useLeadsFilters();

  const summaryQ = useLeadsSummary(filters);
  const timeseriesQ = useLeadsTimeseries(filters, { grain: "mes", split: "origem" });
  const origemQ = useLeadsByDimension(filters, { dim: "origem" });
  const corretorQ = useLeadsByDimension(filters, { dim: "corretor", limit: 10 });
  const heatmapQ = useLeadsHeatmap(filters);

  const summary = summaryQ.data;
  const variacao = summary?.comparativo?.variacao_pct ?? null;

  const areaData = (timeseriesQ.data?.points ?? []).map((p) => ({
    label: p.label,
    ...p.series,
  }));
  const areaSeries = (timeseriesQ.data?.series_meta ?? []).map((m) => ({
    key: m.key,
    label: m.label,
    color: m.cor ?? undefined,
  }));

  const donutData = origemQ.data?.buckets ?? [];
  const corretorData = corretorQ.data?.buckets ?? [];

  const origemSubtitle =
    attributionSubtitle({
      dimTotal: origemQ.data?.total,
      grandTotal: summary?.total,
      dimensionLabel: "com origem identificada",
      missingLabel: "sem origem",
    }) ?? "Distribuição do período selecionado.";

  const corretorSubtitle =
    attributionSubtitle({
      dimTotal: corretorQ.data?.total,
      grandTotal: summary?.total,
      dimensionLabel: "com corretor identificado",
      missingLabel: "sem corretor",
    }) ?? "Ranking por total de leads no período.";

  return (
    <div className="space-y-6" data-testid="leads-overview-success">
      <StatTileRow>
        <StatTile
          label="Total de leads"
          value={summary ? formatCompactNumber(summary.total) : "—"}
          loading={summaryQ.isPending && !summaryQ.data}
          delta={variacao}
          hint="vs. período anterior"
        />
        <StatTile
          label="Novos / Retornos"
          value={
            summary
              ? `${formatCompactNumber(summary.novos)} / ${formatCompactNumber(summary.retornos)}`
              : "—"
          }
          loading={summaryQ.isPending && !summaryQ.data}
        />
        <StatTile
          label="Média diária"
          value={summary ? summary.media_diaria.toFixed(1) : "—"}
          loading={summaryQ.isPending && !summaryQ.data}
        />
        <StatTile
          label="Top origem"
          value={summary?.top_origem?.label ?? "—"}
          hint={summary?.top_origem ? `${formatPercent(summary.top_origem.share_pct)} do total` : undefined}
          loading={summaryQ.isPending && !summaryQ.data}
        />
        <StatTile
          label="Variação"
          value={variacao === null ? "—" : formatPercent(Math.abs(variacao))}
          delta={variacao}
          hint="vs. período anterior"
          loading={summaryQ.isPending && !summaryQ.data}
        />
        {/*
          StatTile (seed organ) has no onClick prop — wrapping it in a plain
          <button> keeps the organ untouched (no local fork) while adding the
          drill-in affordance this KPI needs. Worth promoting an `onClick`
          prop upstream if a 2nd product needs a clickable StatTile (logged
          below as a scoped-improvement, not yet at the N=2 seed-lib bar).
        */}
        <button
          type="button"
          className="text-left"
          onClick={() => setNeedsReview(filters.needs_review === true ? null : true)}
          data-testid="leads-stat-needs-review"
        >
          <StatTile
            icon={AlertCircle}
            label="Precisam de revisão"
            value={summary ? formatCompactNumber(summary.needs_review) : "—"}
            loading={summaryQ.isPending && !summaryQ.data}
            hint={filters.needs_review === true ? "filtro ativo — clique para limpar" : "clique para filtrar"}
          />
        </button>
      </StatTileRow>

      <ChartCard
        title="Evolução mensal por origem"
        subtitle="Total de leads por mês, separados por origem canônica."
        loading={timeseriesQ.isPending && !timeseriesQ.data}
        error={timeseriesQ.isError ? "Erro ao carregar a evolução mensal." : null}
        isEmpty={areaData.length === 0}
        actions={timeseriesQ.isError ? <ClearFiltersButton onClick={clearAll} /> : undefined}
      >
        <AreaChart data={areaData} xKey="label" series={areaSeries} stacked height={320} />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Leads por origem"
          subtitle={origemSubtitle}
          loading={origemQ.isPending && !origemQ.data}
          error={origemQ.isError ? "Erro ao carregar leads por origem." : null}
          isEmpty={donutData.length === 0}
          actions={origemQ.isError ? <ClearFiltersButton onClick={clearAll} /> : undefined}
        >
          <DonutChart data={donutData} nameKey="label" valueKey="total" colorKey="cor" />
        </ChartCard>

        <ChartCard
          title="Top 10 corretores"
          subtitle={corretorSubtitle}
          loading={corretorQ.isPending && !corretorQ.data}
          error={corretorQ.isError ? "Erro ao carregar o ranking de corretores." : null}
          isEmpty={corretorData.length === 0}
          actions={corretorQ.isError ? <ClearFiltersButton onClick={clearAll} /> : undefined}
        >
          <BarChart
            data={corretorData}
            xKey="label"
            series={[{ key: "total", label: "Leads" }]}
            horizontal
          />
        </ChartCard>
      </div>

      <ChartCard
        title="Heatmap ano × mês"
        subtitle="Volume de leads por mês, todos os anos importados."
        loading={heatmapQ.isPending && !heatmapQ.data}
        error={heatmapQ.isError ? "Erro ao carregar o heatmap." : null}
        isEmpty={!heatmapQ.data || heatmapQ.data.anos.length === 0}
        minBodyHeight={220}
        actions={heatmapQ.isError ? <ClearFiltersButton onClick={clearAll} /> : undefined}
      >
        {heatmapQ.data && (
          <Heatmap anos={heatmapQ.data.anos} cells={heatmapQ.data.cells} max={heatmapQ.data.max} />
        )}
      </ChartCard>
    </div>
  );
}
