import { useState, useMemo } from "react";
import { useRelatorioMensal, useRelatorioAnual, useFluxoCaixa } from "@/hooks/useRelatorios";
import { BarChartCard } from "@/components/charts/BarChartCard";
import { LineChartCard } from "@/components/charts/LineChartCard";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { formatCurrency, formatPercent, getCurrentMonth, getMonthLabel } from "@/lib/utils";
import { CHART_COLORS } from "@/lib/constants";
import { FileBarChart, TrendingUp, TrendingDown, Loader2 } from "lucide-react";

type TabView = "mensal" | "anual" | "fluxo";

const tabClass = (active: boolean) =>
  `px-4 py-2 text-sm font-medium rounded-md transition ${
    active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
  }`;

function MensalView({ mes, onMesChange }: { mes: string; onMesChange: (m: string) => void }) {
  // `isFetching` (not `isLoading`) drives the subtle "Atualizando" badge
  // below — placeholderData keeps the previous month's totals on screen
  // during a `mes` change, but these summary cards carry no visible date,
  // and the Mes selector updates instantly; without a signal the numbers
  // would silently read as the newly-selected month's while still being
  // the old one's.
  const { data: relatorio, isLoading, isFetching } = useRelatorioMensal(mes);

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
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const rel = relatorio || {} as any;
  const receita = rel.receita_total || 0;
  const despesa = rel.despesa_total || 0;
  const fluxoCaixa = receita - despesa;
  const taxaPoupanca = receita > 0 ? ((receita - despesa) / receita) * 100 : 0;
  const topCategorias: { nome: string; total: number; cor?: string }[] = rel.top_categorias || [];
  const categoriaChartData = topCategorias.map((c, idx) => ({
    nome: c.nome || "Outros",
    total: c.total || 0,
    cor: c.cor || CHART_COLORS[idx % CHART_COLORS.length],
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-muted-foreground">Mes:</label>
        <select value={mes} onChange={(e) => onMesChange(e.target.value)} className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary">
          {meses.map((m) => (<option key={m} value={m}>{getMonthLabel(m)}</option>))}
        </select>
        {isFetching && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Atualizando...
          </span>
        )}
      </div>

      <div className={`grid grid-cols-1 sm:grid-cols-4 gap-4 transition-opacity ${isFetching ? "opacity-60" : ""}`}>
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
          <div className={`flex items-center gap-2 ${fluxoCaixa >= 0 ? "text-emerald-500" : "text-red-500"}`}>
            {fluxoCaixa >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <p className="text-xl font-bold">{formatCurrency(fluxoCaixa)}</p>
          </div>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Taxa de Poupanca</p>
          <p className={`text-xl font-bold ${taxaPoupanca >= 0 ? "text-emerald-500" : "text-red-500"}`}>{formatPercent(taxaPoupanca)}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <BarChartCard
          title="Receita vs Despesa"
          data={[{ label: getMonthLabel(mes), receita, despesa }]}
          bars={[
            { dataKey: "receita", color: "#10b981", name: "Receita" },
            { dataKey: "despesa", color: "#ef4444", name: "Despesa" },
          ]}
        />
        {categoriaChartData.length > 0 ? (
          <DonutChartCard title="Top Categorias" data={categoriaChartData} />
        ) : (
          <div className="rounded-lg border bg-card p-4 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Sem dados de categoria para o periodo</p>
          </div>
        )}
      </div>

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
                    <div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: cat.cor || CHART_COLORS[idx % CHART_COLORS.length] }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

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

function AnualView({ ano, onAnoChange }: { ano: number; onAnoChange: (a: number) => void }) {
  // Same isFetching-indicator rationale as MensalView above — the Ano
  // selector updates instantly while the totals below carry no visible year.
  const { data: relatorio, isLoading, isFetching } = useRelatorioAnual(ano);

  const anos = useMemo(() => {
    const now = new Date().getFullYear();
    return Array.from({ length: 5 }, (_, i) => now - i);
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const rel = relatorio || {} as any;
  const receitaAnual = rel.receita_anual || 0;
  const despesaAnual = rel.despesa_anual || 0;
  const fluxoAnual = rel.fluxo_liquido_anual || 0;
  const taxaPoupanca = rel.taxa_poupanca_anual || 0;
  const mesesData: any[] = rel.meses || [];

  const chartData = mesesData.map((m: any) => ({
    label: getMonthLabel(m.mes),
    receita: m.receita_total || 0,
    despesa: m.despesa_total || 0,
  }));

  const fluxoData = mesesData.map((m: any) => ({
    label: getMonthLabel(m.mes),
    fluxo: m.fluxo_liquido || 0,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-muted-foreground">Ano:</label>
        <select value={ano} onChange={(e) => onAnoChange(Number(e.target.value))} className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary">
          {anos.map((a) => (<option key={a} value={a}>{a}</option>))}
        </select>
        {isFetching && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Atualizando...
          </span>
        )}
      </div>

      <div className={`grid grid-cols-1 sm:grid-cols-4 gap-4 transition-opacity ${isFetching ? "opacity-60" : ""}`}>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Receita Anual</p>
          <p className="text-xl font-bold text-emerald-500">{formatCurrency(receitaAnual)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Despesa Anual</p>
          <p className="text-xl font-bold text-red-500">{formatCurrency(despesaAnual)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Fluxo Liquido</p>
          <div className={`flex items-center gap-2 ${fluxoAnual >= 0 ? "text-emerald-500" : "text-red-500"}`}>
            {fluxoAnual >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <p className="text-xl font-bold">{formatCurrency(fluxoAnual)}</p>
          </div>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Taxa de Poupanca</p>
          <p className={`text-xl font-bold ${taxaPoupanca >= 0 ? "text-emerald-500" : "text-red-500"}`}>{formatPercent(taxaPoupanca)}</p>
        </div>
      </div>

      {chartData.length > 0 && (
        <BarChartCard
          title="Receita vs Despesa Mensal"
          data={chartData}
          bars={[
            { dataKey: "receita", color: "#10b981", name: "Receita" },
            { dataKey: "despesa", color: "#ef4444", name: "Despesa" },
          ]}
        />
      )}

      {fluxoData.length > 0 && (
        <LineChartCard
          title="Fluxo de Caixa Mensal"
          data={fluxoData}
          lines={[{ dataKey: "fluxo", color: "#3b82f6", name: "Fluxo Liquido" }]}
        />
      )}
    </div>
  );
}

function FluxoCaixaView() {
  const now = new Date();
  const mesAtual = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [dataInicio, setDataInicio] = useState(`${mesAtual}-01`);
  const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const [dataFim, setDataFim] = useState(`${mesAtual}-${String(lastDay).padStart(2, "0")}`);

  const { data: fluxo, isLoading } = useFluxoCaixa(dataInicio, dataFim);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const fluxoData: any[] = (fluxo as any)?.fluxo || [];

  const totalReceitas = fluxoData.reduce((acc, d) => acc + (d.receitas || 0), 0);
  const totalDespesas = fluxoData.reduce((acc, d) => acc + (d.despesas || 0), 0);
  const totalLiquido = totalReceitas - totalDespesas;

  const chartData = fluxoData.map((d: any) => ({
    label: d.data?.slice(5) || "",
    receitas: d.receitas || 0,
    despesas: d.despesas || 0,
    liquido: d.liquido || 0,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-muted-foreground">De:</label>
          <input type="date" value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-muted-foreground">Ate:</label>
          <input type="date" value={dataFim} onChange={(e) => setDataFim(e.target.value)} className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Total Receitas</p>
          <p className="text-xl font-bold text-emerald-500">{formatCurrency(totalReceitas)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Total Despesas</p>
          <p className="text-xl font-bold text-red-500">{formatCurrency(totalDespesas)}</p>
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Liquido</p>
          <div className={`flex items-center gap-2 ${totalLiquido >= 0 ? "text-emerald-500" : "text-red-500"}`}>
            {totalLiquido >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
            <p className="text-xl font-bold">{formatCurrency(totalLiquido)}</p>
          </div>
        </div>
      </div>

      {chartData.length > 0 ? (
        <>
          <BarChartCard
            title="Fluxo Diario"
            data={chartData}
            bars={[
              { dataKey: "receitas", color: "#10b981", name: "Receitas" },
              { dataKey: "despesas", color: "#ef4444", name: "Despesas" },
            ]}
          />
          <LineChartCard
            title="Fluxo Liquido Diario"
            data={chartData}
            lines={[{ dataKey: "liquido", color: "#3b82f6", name: "Liquido" }]}
          />
        </>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <FileBarChart className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhum dado para o periodo selecionado</p>
        </div>
      )}

      {fluxoData.length > 0 && (
        <div className="rounded-lg border bg-card overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                <th className="text-right p-3 font-medium text-muted-foreground">Receitas</th>
                <th className="text-right p-3 font-medium text-muted-foreground">Despesas</th>
                <th className="text-right p-3 font-medium text-muted-foreground">Liquido</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {fluxoData.map((d: any, idx: number) => (
                <tr key={idx} className="hover:bg-accent/50">
                  <td className="p-3">{d.data}</td>
                  <td className="p-3 text-right text-emerald-500">{formatCurrency(d.receitas || 0)}</td>
                  <td className="p-3 text-right text-red-500">{formatCurrency(d.despesas || 0)}</td>
                  <td className={`p-3 text-right font-medium ${(d.liquido || 0) >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                    {formatCurrency(d.liquido || 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Relatorios() {
  const [tab, setTab] = useState<TabView>("mensal");
  const [mesSelecionado, setMesSelecionado] = useState(getCurrentMonth());
  const [anoSelecionado, setAnoSelecionado] = useState(new Date().getFullYear());

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Relatorios</h1>
      </div>

      <div className="flex items-center gap-2">
        <button onClick={() => setTab("mensal")} className={tabClass(tab === "mensal")}>Mensal</button>
        <button onClick={() => setTab("anual")} className={tabClass(tab === "anual")}>Anual</button>
        <button onClick={() => setTab("fluxo")} className={tabClass(tab === "fluxo")}>Fluxo de Caixa</button>
      </div>

      {tab === "mensal" && <MensalView mes={mesSelecionado} onMesChange={setMesSelecionado} />}
      {tab === "anual" && <AnualView ano={anoSelecionado} onAnoChange={setAnoSelecionado} />}
      {tab === "fluxo" && <FluxoCaixaView />}
    </div>
  );
}
