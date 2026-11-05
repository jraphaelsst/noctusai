/**
 * "Uso & Custos" (`/admin/uso`): what the platform's agents cost (real spend) and what our own Claude Code work costs
 * ("equivalente API", NOT an invoice), aggregated and discriminated, plus the dev machine and heavy-job evidence.
 * Platform admins only (`CoreLayout` gates `/admin/*`; every endpoint re-checks -> a 403 is said out loud).
 * Real data only: an empty table says so. Each section loads, fails and empties on its own.
 */
import { Fragment, useRef, useState, type ReactNode } from 'react';
import { Activity, Coins, Gauge, Wallet } from 'lucide-react';
import type { UseQueryResult } from '@tanstack/react-query';
import {
  Badge, BarChart, ChartCard, EmptyState, ErrorState, FilterBar, Input, LineChart, Select,
  Skeleton, StatTile, StatTileRow, TableSkeleton,
} from '@noctusai/lib/design-system';
import { QueryErrorState } from '@noctusai/lib';
import {
  PERIODOS, productRows, useDevUsage, useJobsUsage, useLlmUsage, useMachineUsage, useUsageFilters, useUsageFx,
  useWindow, type DevUsage, type JobsUsage, type LlmUsage, type MachineUsage, type Periodo, type UsageFilters,
} from '../../lib/usage';

// ── formatting (null = "—", never 0) ────────────────────────────────────

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const USD = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD' });
const NUM = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
type N = number | null | undefined;
export const brl = (v: N) => (v == null ? '—' : BRL.format(v));
export const usd = (v: N) => (v == null ? '—' : USD.format(v));
const num = (v: N) => (v == null ? '—' : NUM.format(v));
const pct = (v: N) => (v == null ? '—' : `${NUM.format(v * 100)}%`);
const secs = (v: N) => (v == null ? '—' : v >= 120 ? `${NUM.format(v / 60)} min` : `${NUM.format(v)} s`);
const when = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(+d) ? '—' : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
};
const short = (id: string | null | undefined) => (id ? (id.length > 12 ? `${id.slice(0, 8)}…` : id) : '—');
const SEM_AGENTE = 'sem agente';
const NO_DATA = 'Sem dados ainda: o sync começa após o deploy.';

// ── layout helpers ──────────────────────────────────────────────────────

const status = (e: unknown) => (e as { status?: number } | null)?.status;

/** One independent section: skeleton while there is no data yet, error before empty, empty says so. */
function Section<T>({ id, title, subtitle, query, isEmpty, emptyMessage, children }: {
  id: string; title: string; subtitle?: string; query: UseQueryResult<T>; isEmpty: (d: T) => boolean;
  emptyMessage: string; children: (d: T) => ReactNode;
}) {
  const data = query.data;
  const refreshing = query.isFetching && data !== undefined;
  let body: ReactNode;
  if (query.isError && data === undefined) {
    body = status(query.error) === 403
      ? <ErrorState message="Acesso restrito: apenas admin da plataforma." />
      : <QueryErrorState query={query} />;
  } else if (data === undefined) {
    body = <TableSkeleton rows={4} columns={5} />;
  } else if (isEmpty(data)) {
    body = <EmptyState message={emptyMessage} />;
  } else {
    body = children(data);
  }
  return (
    <section aria-labelledby={`uso-${id}`} data-testid={`secao-${id}`} className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id={`uso-${id}`} className="font-semibold text-card-foreground">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {refreshing && <span className="text-xs text-muted-foreground" role="status">Atualizando…</span>}
      </div>
      {body}
    </section>
  );
}

const th = 'px-2 py-1.5 text-left text-xs font-medium text-muted-foreground';
const thr = `${th} text-right`;
const td = 'px-2 py-1.5 text-sm';
const tdr = `${td} text-right tabular-nums`;

