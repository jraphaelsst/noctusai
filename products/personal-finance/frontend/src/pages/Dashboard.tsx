import { useDashboardKPIs, useDashboardResumo } from "@/hooks/useDashboard";
import { MonthlyNarrativeCard } from "@/components/MonthlyNarrativeCard";
import { usePatrimonioHistorico } from "@/hooks/usePatrimonio";
import { useTransacoesPorCategoria } from "@/hooks/useTransacoes";
import { AreaChartCard } from "@/components/charts/AreaChartCard";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { BarChartCard } from "@/components/charts/BarChartCard";
import { KPICardSkeleton, ChartSkeleton, ListSkeleton } from "@/components/Skeleton";
import { formatCurrency, formatPercent, formatDate, getCurrentMonth, getMonthLabel } from "@/lib/utils";
import type { DashboardKPIs, Transacao, Recorrente, Meta } from "@/types";
import {
  TrendingUp, TrendingDown, Wallet, ArrowLeftRight,
  PiggyBank, BarChart3, Target, CalendarClock,
} from "lucide-react";

function KPICard({
  label,
  value,
  formatted,
  icon: Icon,
  isPercent = false,
}: {
  label: string;
  value: number;
  formatted: string;
  icon: React.ElementType;
  isPercent?: boolean;
}) {
  const isPositive = value >= 0;
  return (
    <div className="rounded-lg border bg-card p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold">{formatted}</span>
        <span className={`flex items-center text-xs font-medium ${isPositive ? "text-emerald-500" : "text-red-500"}`}>
          {isPositive ? <TrendingUp className="w-3 h-3 mr-0.5" /> : <TrendingDown className="w-3 h-3 mr-0.5" />}
          {isPercent ? formatPercent(value) : (isPositive ? "Positivo" : "Negativo")}
        </span>
      </div>
    </div>
  );
}

function TransacaoRow({ t }: { t: Transacao }) {
  const isReceita = t.tipo === "receita";
  return (
    <div className="flex items-center justify-between py-2 border-b last:border-b-0">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-xs shrink-0"
          style={{ backgroundColor: t.categoria?.cor ? `${t.categoria.cor}20` : "hsl(var(--muted))" }}
        >
          {t.categoria?.icone || (isReceita ? "+" : "-")}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{t.descricao || t.comerciante || "Transacao"}</p>
          <p className="text-xs text-muted-foreground">{formatDate(t.data)} {t.conta?.nome ? `- ${t.conta.nome}` : ""}</p>
        </div>
      </div>
      <span className={`text-sm font-semibold whitespace-nowrap ${isReceita ? "text-emerald-500" : "text-red-500"}`}>
        {isReceita ? "+" : "-"}{formatCurrency(Math.abs(t.valor))}
      </span>
    </div>
  );
}

function ContaProxima({ r }: { r: Recorrente }) {
  return (
    <div className="flex items-center justify-between py-2 border-b last:border-b-0">
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">{r.nome}</p>
        <p className="text-xs text-muted-foreground">
          {r.proxima_data ? formatDate(r.proxima_data) : "Sem data"} {r.categoria?.nome ? `- ${r.categoria.nome}` : ""}
        </p>
      </div>
      <span className={`text-sm font-semibold whitespace-nowrap ${r.tipo === "receita" ? "text-emerald-500" : "text-red-500"}`}>
        {formatCurrency(r.valor)}
      </span>
    </div>
  );
}

function MetaResumo({ m }: { m: Meta }) {
  const pct = m.valor_alvo > 0 ? (m.valor_atual / m.valor_alvo) * 100 : 0;
  return (
    <div className="py-2 border-b last:border-b-0 space-y-1">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium truncate">{m.nome}</p>
        <span className="text-xs text-muted-foreground">{pct.toFixed(0)}%</span>
      </div>
      <div className="w-full bg-muted rounded-full h-2">
        <div
          className="h-2 rounded-full bg-primary transition-all"
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        {formatCurrency(m.valor_atual)} de {formatCurrency(m.valor_alvo)}
      </p>
    </div>
  );
}

