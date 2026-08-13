import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Camera, Clock, DollarSign, Package, Repeat, TrendingUp, Users, Wallet } from "lucide-react";
import { useDashboard } from "@/hooks/useApi";
import { Card, ErroBox, PageHeader, Spinner, StatCard } from "@/components/ui";
import { COR_STATUS, TOM_NEGOCIO } from "@/lib/status";
import { fmtMoeda, fmtMoedaCurta, fmtPercentual } from "@/lib/utils";

export default function Dashboard() {
  const { data, isLoading, error } = useDashboard();

  if (isLoading) return <Spinner />;
  if (error) return <ErroBox erro={error} />;
  if (!data) return null;

  const totalFunil = data.funil.reduce((s, e) => s + e.quantidade, 0);

  return (
    <div>
      <PageHeader
        title="Dashboard executivo"
        description="Visão geral da operação, produção e financeiro — tudo calculado sobre os dados reais."
      />

      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Captações do mês"
          value={data.captacoes_mes}
          icon={<Camera className="h-4 w-4" />}
        />
        <StatCard
          label="Entregas do mês"
          value={data.entregas_mes}
          icon={<Package className="h-4 w-4" />}
        />
        <StatCard
          label="Serviços em andamento"
          value={data.servicos_andamento}
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          label="Faturamento do mês"
          value={fmtMoeda(data.faturamento_mes)}
          icon={<DollarSign className="h-4 w-4" />}
        />
        <StatCard label="A receber" value={fmtMoeda(data.a_receber)} icon={<Wallet className="h-4 w-4" />} />
        <StatCard
          label="Ticket médio"
          value={fmtMoeda(data.ticket_medio)}
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <StatCard
          label="Clientes ativos"
          value={data.clientes_ativos}
          icon={<Users className="h-4 w-4" />}
        />
        <StatCard
          label="Recorrência"
          value={fmtPercentual(data.taxa_recorrencia)}
          hint={
            data.prazo_medio_dias != null
              ? `Prazo médio: ${data.prazo_medio_dias.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} dias`
              : "Prazo médio: —"
          }
          icon={<Repeat className="h-4 w-4" />}
        />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="mb-4">
            <h2 className="font-display text-lg">Faturamento</h2>
            <p className="text-xs text-muted-foreground">Últimos meses — valores recebidos</p>
          </div>
          <div className="h-64">
            {data.receita_por_mes.length === 0 ? (
              <p className="pt-16 text-center text-sm text-muted-foreground">Sem receita registrada.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.receita_por_mes}>
                  <defs>
                    <linearGradient id="gradReceita" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="oklch(var(--primary))" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="oklch(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(var(--border))" vertical={false} />
                  <XAxis
                    dataKey="label"
                    stroke="oklch(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="oklch(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => fmtMoedaCurta(Number(v))}
                  />
                  <Tooltip
                    formatter={(v) => fmtMoeda(Number(v))}
                    contentStyle={{
                      background: "oklch(var(--card))",
                      border: "1px solid oklch(var(--border))",
                      borderRadius: "var(--radius)",
                      color: "oklch(var(--foreground))",
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="valor"
                    name="Recebido"
                    stroke="oklch(var(--primary))"
                    strokeWidth={2}
                    fill="url(#gradReceita)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card>
          <div className="mb-4">
            <h2 className="font-display text-lg">Captações por semana</h2>
            <p className="text-xs text-muted-foreground">Ritmo da operação</p>
          </div>
          <div className="h-64">
            {data.captacoes_por_semana.length === 0 ? (
              <p className="pt-16 text-center text-sm text-muted-foreground">Sem captações registradas.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.captacoes_por_semana}>
                  <CartesianGrid strokeDasharray="3 3" stroke="oklch(var(--border))" vertical={false} />
                  <XAxis
                    dataKey="semana"
                    stroke="oklch(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="oklch(var(--muted-foreground))"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "oklch(var(--card))",
                      border: "1px solid oklch(var(--border))",
                      borderRadius: "var(--radius)",
                      color: "oklch(var(--foreground))",
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="captacoes" name="Captações" fill="oklch(var(--primary))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-display text-lg">Funil comercial</h2>
            <p className="text-xs text-muted-foreground">{totalFunil} negócio(s) no pipeline</p>
          </div>
          <Link to="/crm" className="text-sm text-primary hover:underline">
            Abrir CRM →
          </Link>
        </div>
        <div className="space-y-2">
          {data.funil.map((etapa) => (
            <div key={etapa.etapa} className="flex items-center gap-3">
              <span className="w-40 shrink-0 truncate text-sm">{etapa.label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: totalFunil ? `${Math.max(1, (etapa.quantidade / totalFunil) * 100)}%` : "0%",
                    backgroundColor: COR_STATUS[TOM_NEGOCIO[etapa.etapa] ?? "lead"],
                  }}
                />
              </div>
              <span className="w-8 shrink-0 text-right text-sm text-muted-foreground">
                {etapa.quantidade}
              </span>
              <span className="w-28 shrink-0 text-right text-sm text-muted-foreground">
                {fmtMoeda(etapa.valor)}
              </span>
            </div>
          ))}
          {data.funil.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum negócio cadastrado ainda.</p>
          )}
        </div>
      </Card>
    </div>
  );
}
