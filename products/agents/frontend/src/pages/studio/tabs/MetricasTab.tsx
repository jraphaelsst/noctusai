/**
 * Agent Studio — "Métricas": cost, speed and size per message/reply (CONTRACT §14).
 * NoctusAI platform admins only, AGENTS app only — these figures are never shown in another product.
 * The server enforces (`require_platform_admin`); a 403 renders the restricted state.
 */
import { useMemo, useState } from "react";
import {
  AreaChart, BarChart, Button, ChartCard, EmptyState, Field, Input, LineChart, Select, StatTile, StatTileRow, TooltipProvider,
} from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { RestrictedNotice } from "@/components/studio/ConteudoChrome";
import MetricasThread from "@/components/studio/MetricasThread";
import { Nulo, TD, TH, TurnosTabela, idCurto } from "@/components/studio/MetricasTurnos";
import { useMetricasResumo, useMetricasThreads, useMetricasTurnos, type MetricasFiltro } from "@/hooks/studio/useMetricas";
import type { MetricasOrigem, MetricasResumo } from "@/api/studio/types-metricas";
import { errorMessage } from "@/lib/errors";
import { fmtBytes, fmtInt, fmtMs, fmtShare, fmtUsd, media } from "@/lib/metricasFormat";

type Periodo = "7" | "30" | "90" | "custom";
const LIMITE = 25;
const SEM_TURNOS = "Nenhum turno medido no período.";

/** Start of the local day `dias` ago — rounded so the query key is stable within a day. */
function inicioDoDia(dias: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - dias);
  return d.toISOString();
}
const dia = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const is403 = (e: unknown) => (e as { status?: number } | null)?.status === 403;

