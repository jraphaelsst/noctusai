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

export default function VisaoGeral() {
  const { filters } = useLeadsFilters();

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

  return (
    <div className="space-y-6" data-testid="leads-overview-success">
      <StatTileRow>
        <StatTile
          label="Total de leads"
          value={summary ? formatCompactNumber(summary.total) : "—"}
          loading={summaryQ.isPending || summaryQ.isFetching}
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
          loading={summaryQ.isPending || summaryQ.isFetching}
        />
        <StatTile
          label="Média diária"
          value={summary ? summary.media_diaria.toFixed(1) : "—"}
          loading={summaryQ.isPending || summaryQ.isFetching}
        />
        <StatTile
          label="Top origem"
          value={summary?.top_origem?.label ?? "—"}
          hint={summary?.top_origem ? `${formatPercent(summary.top_origem.share_pct)} do total` : undefined}
          loading={summaryQ.isPending || summaryQ.isFetching}
        />
        <StatTile
          label="Variação"
          value={variacao === null ? "—" : formatPercent(Math.abs(variacao))}
          delta={variacao}
          hint="vs. período anterior"
          loading={summaryQ.isPending || summaryQ.isFetching}
        />
      </StatTileRow>

      <ChartCard
        title="Evolução mensal por origem"
        subtitle="Total de leads por mês, separados por origem canônica."
        loading={timeseriesQ.isPending || timeseriesQ.isFetching}
        error={timeseriesQ.isError ? "Erro ao carregar a evolução mensal." : null}
        isEmpty={areaData.length === 0}
      >
        <AreaChart data={areaData} xKey="label" series={areaSeries} stacked height={320} />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Leads por origem"
          subtitle="Distribuição do período selecionado."
          loading={origemQ.isPending || origemQ.isFetching}
          error={origemQ.isError ? "Erro ao carregar leads por origem." : null}
          isEmpty={donutData.length === 0}
        >
          <DonutChart data={donutData} nameKey="label" valueKey="total" colorKey="cor" />
        </ChartCard>

        <ChartCard
          title="Top 10 corretores"
          subtitle="Ranking por total de leads no período."
          loading={corretorQ.isPending || corretorQ.isFetching}
          error={corretorQ.isError ? "Erro ao carregar o ranking de corretores." : null}
          isEmpty={corretorData.length === 0}
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
        loading={heatmapQ.isPending || heatmapQ.isFetching}
        error={heatmapQ.isError ? "Erro ao carregar o heatmap." : null}
        isEmpty={!heatmapQ.data || heatmapQ.data.anos.length === 0}
        minBodyHeight={220}
      >
        {heatmapQ.data && (
          <Heatmap anos={heatmapQ.data.anos} cells={heatmapQ.data.cells} max={heatmapQ.data.max} />
        )}
      </ChartCard>
    </div>
  );
}
