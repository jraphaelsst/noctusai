/**
 * Edição de Fotos — Painel (`/edicao-fotos/painel`, `status_pagina` row
 * `edicao-fotos-painel`, migration 128). Dashboard: pipeline throughput ·
 * queue & health · activity · learning loop · costs (contract §8, W9,
 * migration 133 `social_wiring.fotos_painel`).
 *
 * Who: platform admin (everything, optional org filter) ∨ agency admin
 * (own org only, unconditionally — `org_id` typed only when the caller is
 * platform-scope). `fotosPermissions.dashboardScope(capacidades)` mirrors
 * the backend gate (`require_org_admin`) — `null` for a corretor.
 *
 * Revenue is billing-sourced and not shipped yet (Core, later wave) — the
 * backend always returns `custos.receita.disponivel = false` with a `nota`;
 * this page renders that note rather than inventing a number.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` /
 * `isRefreshing` come pre-computed off the seed hook — never `.isLoading`.
 */
import { useState } from "react";
import { AlertCircle, Lock } from "lucide-react";
import {
  AreaChart,
  BarChart,
  ChartCard,
  DonutChart,
  FilterBar,
  StatTile,
  StatTileRow,
  formatCompactNumber,
  formatPercent,
} from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

import { fotosPermissions, useCapacidades, usePainel } from "@/hooks/useEdicaoFotos";

const DECISAO_LABEL: Record<string, string> = { aprovar: "Aprovar", rejeitar: "Rejeitar" };
const JOB_STATUS_LABEL: Record<string, string> = {
  pending: "Pendente",
  running: "Em execução",
  completed: "Concluído",
  failed: "Falhou",
  dead_letter: "Morto",
};

