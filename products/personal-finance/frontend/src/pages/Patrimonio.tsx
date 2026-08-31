import { usePatrimonioAtual, usePatrimonioHistorico, useCriarSnapshot } from "@/hooks/usePatrimonio";
import { AreaChartCard } from "@/components/charts/AreaChartCard";
import { BarChartCard } from "@/components/charts/BarChartCard";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { PatrimonioSnapshot } from "@/types";
import { Landmark, Camera, TrendingUp, TrendingDown } from "lucide-react";

export default function Patrimonio() {
  const { data: atual, isPending: atualPending } = usePatrimonioAtual();
  const { data: historico, isPending: histPending } = usePatrimonioHistorico(24);
  const criarSnapshot = useCriarSnapshot();

  const showSkeleton = (atualPending && !atual) || (histPending && !historico);

  if (showSkeleton) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const snap: PatrimonioSnapshot | null = atual || null;
  const lista = historico || [];

  const patrimonioLiquido = snap?.patrimonio_liquido || 0;
  const totalAtivos = snap?.total_ativos || 0;
  const totalPassivos = snap?.total_passivos || 0;
  const isPositive = patrimonioLiquido >= 0;

  // Chart data
  const areaData = lista.map((s) => ({
    label: formatDate(s.data),
    valor: s.patrimonio_liquido,
  }));

  const breakdownData = lista.map((s) => ({
    label: formatDate(s.data),
    ativos: s.total_ativos,
    passivos: s.total_passivos,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Patrimonio</h1>
        <button
          onClick={() => criarSnapshot.mutate()}
          disabled={criarSnapshot.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          <Camera className="w-4 h-4" />
          {criarSnapshot.isPending ? "Criando..." : "Criar Snapshot"}
        </button>
      </div>

      {/* Current Net Worth KPI */}
      <div className="rounded-lg border bg-card p-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div>
            <p className="text-sm text-muted-foreground">Patrimonio Liquido</p>
            <div className={`flex items-center gap-2 ${isPositive ? "text-foreground" : "text-red-500"}`}>
              {isPositive ? (
                <TrendingUp className="w-6 h-6 text-emerald-500" />
              ) : (
                <TrendingDown className="w-6 h-6 text-red-500" />
              )}
              <p className="text-3xl font-bold">{formatCurrency(patrimonioLiquido)}</p>
            </div>
            {snap && (
              <p className="text-xs text-muted-foreground mt-1">Atualizado em: {formatDate(snap.data)}</p>
            )}
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Total Ativos</p>
            <p className="text-2xl font-bold text-emerald-500">{formatCurrency(totalAtivos)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Total Passivos</p>
            <p className="text-2xl font-bold text-red-500">{formatCurrency(totalPassivos)}</p>
          </div>
        </div>
      </div>

      {/* Net Worth Over Time */}
      {areaData.length > 0 ? (
        <AreaChartCard
          title="Patrimonio Liquido ao Longo do Tempo"
          data={areaData}
          dataKey="valor"
          xKey="label"
          color="#10b981"
          height={350}
        />
      ) : (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          <Landmark className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhum historico disponivel</p>
          <p className="text-sm">Crie snapshots regularmente para acompanhar a evolucao do seu patrimonio.</p>
        </div>
      )}

      {/* Assets vs Liabilities */}
      {breakdownData.length > 0 && (
        <BarChartCard
          title="Ativos vs Passivos"
          data={breakdownData}
          bars={[
            { dataKey: "ativos", color: "#10b981", name: "Ativos" },
            { dataKey: "passivos", color: "#ef4444", name: "Passivos" },
          ]}
          xKey="label"
          height={300}
        />
      )}
    </div>
  );
}