export default function MetricasTab({ agentKey }: { agentKey: string }) {
  const [periodo, setPeriodo] = useState<Periodo>("7");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [origem, setOrigem] = useState<MetricasOrigem>("canal");
  const [orgId, setOrgId] = useState("");
  const [pagina, setPagina] = useState(1);
  const [thread, setThread] = useState<string | null>(null);

  const janela = useMemo(
    () =>
      periodo === "custom"
        ? { desde: de ? new Date(`${de}T00:00:00`).toISOString() : undefined, ate: ate ? new Date(`${ate}T23:59:59.999`).toISOString() : undefined }
        : { desde: inicioDoDia(Number(periodo)), ate: undefined },
    [periodo, de, ate],
  );
  const filtro: MetricasFiltro = { ...janela, origem, org_id: orgId || undefined };
  const semOrg: MetricasFiltro = { ...filtro, org_id: undefined };

  const resumo = useMetricasResumo(agentKey, filtro);
  // The org picker lists every org of the window, so it reads the un-narrowed summary (same cache entry when no org is picked).
  const orgs = useMetricasResumo(agentKey, semOrg);
  const turnos = useMetricasTurnos(agentKey, filtro, pagina, LIMITE);
  const threads = useMetricasThreads(agentKey, filtro);

  const mudar = (fn: () => void) => {
    fn();
    setPagina(1);
    setThread(null);
  };

  const filtros = (
    <div className="flex flex-wrap items-end gap-3" data-testid="metricas-filtros">
      <Field label="Período">
        <Select value={periodo} onChange={(e) => { const v = e.target.value as Periodo; mudar(() => setPeriodo(v)); }}>
          <option value="7">Últimos 7 dias</option>
          <option value="30">Últimos 30 dias</option>
          <option value="90">Últimos 90 dias</option>
          <option value="custom">Personalizado</option>
        </Select>
      </Field>
      {periodo === "custom" && (
        <>
          <Field label="De">
            <Input type="date" value={de} max={ate || undefined} onChange={(e) => { const v = e.target.value; mudar(() => setDe(v)); }} />
          </Field>
          <Field label="Até">
            <Input type="date" value={ate} min={de || undefined} onChange={(e) => { const v = e.target.value; mudar(() => setAte(v)); }} />
          </Field>
        </>
      )}
      <Field label="Origem">
        <Select value={origem} onChange={(e) => { const v = e.target.value as MetricasOrigem; mudar(() => setOrigem(v)); }}>
          <option value="canal">Canal</option>
          <option value="eval">Avaliação</option>
          <option value="todos">Todos</option>
        </Select>
      </Field>
      <Field label="Organização">
        <Select value={orgId} onChange={(e) => { const v = e.target.value; mudar(() => setOrgId(v)); }}>
          <option value="">Todas as organizações</option>
          {orgId && !(orgs.data?.por_org ?? []).some((o) => o.org_id === orgId) && <option value={orgId}>{idCurto(orgId)}</option>}
          {(orgs.data?.por_org ?? []).map((o) => (
            <option key={o.org_id} value={o.org_id}>
              {idCurto(o.org_id)} · {fmtInt(o.turnos)} turnos
            </option>
          ))}
        </Select>
      </Field>
    </div>
  );

  let corpo;
  if (resumo.showSkeleton) corpo = <StudioLoading rows={4} testId="metricas-loading" />;
  else if (resumo.isError) corpo = is403(resumo.error) ? <RestrictedNotice error={resumo.error} /> : <StudioError error={resumo.error} onRetry={resumo.refetch} mensagem={`Não foi possível carregar as métricas. ${errorMessage(resumo.error)}`} />;
  else if (!resumo.data || resumo.data.resumo.turnos === 0)
    corpo = <EmptyState message={`${SEM_TURNOS} Amplie o período ou troque a origem (Canal, Avaliação, Todos) para ver outros turnos.`} />;
  else {
    const d = resumo.data;
    const r = d.resumo;
    corpo = (
      <>
        {d.truncado && (
          <p className="rounded-lg border border-border bg-card p-3 text-sm text-muted-foreground" role="status" data-testid="metricas-truncado">
            Há mais turnos no período do que o limite de leitura: os números abaixo cobrem apenas os mais recentes. Reduza o período ou filtre por organização.
          </p>
        )}
        <Kpis r={r} />
        <div className="grid gap-4 lg:grid-cols-3">
          <ChartCard title="Custo por dia" subtitle="USD">
            <AreaChart data={d.serie_diaria} xKey="dia" series={[{ key: "custo_usd", label: "Custo (USD)" }]} height={220} valueFormatter={(v) => fmtUsd(v)} xTickFormatter={dia} />
          </ChartCard>
          <ChartCard title="Turnos por dia">
            <BarChart data={d.serie_diaria} xKey="dia" series={[{ key: "turnos", label: "Turnos" }]} height={220} valueFormatter={fmtInt} xTickFormatter={dia} />
          </ChartCard>
          <ChartCard title="Latência p95 por dia" subtitle="turno e LLM">
            <LineChart
              data={d.serie_diaria}
              xKey="dia"
              series={[{ key: "turno_ms_p95", label: "Turno p95" }, { key: "llm_ms_p95", label: "LLM p95" }]}
              height={220}
              valueFormatter={fmtMs}
              xTickFormatter={dia}
            />
          </ChartCard>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Grupo titulo="Por versão compilada" testId="metricas-por-versao" rotulo="Versão" linhas={d.por_versao.map((g) => ({ id: g.compiled_hash ?? "", rotulo: g.compiled_hash ? g.compiled_hash.slice(0, 10) : null, r: g }))} semRotulo="Turnos sem hash de versão compilada." />
          <Grupo titulo="Por organização" testId="metricas-por-org" rotulo="Org" linhas={d.por_org.map((g) => ({ id: g.org_id, rotulo: idCurto(g.org_id), r: g }))} semRotulo="" />
        </div>
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Conversas mais caras</h2>
          {threads.showSkeleton ? (
            <StudioLoading rows={2} />
          ) : threads.isError ? (
            <StudioError error={threads.error} onRetry={threads.refetch} />
          ) : (threads.data?.itens ?? []).length === 0 ? (
            <EmptyState message="Nenhuma conversa com turnos medidos no período." />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border bg-card">
              <table className="w-full text-sm" data-testid="metricas-threads">
                <thead className="border-b border-border text-left text-xs text-muted-foreground">
                  <tr><TH>Conversa</TH><TH>Turnos</TH><TH>Custo</TH><TH>Custo/turno</TH><TH>Turno p95</TH></tr>
                </thead>
                <tbody>
                  {(threads.data?.itens ?? []).slice().sort((a, b) => b.custo_usd - a.custo_usd).map((t) => (
                    <tr key={t.thread_id} className="border-b border-border last:border-0">
                      <TD>
                        <button type="button" className="font-mono text-xs text-primary underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring" aria-label={`Abrir conversa ${idCurto(t.thread_id)}`} onClick={() => setThread(t.thread_id)}>
                          {idCurto(t.thread_id)}
                        </button>
                      </TD>
                      <TD>{fmtInt(t.turnos)}</TD><TD>{fmtUsd(t.custo_usd)}</TD><TD>{fmtUsd(t.custo_por_turno_usd, 4)}</TD><TD>{fmtMs(t.turno_ms_p95)}</TD>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        {thread && <MetricasThread agentKey={agentKey} threadId={thread} origem={origem} onFechar={() => setThread(null)} />}
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Turnos recentes</h2>
          {turnos.showSkeleton ? (
            <StudioLoading rows={3} />
          ) : turnos.isError ? (
            <StudioError error={turnos.error} onRetry={turnos.refetch} />
          ) : (turnos.data?.itens ?? []).length === 0 ? (
            <EmptyState message="Nenhum turno nesta página." />
          ) : (
            <>
              <TurnosTabela turnos={turnos.data?.itens ?? []} onAbrirThread={setThread} />
              <Paginacao pagina={turnos.data?.pagina ?? pagina} limite={turnos.data?.limite ?? LIMITE} total={turnos.data?.total ?? 0} ocupado={turnos.isRefreshing} onPagina={setPagina} />
            </>
          )}
        </section>
      </>
    );
  }

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-6" data-testid="metricas-tab">
        <p className="text-xs text-muted-foreground">Custo (USD), velocidade e tamanho de cada turno do agente. Visível apenas para administradores da plataforma.</p>
        {filtros}
        {resumo.isRefreshing && <span className="text-xs text-muted-foreground" role="status">Atualizando…</span>}
        {corpo}
      </div>
    </TooltipProvider>
  );
}

function Kpis({ r }: { r: MetricasResumo }) {
  const n = r.turnos;
  const par = (a: string, b: string) => `${a} / ${b}`;
  return (
    <StatTileRow>
      <StatTile label="Turnos" value={fmtInt(n)} hint={`${fmtInt(r.turnos_erro)} com erro · ${fmtInt(r.handoffs)} handoffs`} />
      <StatTile label="Custo total" value={fmtUsd(r.custo_usd)} hint="USD, eventos precificados" />
      <StatTile label="Custo por turno" value={fmtUsd(r.custo_por_turno_usd, 4)} hint="USD" />
      <StatTile label="Cache lido" value={fmtShare(r.cache_leitura_share)} hint="dos tokens de entrada" />
      <StatTile label="Turno p50 / p95" value={par(fmtMs(r.turno_ms_p50), fmtMs(r.turno_ms_p95))} />
      <StatTile label="LLM p50 / p95" value={par(fmtMs(r.llm_ms_p50), fmtMs(r.llm_ms_p95))} />
      <StatTile label="Tokens médios ent. / saí." value={par(fmtInt(media(r.tokens_entrada, n)), fmtInt(media(r.tokens_saida, n)))} hint="por turno" />
      <StatTile label="Bytes médios ent. / saí." value={par(fmtBytes(media(r.inbound_bytes, n)), fmtBytes(media(r.reply_bytes, n)))} hint="por turno" />
    </StatTileRow>
  );
}

function Grupo({ titulo, testId, rotulo, linhas, semRotulo }: { titulo: string; testId: string; rotulo: string; linhas: { id: string; rotulo: string | null; r: MetricasResumo }[]; semRotulo: string }) {
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold">{titulo}</h2>
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm" data-testid={testId}>
          <thead className="border-b border-border text-left text-xs text-muted-foreground">
            <tr><TH>{rotulo}</TH><TH>Turnos</TH><TH>Custo</TH><TH>Custo/turno</TH><TH>Cache</TH><TH>Turno p95</TH></tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={l.id || "sem"} className="border-b border-border last:border-0">
                <TD><span className="font-mono text-xs" title={l.id || undefined}>{l.rotulo ?? <Nulo motivo={semRotulo} />}</span></TD>
                <TD>{fmtInt(l.r.turnos)}</TD><TD>{fmtUsd(l.r.custo_usd)}</TD><TD>{fmtUsd(l.r.custo_por_turno_usd, 4)}</TD><TD>{fmtShare(l.r.cache_leitura_share)}</TD><TD>{fmtMs(l.r.turno_ms_p95)}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Paginacao({ pagina, limite, total, ocupado, onPagina }: { pagina: number; limite: number; total: number; ocupado: boolean; onPagina: (p: number) => void }) {
  const paginas = Math.max(1, Math.ceil(total / limite));
  return (
    <nav className="flex items-center gap-3 text-sm" aria-label="Paginação dos turnos">
      <Button size="sm" variant="outline" disabled={pagina <= 1 || ocupado} onClick={() => onPagina(pagina - 1)}>Anterior</Button>
      <span className="tabular-nums text-muted-foreground" data-testid="metricas-pagina">Página {pagina} de {paginas} · {fmtInt(total)} turnos</span>
      <Button size="sm" variant="outline" disabled={pagina >= paginas || ocupado} onClick={() => onPagina(pagina + 1)}>Próxima</Button>
    </nav>
  );
}