function formatBRL(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function defaultRange(): { desde: string; ate: string } {
  const ate = new Date();
  const desde = new Date(ate);
  desde.setDate(desde.getDate() - 30);
  return { desde: desde.toISOString().slice(0, 10), ate: ate.toISOString().slice(0, 10) };
}

/** One row per date, one column per estado — what `AreaChart`'s `series` needs. */
function pivotPipeline(
  pontos: { data: string; estado: string; total: number }[]
): Record<string, number | string>[] {
  const byDate = new Map<string, Record<string, number | string>>();
  for (const p of pontos) {
    const row = byDate.get(p.data) ?? { data: p.data };
    row[p.estado] = p.total;
    byDate.set(p.data, row);
  }
  return Array.from(byDate.values()).sort((a, b) => String(a.data).localeCompare(String(b.data)));
}

function pipelineSeriesFor(pontos: { estado: string }[]): { key: string; label: string }[] {
  return Array.from(new Set(pontos.map((p) => p.estado))).map((estado) => ({ key: estado, label: estado }));
}

export default function Painel() {
  const { capacidades, showSkeleton } = useCapacidades();
  if (showSkeleton) return <PainelSkeleton />;
  const escopo = fotosPermissions.dashboardScope(capacidades);
  if (escopo === null) return <AcessoRestrito />;
  return <PainelView isPlatform={escopo === "platform"} />;
}

function PainelView({ isPlatform }: { isPlatform: boolean }) {
  const initial = defaultRange();
  const [desde, setDesde] = useState(initial.desde);
  const [ate, setAte] = useState(initial.ate);
  const [orgId, setOrgId] = useState("");

  const { painel, showSkeleton, isRefreshing, error, refetch } = usePainel({
    desde,
    ate,
    org_id: isPlatform && orgId.trim() ? orgId.trim() : undefined,
  });

  const pipelineData = pivotPipeline(painel?.pipeline.pontos ?? []);
  const pipelineSeries = pipelineSeriesFor(painel?.pipeline.pontos ?? []);
  const filaJobs = Object.entries(painel?.fila.jobs ?? {}).map(([estado, total]) => ({
    estado: JOB_STATUS_LABEL[estado] ?? estado,
    total,
  }));
  const veredito = Object.entries(painel?.aprendizado.veredito_ia ?? {}).map(([decisao, total]) => ({
    decisao: DECISAO_LABEL[decisao] ?? decisao,
    total,
  }));
  const custos = painel?.custos.por_categoria ?? [];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6" data-testid="edicao-fotos-painel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Painel</h1>
          <p className="text-sm text-muted-foreground">
            {painel
              ? painel.escopo === "plataforma"
                ? "Todas as organizações."
                : "Sua organização."
              : "Carregando…"}
          </p>
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="painel-atualizando">
            Atualizando…
          </span>
        )}
      </div>

      <FilterBar>
        <div className="flex items-center gap-2">
          <Label htmlFor="painel-desde">De</Label>
          <Input
            id="painel-desde"
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor="painel-ate">Até</Label>
          <Input id="painel-ate" type="date" value={ate} onChange={(e) => setAte(e.target.value)} className="w-40" />
        </div>
        {isPlatform && (
          <div className="flex items-center gap-2">
            <Label htmlFor="painel-org">Organização</Label>
            <Input
              id="painel-org"
              placeholder="Todas"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              className="w-56"
              data-testid="painel-org-filter"
            />
          </div>
        )}
      </FilterBar>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : (
        <>
          <StatTileRow>
            <StatTile
              label="Lotes criados"
              value={painel ? formatCompactNumber(painel.atividade.lotes_criados) : "—"}
              loading={showSkeleton}
            />
            <StatTile
              label="Fotos enviadas"
              value={painel ? formatCompactNumber(painel.atividade.fotos_enviadas) : "—"}
              loading={showSkeleton}
            />
            <StatTile
              label="Taxa de aprovação"
              value={painel ? formatPercent(painel.aprendizado.taxa_aprovacao * 100) : "—"}
              loading={showSkeleton}
            />
            <StatTile
              label="Acerto da IA"
              value={
                painel && painel.aprendizado.acerto_ia_pct !== null
                  ? formatPercent(painel.aprendizado.acerto_ia_pct)
                  : "—"
              }
              hint={
                painel && painel.aprendizado.acerto_ia_pct === null
                  ? "sem fotos com veredito e decisão no período"
                  : undefined
              }
              loading={showSkeleton}
            />
            <StatTile
              label="Custo total"
              value={painel ? formatBRL(painel.custos.total_brl) : "—"}
              loading={showSkeleton}
            />
            <StatTile
              label="Margem"
              value={painel ? formatBRL(painel.custos.margem_brl) : "—"}
              hint={painel && !painel.custos.receita.disponivel ? painel.custos.receita.nota ?? undefined : undefined}
              loading={showSkeleton}
            />
          </StatTileRow>

          <ChartCard
            title="Fluxo do pipeline"
            subtitle="Fotos por estado, ao longo do tempo."
            loading={showSkeleton}
            isEmpty={pipelineData.length === 0}
          >
            <AreaChart data={pipelineData} xKey="data" series={pipelineSeries} stacked height={300} />
          </ChartCard>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard
              title="Fila e saúde"
              subtitle="Jobs de edição/avaliação por status — plataforma inteira."
              loading={showSkeleton}
              isEmpty={filaJobs.every((j) => j.total === 0)}
            >
              <BarChart data={filaJobs} xKey="estado" series={[{ key: "total", label: "Jobs" }]} horizontal />
            </ChartCard>

            <ChartCard
              title="Atividade diária"
              subtitle="Lotes, fotos e decisões por dia."
              loading={showSkeleton}
              isEmpty={(painel?.atividade.serie_diaria.length ?? 0) === 0}
            >
              <AreaChart
                data={painel?.atividade.serie_diaria ?? []}
                xKey="data"
                series={[
                  { key: "lotes", label: "Lotes" },
                  { key: "fotos", label: "Fotos" },
                  { key: "decisoes", label: "Decisões" },
                ]}
                height={280}
              />
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard
              title="Veredito da IA"
              subtitle="Recomendações do avaliador automático no período."
              loading={showSkeleton}
              isEmpty={veredito.every((v) => v.total === 0)}
            >
              <DonutChart data={veredito} nameKey="decisao" valueKey="total" />
            </ChartCard>

            <ChartCard
              title="Custos por categoria"
              subtitle="OpenAI (edição + visão), armazenamento, taxas de pagamento — em BRL."
              loading={showSkeleton}
              isEmpty={custos.length === 0}
            >
              <BarChart data={custos} xKey="categoria" series={[{ key: "total_brl", label: "R$" }]} />
            </ChartCard>
          </div>

          {painel && !painel.custos.receita.disponivel && (
            <Card className="border-amber-500/40 bg-amber-500/5" data-testid="painel-sem-faturamento">
              <CardContent className="flex items-start gap-3 p-4">
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                <p className="text-sm">
                  {painel.custos.receita.nota ?? "Sem dados de faturamento — a margem reflete apenas custos."}
                </p>
              </CardContent>
            </Card>
          )}

          {painel && painel.fila.travados > 0 && (
            <p className="text-xs text-muted-foreground" data-testid="painel-travados">
              {painel.fila.travados} job(s) travado(s) na fila — verifique o worker.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="painel-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da organização e da plataforma.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function PainelSkeleton() {
  return (
    <div className="space-y-3 p-6" data-testid="painel-loading">
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-24 w-full" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar o painel.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
