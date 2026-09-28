/**
 * Dashboard — `/` (CONTRACT.md ninho-vazio §Frontend FE-A, on
 * `GET /api/dashboard`).
 *
 * Every number rendered here is read straight off the payload — the page
 * computes no KPI of its own (the contract defines each one server-side and
 * its tests assert those definitions). Charts are the seed organs from
 * `@noctusai/lib/design-system` (ChartCard / StatTile / AreaChart / BarChart
 * / DonutChart), never a local recharts wrapper.
 *
 * Money is integer centavos end to end: chart rows keep the raw centavos
 * and the value formatter renders BRL, so no value is ever rounded twice.
 *
 * Two loading signals, never `isLoading`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarHeart,
  CircleDollarSign,
  PiggyBank,
  Percent,
  TrendingDown,
  UserRound,
  Wallet,
} from "lucide-react";
import {
  AreaChart,
  BarChart,
  ChartCard,
  DonutChart,
  PT_BR_MONTH_LABELS_SHORT,
  StatTile,
  StatTileRow,
  formatPercent,
} from "@noctusai/lib/design-system";
import { ErrorState, Select } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { formatBRLFromCents } from "@/lib/money";
import { useDashboard, type DashboardResponse } from "@/hooks/useDashboard";
import { NIVEL_GRUPOTERAPIA_LABELS } from "@/hooks/usePlanos";

const STATUS_LABELS: Record<string, string> = {
  pendente: "Pendente",
  ativo: "Ativo",
  atrasado: "Atrasado",
  pausado: "Pausado",
  cancelado: "Cancelado",
};

const ORIGEM_LABELS: Record<string, string> = {
  cadastro: "Cadastro no site",
  checkout: "Checkout",
  aplicacao: "Aplicação",
  convite: "Convite",
};

const JANELAS = [6, 12, 24] as const;

/** `"2026-09"` → `"Set/26"`. Anything unparseable is shown as-is. */
export function formatMes(mes: string): string {
  const [ano, m] = mes.split("-");
  const idx = Number(m) - 1;
  if (!ano || !(idx >= 0 && idx < 12)) return mes;
  return `${PT_BR_MONTH_LABELS_SHORT[idx]}/${ano.slice(-2)}`;
}