export default function Dashboard() {
  const { data: kpis, isPending: kpisPending } = useDashboardKPIs();
  const { data: resumo, isPending: resumoPending } = useDashboardResumo();

  const currentMonth = getCurrentMonth();
  const [ano, mes] = currentMonth.split("-");
  const dataInicio = `${ano}-${mes}-01`;
  const lastDay = new Date(parseInt(ano), parseInt(mes), 0).getDate();
  const dataFim = `${ano}-${mes}-${String(lastDay).padStart(2, "0")}`;

  const { data: patrimonioHist } = usePatrimonioHistorico(12);
  const { data: transacoesCat } = useTransacoesPorCategoria(dataInicio, dataFim);

  const showSkeleton = (kpisPending && !kpis) || (resumoPending && !resumo);

  if (showSkeleton) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICardSkeleton />
          <KPICardSkeleton />
          <KPICardSkeleton />
          <KPICardSkeleton />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2"><ChartSkeleton /></div>
          <ChartSkeleton />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <ListSkeleton />
          <ListSkeleton />
          <ListSkeleton />
        </div>
      </div>
    );
  }

  const k: DashboardKPIs = kpis || {
    patrimonio_liquido: 0,
    total_ativos: 0,
    total_passivos: 0,
    receita_mensal: 0,
    despesa_mensal: 0,
    fluxo_caixa_mensal: 0,
    taxa_poupanca: 0,
    retorno_investimentos: 0,
    valor_investimentos: 0,
  };

  const patrimonioChartData = (patrimonioHist || []).map((snap) => ({
    label: formatDate(snap.data),
    valor: snap.patrimonio_liquido,
  }));

  const categoriasChartData = (transacoesCat || []).map((item: any) => ({
    nome: item.categoria || item.nome || "Outros",
    total: item.total || item.valor || 0,
    cor: item.cor,
  }));

  const receitaDespesaData = [
    { label: getMonthLabel(currentMonth), receita: k.receita_mensal, despesa: k.despesa_mensal },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* AI monthly-narrative digest — gated by `pf.monthly_narrative` consent. */}
      <MonthlyNarrativeCard />

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Patrimonio Liquido"
          value={k.patrimonio_liquido}
          formatted={formatCurrency(k.patrimonio_liquido)}
          icon={Wallet}
        />
        <KPICard
          label="Fluxo de Caixa Mensal"
          value={k.fluxo_caixa_mensal}
          formatted={formatCurrency(k.fluxo_caixa_mensal)}
          icon={ArrowLeftRight}
        />
        <KPICard
          label="Taxa de Poupanca"
          value={k.taxa_poupanca}
          formatted={formatPercent(k.taxa_poupanca)}
          icon={PiggyBank}
          isPercent
        />
        <KPICard
          label="Retorno Investimentos"
          value={k.retorno_investimentos}
          formatted={formatPercent(k.retorno_investimentos)}
          icon={BarChart3}
          isPercent
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <AreaChartCard
            title="Patrimonio Historico"
            data={patrimonioChartData}
            dataKey="valor"
            xKey="label"
            color="#10b981"
          />
        </div>
        <DonutChartCard title="Despesas por Categoria" data={categoriasChartData} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-3">
          <BarChartCard
            title="Receita vs Despesa"
            data={receitaDespesaData}
            bars={[
              { dataKey: "receita", color: "#10b981", name: "Receita" },
              { dataKey: "despesa", color: "#ef4444", name: "Despesa" },
            ]}
          />
        </div>
      </div>

      {/* Lists */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Recent Transactions */}
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <ArrowLeftRight className="w-4 h-4 text-muted-foreground" />
            <h3 className="font-semibold">Transacoes Recentes</h3>
          </div>
          {resumo?.transacoes_recentes && resumo.transacoes_recentes.length > 0 ? (
            resumo.transacoes_recentes.slice(0, 5).map((t) => (
              <TransacaoRow key={t.id} t={t} />
            ))
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">Nenhuma transacao recente</p>
          )}
        </div>

        {/* Upcoming Bills */}
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <CalendarClock className="w-4 h-4 text-muted-foreground" />
            <h3 className="font-semibold">Proximas Contas</h3>
          </div>
          {resumo?.proximas_contas && resumo.proximas_contas.length > 0 ? (
            resumo.proximas_contas.slice(0, 5).map((r) => (
              <ContaProxima key={r.id} r={r} />
            ))
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">Nenhuma conta proxima</p>
          )}
        </div>

        {/* Active Goals */}
        <div className="rounded-lg border bg-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Target className="w-4 h-4 text-muted-foreground" />
            <h3 className="font-semibold">Metas Ativas</h3>
          </div>
          {resumo?.metas_ativas && resumo.metas_ativas.length > 0 ? (
            resumo.metas_ativas.slice(0, 5).map((m) => (
              <MetaResumo key={m.id} m={m} />
            ))
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">Nenhuma meta ativa</p>
          )}
        </div>
      </div>
    </div>
  );
}