function Table({ head, children, label }: { head: Array<[string, boolean?]>; children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse" aria-label={label}>
        <thead>
          <tr className="border-b border-border">{head.map(([h, right]) => <th key={h} className={right ? thr : th}>{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-border">{children}</tbody>
      </table>
    </div>
  );
}

function Expander({ open, onToggle, children, label }: { open: boolean; onToggle: () => void; children: ReactNode; label: string }) {
  return (
    <button type="button" aria-expanded={open} aria-label={`${open ? 'Recolher' : 'Expandir'} ${label}`} onClick={onToggle}
      className="inline-flex items-center gap-1.5 text-left hover:underline">
      <span aria-hidden="true" className="w-3 text-muted-foreground">{open ? '▾' : '▸'}</span>{children}
    </button>
  );
}

function useToggleSet() {
  const [s, setS] = useState<Set<string>>(new Set());
  return [s, (k: string) => setS((p) => { const n = new Set(p); if (n.has(k)) n.delete(k); else n.add(k); return n; })] as const;
}

/** Option values seen so far: a filter's own response narrows to the selection, but the dropdown must keep the others. */
function useSeen(values: string[], selected: string): string[] {
  const seen = useRef(new Set<string>());
  values.forEach((v) => v && seen.current.add(v));
  if (selected) seen.current.add(selected);
  return [...seen.current].sort();
}

// ── filter bar ──────────────────────────────────────────────────────────

function Filters({ f, set, clear, llm, dev, machine, jobs }: {
  f: UsageFilters; set: (p: Partial<UsageFilters>) => void; clear: () => void;
  llm?: LlmUsage; dev?: DevUsage; machine?: MachineUsage; jobs?: JobsUsage;
}) {
  const rows = llm ? productRows(llm) : [];
  const products = useSeen(rows.map((r) => r.product), f.product);
  const agents = useSeen(rows.flatMap((r) => (r.per_agent ?? []).map((a) => a.agent_key ?? '')).filter(Boolean), f.agent === 'none' ? '' : f.agent);
  const hosts = useSeen([...(dev?.filters_available.hosts ?? []), ...(machine?.filters_available.hosts ?? []), ...(jobs?.filters_available.hosts ?? [])], f.host);
  const models = useSeen(dev?.filters_available.models ?? [], f.model);
  const phases = useSeen([...(machine?.filters_available.phases ?? []), ...(jobs?.filters_available.phases ?? [])], f.phase);
  const chips = ([
    ['product', 'Produto'], ['agent', 'Agente'], ['org', 'Org'], ['host', 'Host'], ['session', 'Sessão'], ['model', 'Modelo'], ['phase', 'Fase'],
  ] as const).filter(([k]) => f[k]).map(([k, label]) => ({
    key: k, label: `${label}: ${f[k] === 'none' ? SEM_AGENTE : f[k]}`, onClear: () => set({ [k]: '' }),
  }));
  const sel = (label: string, value: string, key: keyof UsageFilters, opts: string[], extra?: ReactNode) => (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <Select aria-label={label} value={value} onChange={(e) => set({ [key]: e.target.value })}>
        <option value="">Todos</option>{extra}{opts.map((o) => <option key={o} value={o}>{o}</option>)}
      </Select>
    </label>
  );
  return (
    <FilterBar chips={chips} onClearAll={chips.length || f.periodo !== '7d' ? clear : undefined}>
      <div className="flex flex-wrap items-end gap-3">
        <div role="group" aria-label="Período" className="flex gap-1">
          {PERIODOS.map((p) => (
            <button key={p.key} type="button" aria-pressed={f.periodo === p.key} onClick={() => set({ periodo: p.key as Periodo })}
              className={`rounded-md border px-2.5 py-1.5 text-sm ${f.periodo === p.key ? 'border-primary bg-primary/10 font-medium' : 'border-border'}`}>
              {p.label}
            </button>
          ))}
        </div>
        {f.periodo === 'custom' && (
          <>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">De
              <Input type="date" aria-label="De" value={f.from} onChange={(e) => set({ from: e.target.value })} /></label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">Até
              <Input type="date" aria-label="Até" value={f.to} onChange={(e) => set({ to: e.target.value })} /></label>
          </>
        )}
        {sel('Produto', f.product, 'product', products)}
        {sel('Agente', f.agent, 'agent', agents, <option value="none">{SEM_AGENTE}</option>)}
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Organização (id)
          <Input aria-label="Organização" value={f.org} placeholder="uuid" onChange={(e) => set({ org: e.target.value.trim() })} /></label>
        {sel('Host', f.host, 'host', hosts)}
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">Sessão (dev)
          <Input aria-label="Sessão" value={f.session} placeholder="session id" onChange={(e) => set({ session: e.target.value.trim() })} /></label>
        {sel('Modelo', f.model, 'model', models)}
        {sel('Fase', f.phase, 'phase', phases)}
      </div>
    </FilterBar>
  );
}

// ── A · total ───────────────────────────────────────────────────────────

function Total({ llm, dev, fx }: { llm: UseQueryResult<LlmUsage>; dev: UseQueryResult<DevUsage>; fx: UseQueryResult<{ usd_brl: number | null; date: string | null }> }) {
  const pending = (q: UseQueryResult<unknown>) => q.data === undefined && !q.isError;
  const forbidden = [llm, dev, fx].some((q) => q.isError && status(q.error) === 403);
  const agentsBrl = llm.data?.totals.cost_brl ?? null;
  const rate = fx.data?.usd_brl ?? null;
  const devUsd = dev.data?.totals.cost_usd ?? null;
  const devBrl = devUsd != null && rate != null ? devUsd * rate : null;
  const total = agentsBrl != null && devBrl != null ? agentsBrl + devBrl : null;
  const hours = llm.data?.window.hours ?? dev.data?.window.hours;
  const perHour = total != null && hours ? total / hours : null;
  const missing = (q: UseQueryResult<unknown>, label: string) => (q.isError && q.data === undefined ? `${label} indisponível` : undefined);
  const noFx = dev.data && fx.data && rate == null ? 'sem câmbio' : undefined;
  const semAgente = llm.data?.attribution?.calls_without_agent ?? 0;
  const loading = pending(llm) || pending(dev) || pending(fx);
  return (
    <section aria-label="Total" data-testid="secao-total" className="space-y-3">
      {forbidden && <ErrorState message="Acesso restrito: apenas admin da plataforma." />}
      <StatTileRow>
        <StatTile icon={Wallet} label="Total (agentes + desenvolvimento)" loading={loading} value={brl(total)}
          hint={noFx ?? missing(llm, 'agentes') ?? missing(dev, 'desenvolvimento') ?? missing(fx, 'câmbio') ?? undefined} />
        <StatTile icon={Coins} label="Agentes da plataforma" loading={pending(llm)} value={brl(agentsBrl)}
          hint={missing(llm, 'agentes') ?? (llm.data ? `${usd(llm.data.totals.cost_usd)} · gasto real` : undefined)} />
        <StatTile icon={Activity} label="Nosso desenvolvimento" loading={pending(dev) || pending(fx)} value={brl(devBrl)}
          hint={noFx ?? missing(dev, 'desenvolvimento') ?? (devUsd != null ? `${usd(devUsd)} · equivalente API` : undefined)} />
        <StatTile icon={Gauge} label="Custo por hora" loading={loading} value={brl(perHour)} hint={hours ? `média em ${num(hours)} h` : undefined} />
      </StatTileRow>
      {semAgente > 0 && llm.data?.attribution && (
        <div role="alert" className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
          {num(semAgente)} de {num(semAgente + llm.data.attribution.calls_with_agent)} chamadas de IA no período não identificam o agente
          {' '}(aparecem como “{SEM_AGENTE}”): o custo por agente está subestimado.
        </div>
      )}
      {fx.data && <p className="text-xs text-muted-foreground">Desenvolvimento = custo na tabela de preços da API (equivalente API, não é fatura) × PTAX {fx.data.usd_brl != null ? `${num(fx.data.usd_brl)} (${fx.data.date ?? 's/ data'})` : 'indisponível'}.</p>}
    </section>
  );
}

// ── B · agentes ─────────────────────────────────────────────────────────

function Agentes({ q }: { q: UseQueryResult<LlmUsage> }) {
  const [open, toggle] = useToggleSet();
  return (
    <Section id="agentes" title="Agentes da plataforma" subtitle="Produto → agente → conversas (gasto real, BRL na PTAX do dia)" query={q}
      isEmpty={(d) => d.totals.calls === 0} emptyMessage="Nenhuma chamada de agente no período.">
      {(d) => (
        <Table label="Custo por produto e agente" head={[['Produto / agente'], ['BRL', true], ['US$', true], ['Chamadas', true], ['Tokens (entrada / saída)', true], ['Conversas', true]]}>
          {productRows(d).map((p) => {
            const pk = `p:${p.product}`;
            return (
              <Fragment key={pk}>
                <tr>
                  <td className={`${td} font-medium`}><Expander open={open.has(pk)} onToggle={() => toggle(pk)} label={p.product}>{p.product}</Expander></td>
                  <td className={tdr}>{brl(p.cost_brl)}</td><td className={tdr}>{usd(p.cost_usd)}</td>
                  <td className={tdr}>{num(p.calls)}</td><td className={tdr}>{num(p.input_tokens)} / {num(p.output_tokens)}</td><td className={tdr}>—</td>
                </tr>
                {open.has(pk) && (p.per_agent ?? []).map((a) => {
                  const ak = `${pk}|a:${a.agent_key ?? ''}`;
                  const sessions = (d.per_session ?? []).filter((s) => s.product === p.product && (s.agent_key ?? null) === (a.agent_key ?? null));
                  return (
                    <Fragment key={ak}>
                      <tr className="bg-muted/30">
                        <td className={`${td} pl-8`}>
                          <Expander open={open.has(ak)} onToggle={() => toggle(ak)} label={a.agent_key ?? SEM_AGENTE}>
                            {a.agent_key ?? <span className="italic">{SEM_AGENTE}</span>}
                          </Expander>
                        </td>
                        <td className={tdr}>{brl(a.cost_brl)}</td><td className={tdr}>{usd(a.cost_usd)}</td>
                        <td className={tdr}>{num(a.calls)}</td><td className={tdr}>{num(a.input_tokens)} / {num(a.output_tokens)}</td><td className={tdr}>{num(a.conversations)}</td>
                      </tr>
                      {open.has(ak) && (sessions.length === 0
                        ? <tr><td colSpan={6} className={`${td} pl-14 text-muted-foreground`}>Sem conversas entre as 200 mais caras do período.</td></tr>
                        : sessions.map((s, i) => (
                          <tr key={`${ak}|${s.conversation_id}|${i}`} className="bg-muted/50">
                            <td className={`${td} pl-14 text-xs`} title={s.conversation_id ?? ''}>conversa {short(s.conversation_id)} <span className="text-muted-foreground">· org {short(s.org_id)} · {when(s.last)}</span></td>
                            <td className={tdr}>{brl(s.cost_brl)}</td><td className={tdr}>{usd(s.cost_usd)}</td><td className={tdr}>{num(s.calls)}</td><td className={tdr} /><td className={tdr} />
                          </tr>
                        )))}
                    </Fragment>
                  );
                })}
                {open.has(pk) && !(p.per_agent?.length) && (
                  <tr><td colSpan={6} className={`${td} pl-8 text-muted-foreground`}>Detalhe por agente indisponível para este produto.</td></tr>
                )}
                {open.has(pk) && [...(p.per_feature ?? []).map((x) => ['feature', x.feature ?? '—', x] as const), ...(p.by_model ?? []).map((x) => ['modelo', `${x.provider ?? ''}/${x.model ?? '—'}`, x] as const)].map(([kind, name, x]) => (
                  <tr key={`${pk}|${kind}|${name}`} className="bg-muted/30 text-muted-foreground">
                    <td className={`${td} pl-8`}>{kind}: {name}</td><td className={tdr}>{brl(x.cost_brl)}</td><td className={tdr}>{usd(x.cost_usd)}</td>
                    <td className={tdr}>{num(x.calls)}</td><td className={tdr}>{num(x.input_tokens)} / {num(x.output_tokens)}</td><td className={tdr} />
                  </tr>
                ))}
              </Fragment>
            );
          })}
        </Table>
      )}
    </Section>
  );
}

// ── C · desenvolvimento ─────────────────────────────────────────────────

function Dev({ q, rate }: { q: UseQueryResult<DevUsage>; rate: number | null }) {
  const [open, toggle] = useToggleSet();
  const cell = (c: number) => (
    <><td className={tdr}>{usd(c)}</td><td className={tdr}>{rate != null ? brl(c * rate) : 'sem câmbio'}</td></>
  );
  return (
    <Section id="dev" title="Nosso desenvolvimento" subtitle="Claude Code, equivalente API em US$ (não é fatura)" query={q}
      isEmpty={(d) => d.totals.requests === 0 && d.series.length === 0} emptyMessage={NO_DATA}>
      {(d) => (
        <div className="space-y-4">
          <ChartCard title="Custo por hora" subtitle="US$, equivalente API" isEmpty={d.series.length === 0} emptyMessage={NO_DATA}>
            <BarChart data={d.series} xKey="hour" series={[{ key: 'cost_usd', label: 'Custo (US$)' }]} valueFormatter={(v) => usd(v)}
              xTickFormatter={(v) => when(String(v))} height={220} />
          </ChartCard>
          <p className="text-sm text-muted-foreground" data-testid="dev-totais">
            {num(d.totals.requests)} requisições · {num(d.totals.input_tokens)} tokens de entrada · {num(d.totals.output_tokens)} de saída ·
            {' '}{num(d.totals.thinking_tokens)} de raciocínio · cache {num(d.totals.cache_read_tokens)} lido / {num(d.totals.cache_write_tokens)} escrito ·
            {' '}{num(d.totals.prompt_chars)} caracteres de prompt · {num(d.totals.output_chars)} de saída · {num(d.totals.tool_result_chars)} de resultados de ferramenta ·
            {' '}{num(d.totals.tool_calls)} chamadas de ferramenta · {usd(d.totals.cost_usd_per_hour)}/h
          </p>
          <Table label="Custo por sessão" head={[['Sessão'], ['US$', true], ['BRL', true], ['Requisições', true], ['Tokens (e / s)', true], ['Ferramentas', true], ['Subagentes', true]]}>
            {d.per_session.map((s) => {
              const agents = d.per_agent.filter((a) => a.session_id === s.session_id);
              return (
                <Fragment key={s.session_id}>
                  <tr>
                    <td className={td}><Expander open={open.has(s.session_id)} onToggle={() => toggle(s.session_id)} label={`sessão ${short(s.session_id)}`}>
                      <span title={s.session_id}>{short(s.session_id)}</span> <span className="text-xs text-muted-foreground">{s.project ?? ''} · {s.host ?? ''} · {when(s.last)}</span></Expander></td>
                    {cell(s.cost_usd)}<td className={tdr}>{num(s.requests)}</td><td className={tdr}>{num(s.input_tokens)} / {num(s.output_tokens)}</td>
                    <td className={tdr}>{num(s.tool_calls)}</td><td className={tdr}>{num(s.subagents)}</td>
                  </tr>
                  {open.has(s.session_id) && agents.map((a) => (
                    <tr key={`${s.session_id}|${a.agent_id}`} className="bg-muted/30">
                      <td className={`${td} pl-8`}>{a.agent_id === '' ? 'sessão principal' : `subagente ${short(a.agent_id)}`}</td>
                      {cell(a.cost_usd)}<td className={tdr}>{num(a.requests)}</td><td className={tdr}>{num(a.input_tokens)} / {num(a.output_tokens)}</td>
                      <td className={tdr}>{num(a.tool_calls)}</td><td className={tdr} />
                    </tr>
                  ))}
                  {open.has(s.session_id) && agents.length === 0 && <tr><td colSpan={7} className={`${td} pl-8 text-muted-foreground`}>Sem detalhe por agente.</td></tr>}
                </Fragment>
              );
            })}
          </Table>
          <Table label="Custo por modelo" head={[['Modelo'], ['US$', true], ['BRL', true], ['Requisições', true], ['Tokens (e / s)', true]]}>
            {d.per_model.map((m) => (
              <tr key={m.model}><td className={td}>{m.model}</td>{cell(m.cost_usd)}<td className={tdr}>{num(m.requests)}</td><td className={tdr}>{num(m.input_tokens)} / {num(m.output_tokens)}</td></tr>
            ))}
          </Table>
        </div>
      )}
    </Section>
  );
}

// ── D · máquina ─────────────────────────────────────────────────────────

function Maquina({ q }: { q: UseQueryResult<MachineUsage> }) {
  const chart = (title: string, subtitle: string, key: 'cpu_idle_pct' | 'reclaimable_mb' | 'swapout_per_s', fmt: (v: number) => string, d: MachineUsage) => (
    <ChartCard title={title} subtitle={subtitle} isEmpty={d.series.every((p) => p[key] == null)} emptyMessage="Sem medições neste período.">
      <LineChart data={d.series} xKey="ts" series={[{ key, label: title }]} valueFormatter={fmt} xTickFormatter={(v) => when(String(v))} height={180} />
    </ChartCard>
  );
  return (
    <Section id="maquina" title="Máquina" subtitle="Folga do Mac durante o trabalho; fases marcadas abaixo" query={q} isEmpty={(d) => d.series.length === 0} emptyMessage={NO_DATA}>
      {(d) => (
        <div className="space-y-4">
          {chart('CPU ociosa', '% (menor = mais carregada)', 'cpu_idle_pct', (v) => `${num(v)}%`, d)}
          {chart('Memória recuperável', 'MB livres ou recuperáveis', 'reclaimable_mb', (v) => `${num(v)} MB`, d)}
          {chart('Swap-out', 'páginas por segundo', 'swapout_per_s', (v) => `${num(v)}/s`, d)}
          <div>
            <h3 className="mb-1 text-sm font-medium">Fases e marcos</h3>
            {d.marks.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum marco registrado no período.</p> : (
              <ul className="space-y-0.5 text-sm">{d.marks.map((m, i) => <li key={`${m.ts}-${i}`}><span className="text-muted-foreground">{when(m.ts)}</span> · <Badge>{m.kind}</Badge> {m.label}</li>)}</ul>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

// ── E · jobs ────────────────────────────────────────────────────────────

function Jobs({ q }: { q: UseQueryResult<JobsUsage> }) {
  return (
    <Section id="jobs" title="Jobs pesados" subtitle="Por fase: lentidão contra a fase “build”, falsos vermelhos, falhas" query={q}
      isEmpty={(d) => d.jobs.length === 0 && d.per_phase.length === 0} emptyMessage={NO_DATA}>
      {(d) => (
        <div className="space-y-4">
          <Table label="Comparação por fase" head={[['Fase'], ['Execuções', true], ['Não admitidos', true], ['Duração média', true], ['Espera média', true], ['Pico RSS', true], ['Falhas', true], ['Falsos vermelhos', true], ['Jobs/h', true]]}>
            {d.per_phase.map((p) => (
              <tr key={p.phase}><td className={td}>{p.phase}</td><td className={tdr}>{num(p.runs)}</td><td className={tdr}>{num(p.not_admitted)}</td>
                <td className={tdr}>{secs(p.mean_duration_s)}</td><td className={tdr}>{secs(p.mean_waited_s)}</td><td className={tdr}>{p.max_peak_rss_mb == null ? '—' : `${num(p.max_peak_rss_mb)} MB`}</td>
                <td className={tdr}>{pct(p.fail_rate)}</td><td className={tdr}>{num(p.false_red_total)}</td><td className={tdr}>{num(p.jobs_per_hour)}</td></tr>
            ))}
          </Table>
          {d.slowdown.length > 0 && (
            <Table label="Lentidão contra a fase de referência" head={[['Job'], ['Fase'], ['Duração média', true], ['Referência', true], ['Fator', true]]}>
              {d.slowdown.map((s) => (
                <tr key={`${s.kind_target}|${s.phase}`}><td className={td}>{s.kind_target}</td><td className={td}>{s.phase}</td><td className={tdr}>{secs(s.mean_duration_s)}</td>
                  <td className={tdr}>{secs(s.baseline_mean_s)} ({s.baseline_phase})</td><td className={tdr}>{s.factor == null ? '—' : `${num(s.factor)}×`}</td></tr>
              ))}
            </Table>
          )}
          <div>
            <h3 className="mb-1 text-sm font-medium">Jobs recentes ({num(Math.min(d.jobs.length, 100))} de {num(d.jobs.length)})</h3>
            <Table label="Jobs recentes" head={[['Quando'], ['Job'], ['Evento'], ['Fase'], ['Admitido'], ['Espera', true], ['Duração', true], ['Pico RSS', true], ['Saída', true], ['Vermelhos falso / real', true]]}>
              {[...d.jobs].sort((a, b) => +new Date(b.ts) - +new Date(a.ts)).slice(0, 100).map((j, i) => (
                <tr key={`${j.ts}-${j.job}-${i}`}><td className={td}>{when(j.ts)}</td><td className={td}>{j.job}</td><td className={td}>{j.event}</td><td className={td}>{j.phase ?? '—'}</td>
                  <td className={td}>{j.admitted == null ? '—' : j.admitted ? 'sim' : 'não'}</td><td className={tdr}>{secs(j.waited_s)}</td><td className={tdr}>{secs(j.duration_s)}</td>
                  <td className={tdr}>{j.peak_rss_mb == null ? '—' : `${num(j.peak_rss_mb)} MB`}</td><td className={tdr}>{num(j.exit_code)}</td><td className={tdr}>{num(j.false_red_count)} / {num(j.real_red_count)}</td></tr>
              ))}
            </Table>
          </div>
        </div>
      )}
    </Section>
  );
}

// ── F · atualização ─────────────────────────────────────────────────────

function Atualizacao({ qs }: { qs: Array<[string, UseQueryResult<{ freshness?: Record<string, string | null> }>]> }) {
  const rows = qs.flatMap(([src, q]) => Object.entries(q.data?.freshness ?? {}).map(([table, ts]) => ({ src, table, ts })));
  const pendingAll = qs.every(([, q]) => q.data === undefined && !q.isError);
  return (
    <section aria-labelledby="uso-atualizacao" data-testid="secao-atualizacao" className="space-y-2 rounded-lg border border-border bg-card p-4">
      <h2 id="uso-atualizacao" className="font-semibold text-card-foreground">Atualização</h2>
      {pendingAll ? <Skeleton className="h-6 w-1/2" /> : rows.length === 0 ? <EmptyState message={NO_DATA} /> : (
        <ul className="text-sm">{rows.map((r) => (
          <li key={`${r.src}.${r.table}`}>{r.table}: {r.ts ? when(r.ts) : <span className="text-muted-foreground">sem dados ainda</span>}</li>
        ))}</ul>
      )}
      {qs.some(([, q]) => q.isError) && <p className="text-xs text-muted-foreground">Algumas fontes falharam; a frescura delas não aparece.</p>}
    </section>
  );
}

// ── page ────────────────────────────────────────────────────────────────

export function AdminUsoCustos() {
  const { filters, set, clear } = useUsageFilters();
  const w = useWindow(filters);
  const llm = useLlmUsage(filters, w);
  const dev = useDevUsage(filters, w);
  const machine = useMachineUsage(filters, w);
  const jobs = useJobsUsage(filters, w);
  const fx = useUsageFx();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Uso &amp; Custos</h1>
        <p className="text-sm text-muted-foreground">Agentes da plataforma e nosso desenvolvimento: total e detalhe por agente, sessão e modelo.</p>
      </div>
      <Filters f={filters} set={set} clear={clear} llm={llm.data} dev={dev.data} machine={machine.data} jobs={jobs.data} />
      {!w ? (
        <EmptyState message="Escolha as datas inicial e final do período personalizado." />
      ) : (
        <>
          <Total llm={llm} dev={dev} fx={fx} />
          <Agentes q={llm} />
          <Dev q={dev} rate={fx.data?.usd_brl ?? null} />
          <Maquina q={machine} />
          <Jobs q={jobs} />
          <Atualizacao qs={[['agentes', llm], ['dev', dev], ['máquina', machine], ['jobs', jobs]]} />
        </>
      )}
    </div>
  );
}