function formatDataHora(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function formatCount(n: number): string {
  return n.toLocaleString("pt-BR");
}

export default function Dashboard() {
  const [meses, setMeses] = useState<number>(12);
  const { data, isPending, isFetching, error } = useDashboard(meses);

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Membros, receita e grupoterapia do Ninho Vazio.
            {data ? ` Atualizado em ${formatDataHora(data.gerado_em)}.` : ""}
            {/* lying-loading-ok: text-only suffix, never unmounts the data below */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <Select
          className="w-40"
          value={String(meses)}
          onChange={(e) => setMeses(Number(e.target.value))}
          aria-label="Período do dashboard"
        >
          {JANELAS.map((n) => (
            <option key={n} value={n}>
              Últimos {n} meses
            </option>
          ))}
        </Select>
      </div>

      {error && !data ? (
        <ErrorState message={errorMessage(error)} />
      ) : (
        <DashboardBody data={data} showSkeleton={showSkeleton} />
      )}
    </div>
  );
}

function DashboardBody({ data, showSkeleton }: { data: DashboardResponse | undefined; showSkeleton: boolean }) {
  const kpis = data?.kpis;
  const series = data?.series;

  const mensal = series?.mensal ?? [];
  const mensalVazio = mensal.every(
    (m) => !m.entradas_centavos && !m.saidas_centavos && !m.novos_membros && !m.cancelamentos && !m.mrr_centavos,
  );

  const porPlano = useMemo(
    () =>
      (kpis?.por_plano ?? []).map((p) => ({
        rotulo: `${p.nome} · ${NIVEL_GRUPOTERAPIA_LABELS[p.nivel_grupoterapia] ?? p.nivel_grupoterapia}`,
        membros: p.membros,
      })),
    [kpis?.por_plano],
  );
  const porOrigem = useMemo(
    () => (series?.origem_membros ?? []).map((o) => ({ rotulo: ORIGEM_LABELS[o.origem] ?? o.origem, membros: o.membros })),
    [series?.origem_membros],
  );
  const porStatus = useMemo(
    () => (series?.status_membros ?? []).map((s) => ({ rotulo: STATUS_LABELS[s.status] ?? s.status, membros: s.membros })),
    [series?.status_membros],
  );
  const ocupacao = useMemo(
    () =>
      (series?.grupoterapia ?? []).map((g) => ({
        rotulo: `${g.titulo} (${new Date(g.inicio).toLocaleDateString("pt-BR")})`,
        reservas: g.reservas,
        vagas_livres: Math.max(g.vagas_fala - g.reservas, 0),
      })),
    [series?.grupoterapia],
  );

  const semMembros = (rows: Array<{ membros: number }>) => rows.every((r) => !r.membros);

  return (
    <>
      <StatTileRow>
        <StatTile
          icon={UserRound}
          label="Membros ativos"
          loading={showSkeleton}
          value={kpis ? formatCount(kpis.membros_ativos) : null}
          hint={kpis ? `de ${formatCount(kpis.membros_total)} no total` : undefined}
        />
        <StatTile
          icon={CircleDollarSign}
          label="MRR"
          loading={showSkeleton}
          value={kpis ? formatBRLFromCents(kpis.mrr_centavos) : null}
          hint="Receita recorrente mensal"
        />
        <StatTile
          icon={Wallet}
          label="ARPU"
          loading={showSkeleton}
          value={kpis ? formatBRLFromCents(kpis.arpu_centavos) : null}
          hint="Por membro pagante"
        />
        <StatTile
          icon={AlertTriangle}
          label="Em carência"
          loading={showSkeleton}
          value={kpis ? formatCount(kpis.em_carencia) : null}
          hint="Cobrança falhou, acesso mantido"
        />
      </StatTileRow>
      <StatTileRow>
        <StatTile
          icon={TrendingDown}
          label="Churn do mês"
          loading={showSkeleton}
          value={kpis ? formatPercent(kpis.churn_mes_pct) : null}
          hint={kpis ? `${formatCount(kpis.novos_mes)} novos · ${formatCount(kpis.cancelamentos_mes)} cancelamentos` : undefined}
        />
        <StatTile
          icon={CircleDollarSign}
          label="Receita do mês"
          loading={showSkeleton}
          value={kpis ? formatBRLFromCents(kpis.receita_mes_centavos) : null}
        />
        <StatTile
          icon={PiggyBank}
          label="Saldo do mês"
          loading={showSkeleton}
          value={kpis ? formatBRLFromCents(kpis.saldo_mes_centavos) : null}
          hint="Entradas menos saídas"
        />
        <StatTile
          icon={Percent}
          label="Conversão pago"
          loading={showSkeleton}
          value={kpis ? formatPercent(kpis.conversao_pago_pct) : null}
          hint="Ativos em plano pago"
        />
      </StatTileRow>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Entradas × saídas"
          subtitle="Fluxo de caixa por mês"
          loading={showSkeleton}
          isEmpty={!showSkeleton && mensalVazio}
          emptyMessage="Nenhum lançamento no período."
        >
          <BarChart
            data={mensal}
            xKey="mes"
            series={[
              { key: "entradas_centavos", label: "Entradas" },
              { key: "saidas_centavos", label: "Saídas" },
            ]}
            valueFormatter={formatBRLFromCents}
            xTickFormatter={formatMes}
          />
        </ChartCard>
        <ChartCard
          title="MRR"
          subtitle="Receita recorrente ao fim de cada mês"
          loading={showSkeleton}
          isEmpty={!showSkeleton && mensal.every((m) => !m.mrr_centavos)}
          emptyMessage="Nenhuma assinatura paga no período."
        >
          <AreaChart
            data={mensal}
            xKey="mes"
            series={[{ key: "mrr_centavos", label: "MRR" }]}
            valueFormatter={formatBRLFromCents}
            xTickFormatter={formatMes}
          />
        </ChartCard>
        <ChartCard
          title="Novos × cancelamentos"
          subtitle="Membros por mês"
          loading={showSkeleton}
          isEmpty={!showSkeleton && mensal.every((m) => !m.novos_membros && !m.cancelamentos)}
          emptyMessage="Nenhuma entrada ou saída de membros no período."
        >
          <BarChart
            data={mensal}
            xKey="mes"
            series={[
              { key: "novos_membros", label: "Novos" },
              { key: "cancelamentos", label: "Cancelamentos" },
            ]}
            valueFormatter={formatCount}
            xTickFormatter={formatMes}
          />
        </ChartCard>
        <ChartCard
          title="Membros por plano"
          loading={showSkeleton}
          isEmpty={!showSkeleton && semMembros(porPlano)}
          emptyMessage="Nenhum membro em plano ainda."
        >
          <DonutChart data={porPlano} nameKey="rotulo" valueKey="membros" valueFormatter={formatCount} />
        </ChartCard>
        <ChartCard
          title="Membros por origem"
          loading={showSkeleton}
          isEmpty={!showSkeleton && semMembros(porOrigem)}
          emptyMessage="Nenhum membro cadastrado ainda."
        >
          <DonutChart data={porOrigem} nameKey="rotulo" valueKey="membros" valueFormatter={formatCount} />
        </ChartCard>
        <ChartCard
          title="Membros por status"
          loading={showSkeleton}
          isEmpty={!showSkeleton && semMembros(porStatus)}
          emptyMessage="Nenhum membro cadastrado ainda."
        >
          <DonutChart data={porStatus} nameKey="rotulo" valueKey="membros" valueFormatter={formatCount} />
        </ChartCard>
      </div>

      <ChartCard
        title="Ocupação da grupoterapia"
        subtitle="Vagas de fala reservadas nas próximas e últimas sessões"
        loading={showSkeleton}
        isEmpty={!showSkeleton && ocupacao.length === 0}
        emptyMessage="Nenhuma sessão de grupoterapia agendada ou realizada."
        actions={<CalendarHeart className="h-5 w-5 text-muted-foreground" aria-hidden="true" />}
      >
        <BarChart
          data={ocupacao}
          xKey="rotulo"
          horizontal
          stacked
          height={Math.max(160, ocupacao.length * 36)}
          series={[
            { key: "reservas", label: "Reservadas" },
            { key: "vagas_livres", label: "Livres" },
          ]}
          valueFormatter={formatCount}
        />
      </ChartCard>
    </>
  );
}
