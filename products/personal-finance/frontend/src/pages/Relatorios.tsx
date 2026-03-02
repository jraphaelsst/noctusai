import { useState, useMemo } from "react";
import { useRelatorioMensal } from "@/hooks/useRelatorios";
import { BarChartCard } from "@/components/charts/BarChartCard";
import { LineChartCard } from "@/components/charts/LineChartCard";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { formatCurrency, formatPercent, getCurrentMonth, getMonthLabel } from "@/lib/utils";
import { CHART_COLORS } from "@/lib/constants";
import { FileBarChart, TrendingUp, TrendingDown } from "lucide-react";

export default function Relatorios() {
  const [mesSelecionado, setMesSelecionado] = useState(getCurrentMonth());
  const { data: relatorio, isLoading } = useRelatorioMensal(mesSelecionado);

  // Build month selector options (current + last 23 months)
  const meses = useMemo(() => {
    const result: string[] = [];
    const now = new Date();
    for (let i = 0; i < 24; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      result.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    }
    return result;
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const rel = relatorio || {} as any;
  const receita = rel.receita_total || rel.receita || 0;
  const despesa = rel.despesa_total || rel.despesa || 0;
  const fluxoCaixa = receita - despesa;
  const taxaPoupanca = receita > 0 ? ((receita - despesa) / receita) * 100 : 0;
  const isPositiveFluxo = fluxoCaixa >= 0;

  // Top categories
  const topCategorias: { nome: string; total: number; cor?: string }[] = rel.top_categorias || rel.categorias || [];
  const categoriaChartData = topCategorias.map((c, idx) => ({
    nome: c.nome || "Outros",
    total: c.total || 0,
    cor: c.cor || CHART_COLORS[idx % CHART_COLORS.length],
  }));

  // Cash flow chart (income vs expense for each month, using comparativo_mensal if available)
  const comparativo: any[] = rel.comparativo_mensal || rel.comparativo || [];
  const cashFlowData = comparativo.length > 0
    ? comparativo.map((m: any) => ({
        label: getMonthLabel(m.mes || m.periodo || ""),
        receita: m.receita || m.receita_total || 0,
        despesa: m.despesa || m.despesa_total || 0,
      }))
    : [
        {
          label: getMonthLabel(mesSelecionado),
          receita,
          despesa,
        },
      ];

  // Monthly comparison line data
  const lineData = comparativo.length > 0
    ? comparativo.map((m: any) => ({
        label: getMonthLabel(m.mes || m.periodo || ""),
        fluxo: (m.receita || m.receita_total || 0) - (m.despesa || m.despesa_total || 0),
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Relatorios</h1>
      </div>

      {/* Month selector */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-muted-foreground">Mes:</label>
        <select
          value={mesSelecionado}
          onChange={(e) => setMesSelecionado(e.target.value)}
          className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {meses.map((m) => (
            <option key={m} value={m}>{getMonthLabel(m)}</option>
          ))}
        </select>
      </div>

      {/* KPI Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Receita</p>
          <p className="text-xl font-bold text-emerald-500">{formatCurrency(receita)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Despesa</p>
          <p className="text-xl font-bold text-red-500">{formatCurrency(despesa)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Fluxo de Caixa</p>
          <div className={`flex items-center gap-2 ${isPositiveFluxo ? "text-emerald-500" : "text-red-500"}`}>
            {isPositiveFluxo ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <p className="text-xl font-bold">{formatCurrency(fluxoCaixa)}</p>
          </div>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Taxa de Poupanca</p>
          <p className={`text-xl font-bold ${taxaPoupanca >= 0 ? "text-emerald-500" : "text-red-500"}`}>
            {formatPercent(taxaPoupanca)}
          </p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Income vs Expense */}
        <BarChartCard
          title="Receita vs Despesa"
          data={cashFlowData}
          bars={[
            { dataKey: "receita", color: "#10b981", name: "Receita" },
            { dataKey: "despesa", color: "#ef4444", name: "Despesa" },
          ]}
        />

        {/* Top Categories */}
        {categoriaChartData.length > 0 ? (
          <DonutChartCard title="Top Categorias" data={categoriaChartData} />
        ) : (
          <div className="rounded-lg border bg-card p-4 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Sem dados de categoria para o periodo</p>
          </div>
        )}
      </div>

      {/* Monthly Comparison */}
      {lineData.length > 1 && (
        <LineChartCard
          title="Comparacao Mensal - Fluxo de Caixa"
          data={lineData}
          lines={[
            { dataKey: "fluxo", color: "#3b82f6", name: "Fluxo de Caixa" },
          ]}
        />
      )}

      {/* Top Categories Table */}
      {topCategorias.length > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <h3 className="font-semibold mb-3">Top Categorias</h3>
          <div className="space-y-2">
            {topCategorias.map((cat, idx) => {
              const maxVal = Math.max(...topCategorias.map((c) => c.total));
              const pct = maxVal > 0 ? (cat.total / maxVal) * 100 : 0;
              return (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium truncate">{cat.nome || "Outros"}</span>
                    <span className="text-muted-foreground ml-2 shrink-0">{formatCurrency(cat.total)}</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div
                      className="h-2 rounded-full transition-all"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: cat.cor || CHART_COLORS[idx % CHART_COLORS.length],
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!relatorio && !isLoading && (
        <div className="text-center py-12 text-muted-foreground">
          <FileBarChart className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhum dado para o periodo selecionado</p>
          <p className="text-sm">Adicione transacoes para gerar relatorios.</p>
        </div>
      )}
    </div>
  );
}
