/**
 * Admin > Operação — the platform's routines, health, model catalog, costs and
 * the owner daily brief, in one place (platform admins only; `CoreLayout`
 * already gates `/admin/*`, the API gates every call).
 *
 * Tabs are sub-routes (`/admin/operacao/<tab>`, the seed `SectionTabsPage`):
 *   rotinas — every product's scheduled jobs with schedule, last run and the
 *             last-24h counts; failures and missing runs first; the brief
 *             dead-man banner.
 *   saude   — container health from the existing `/api/fleet`.
 *   modelos — the effective seed model catalog.
 *   custos  — LLM spend yesterday per product + cost ledger per org.
 *   brief   — latest owner brief and its history; "Gerar agora" previews one.
 *
 * Everything here is code + cron on the backend — no LLM call.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { QueryErrorState, SectionTabsPage, type SectionTab } from '@noctusai/lib/components';
import { Badge, Button, EmptyState, Skeleton } from '@noctusai/lib/design-system';
import {
  type CatalogModel,
  type CostLedgerSummary,
  type OwnerBrief,
  type RoutineJob,
  type RoutineProduct,
  useBriefs,
  useCatalogModels,
  useCosts,
  useFleetHealth,
  useGenerateBrief,
  useJobRuns,
  useRoutines,
} from '../../lib/operations';

function formatWhen(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', { timeZone, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function formatSchedule(job: RoutineJob): string {
  if (job.cron) return `cron ${job.cron}`;
  if (job.interval_seconds) {
    const s = job.interval_seconds;
    if (s % 3600 === 0) return `a cada ${s / 3600} h`;
    if (s % 60 === 0) return `a cada ${s / 60} min`;
    return `a cada ${s} s`;
  }
  return 'agenda não publicada';
}

function usd(v: number | null | undefined): string {
  return v == null ? '—' : v.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function brl(v: number): string {
  return v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function LoadingRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-16" />)}
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = { ok: 'ok', error: 'erro', skipped: 'pulada' };

function RunBadge({ status }: { status: string | undefined }) {
  if (!status) return <Badge variant="muted">nunca rodou</Badge>;
  const variant = status === 'error' ? 'destructive' : status === 'ok' ? 'default' : 'outline';
  return <Badge variant={variant}>{STATUS_LABEL[status] ?? status}</Badge>;
}

// ── Rotinas ─────────────────────────────────────────────────────────────

function JobHistory({ product, job, timeZone }: { product: string; job: string; timeZone: string }) {
  const runs = useJobRuns(product, job, true);
  if (runs.isPending && !runs.data) return <Skeleton className="h-10" />;
  if (runs.isError && !runs.data) return <QueryErrorState query={runs} variant="inline" />;
  const rows = runs.data ?? [];
  if (rows.length === 0) return <p className="text-xs text-muted-foreground">Nenhuma execução registrada.</p>;
  return (
    <ul className="space-y-1 text-xs">
      {rows.map((r) => (
        <li key={`${r.started_at}-${r.status}`} className="flex flex-wrap items-baseline gap-2">
          <span className="font-mono text-muted-foreground">{formatWhen(r.started_at, timeZone)}</span>
          <RunBadge status={r.status} />
          {r.duration_ms != null && <span className="text-muted-foreground">{r.duration_ms} ms</span>}
          {r.error && <span className="break-all text-destructive">{r.error}</span>}
        </li>
      ))}
    </ul>
  );
}

function JobRow({ product, job, timeZone }: { product: RoutineProduct; job: RoutineJob; timeZone: string }) {
  const [open, setOpen] = useState(false);
  const failing = job.overdue || job.last_run?.status === 'error';
  return (
    <>
      <tr className={failing ? 'bg-destructive/5' : 'hover:bg-muted/40'}>
        <td className="px-4 py-3 font-mono text-xs text-foreground">{job.job}</td>
        <td className="px-4 py-3 text-xs text-muted-foreground">{formatSchedule(job)}</td>
        <td className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <RunBadge status={job.last_run?.status} />
            <span className="text-xs text-muted-foreground">{formatWhen(job.last_run?.started_at, timeZone)}</span>
          </div>
          {job.last_run?.error && <p className="mt-1 line-clamp-2 break-all text-xs text-destructive">{job.last_run.error}</p>}
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground">
          {job.runs_24h} execuções{job.errors_24h > 0 && <span className="text-destructive"> · {job.errors_24h} erro(s)</span>}
        </td>
        <td className="px-4 py-3 text-xs">
          {job.overdue ? (
            <span className="text-destructive">Faltando (esperada {formatWhen(job.expected_at, timeZone)})</span>
          ) : product.active ? (
            <span className="text-muted-foreground">em dia</span>
          ) : (
            <span className="text-muted-foreground">produto inativo</span>
          )}
        </td>
        <td className="px-4 py-3 text-right">
          <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? 'Ocultar' : 'Histórico'}
          </Button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} className="bg-muted/30 px-4 py-3">
            <JobHistory product={product.product} job={job.job} timeZone={timeZone} />
          </td>
        </tr>
      )}
    </>
  );
}

function RoutinesSection() {
  const query = useRoutines();
  const { data, isPending, isFetching } = query;
  if (isPending && !data) return <LoadingRows />;
  if (query.isError && !data) return <QueryErrorState query={query} />;
  if (!data) return null;
  const tz = data.timezone;

  return (
    <div className="space-y-4" aria-busy={isFetching && !!data}>
      {data.brief.missing ? (
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          Brief diário ausente: nenhuma execução ok nas últimas {data.brief.deadman_hours} h
          {data.brief.last_ok_at ? ` (última em ${formatWhen(data.brief.last_ok_at, tz)})` : ' (nunca rodou)'}.
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Brief diário ok — última execução em {formatWhen(data.brief.last_ok_at, tz)}.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: 'Rotinas', value: data.totals.jobs },
          { label: `Execuções (${data.window_hours} h)`, value: data.totals.runs_24h },
          { label: 'Erros', value: data.totals.errors_24h },
          { label: 'Faltando', value: data.totals.overdue },
        ].map((c) => (
          <div key={c.label} className="rounded-lg border border-border bg-card p-4">
            <div className="text-2xl font-bold text-foreground">{c.value}</div>
            <div className="mt-1 text-sm text-muted-foreground">{c.label}</div>
          </div>
        ))}
      </div>

      {data.products.length === 0 ? (
        <EmptyState message="Nenhuma rotina registrada ainda. Cada produto publica suas rotinas quando o agendador inicia." />
      ) : (
        data.products.map((product) => (
          <section key={product.product} className="overflow-hidden rounded-lg border border-border bg-card">
            <header className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/50 px-4 py-3">
              <h3 className="font-medium text-foreground">{product.product}</h3>
              {!product.active && <Badge variant="muted">inativo</Badge>}
              {product.failing > 0 && <Badge variant="destructive">{product.failing} com problema</Badge>}
            </header>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Rotina</th>
                    <th className="px-4 py-2 font-medium">Agenda</th>
                    <th className="px-4 py-2 font-medium">Última execução</th>
                    <th className="px-4 py-2 font-medium">{data.window_hours} h</th>
                    <th className="px-4 py-2 font-medium">Situação</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {product.jobs.map((job) => <JobRow key={job.job} product={product} job={job} timeZone={tz} />)}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
      <p className="text-xs text-muted-foreground">Horários no fuso da plataforma ({tz}).</p>
    </div>
  );
}

// ── Saúde ───────────────────────────────────────────────────────────────

function HealthSection() {
  const query = useFleetHealth();
  const { data, isPending } = query;
  if (isPending && !data) return <LoadingRows />;
  if (query.isError && !data) return <QueryErrorState query={query} />;
  const rows = data ?? [];
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Estado dos contêineres. Para ligar, desligar ou reiniciar use o <Link to="/admin/fleet" className="text-primary underline">Fleet Control</Link>.
      </p>
      {rows.length === 0 ? (
        <EmptyState message="Nenhum contêiner registrado." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium">Produto</th>
                <th className="px-4 py-2 font-medium">Contêiner</th>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 font-medium">Saúde</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((p) => {
                const bad = p.state !== 'absent' && (!p.running || p.health === 'unhealthy');
                return (
                  <tr key={p.slug} className={bad ? 'bg-destructive/5' : undefined}>
                    <td className="px-4 py-2 text-foreground">{p.display || p.slug}</td>
                    <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{p.container}</td>
                    <td className="px-4 py-2">{p.running ? <Badge>rodando</Badge> : <Badge variant={p.state === 'absent' ? 'muted' : 'destructive'}>{p.state}</Badge>}</td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">{p.health}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Modelos de IA ───────────────────────────────────────────────────────

function ModelsSection() {
  const query = useCatalogModels();
  const { data, isPending } = query;
  if (isPending && !data) return <LoadingRows />;
  if (query.isError && !data) return <QueryErrorState query={query} />;
  const rows = data ?? [];
  if (rows.length === 0) return <EmptyState message="Catálogo de modelos vazio." />;
  const byProvider = rows.reduce<Record<string, CatalogModel[]>>((acc, m) => {
    (acc[m.provider] ??= []).push(m);
    return acc;
  }, {});
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Catálogo efetivo do seed (preços por 1M tokens, US$). Gasto por produto em <Link to="/admin/operacao/custos" className="text-primary underline">Custos</Link>.
      </p>
      {Object.entries(byProvider).map(([provider, models]) => (
        <section key={provider} className="overflow-hidden rounded-lg border border-border bg-card">
          <h3 className="border-b border-border bg-muted/50 px-4 py-2 text-sm font-medium text-foreground">{provider}</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium">Modelo</th>
                <th className="px-4 py-2 font-medium">Tipo</th>
                <th className="px-4 py-2 font-medium">Entrada</th>
                <th className="px-4 py-2 font-medium">Saída</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {models.map((m) => (
                <tr key={`${m.provider}:${m.id}`}>
                  <td className="px-4 py-2"><span className="text-foreground">{m.label}</span> <span className="font-mono text-xs text-muted-foreground">{m.id}</span></td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{m.kind}</td>
                  <td className="px-4 py-2 text-xs">{usd(m.cost_per_1m_input_tokens)}</td>
                  <td className="px-4 py-2 text-xs">{usd(m.cost_per_1m_output_tokens)}</td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex justify-end gap-1">
                      {m.stub && <Badge variant="outline">stub</Badge>}
                      {!m.priced && !m.stub && <Badge variant="muted">sem preço</Badge>}
                      {m.supports_batch && <Badge variant="outline">batch</Badge>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

// ── Custos ──────────────────────────────────────────────────────────────

function LedgerTable({ title, summary }: { title: string; summary: CostLedgerSummary }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-medium text-foreground">{title}: {brl(summary.total_brl)}</h3>
      {summary.pending_fx > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">{summary.pending_fx} lançamento(s) aguardando câmbio (fora do total).</p>
      )}
      {summary.per_org.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">Nenhum custo registrado.</p>
      ) : (
        <ul className="mt-2 divide-y divide-border text-sm">
          {summary.per_org.map((o) => (
            <li key={o.org_id || o.org_name} className="flex justify-between py-1.5">
              <span className="text-foreground">{o.org_name}</span>
              <span className="text-muted-foreground">{brl(o.amount_brl)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CostsSection() {
  const query = useCosts();
  const { data, isPending } = query;
  if (isPending && !data) return <LoadingRows />;
  if (query.isError && !data) return <QueryErrorState query={query} />;
  if (!data) return null;
  const llm = data.llm_yesterday;
  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-border bg-card p-4">
        <h3 className="text-sm font-medium text-foreground">IA ontem: {usd(llm.total_usd)}</h3>
        {!llm.available ? (
          <p role="alert" className="mt-2 text-sm text-destructive">Fonte de uso de IA indisponível: {llm.error}</p>
        ) : llm.per_product.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">Nenhuma chamada de IA registrada ontem.</p>
        ) : (
          <ul className="mt-2 divide-y divide-border text-sm">
            {llm.per_product.map((p) => (
              <li key={p.product} className="flex justify-between py-1.5">
                <span className="text-foreground">{p.product}</span>
                <span className="text-muted-foreground">{usd(p.cost_usd)} · {p.calls} chamadas</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <LedgerTable title="Custos ontem" summary={data.cost_ledger_yesterday} />
        <LedgerTable title="Custos no mês" summary={data.cost_ledger_month} />
      </div>
      <p className="text-xs text-muted-foreground">
        Receita e pagamentos em <Link to="/admin/billing" className="text-primary underline">Faturamento</Link>; livros da plataforma em{' '}
        <Link to="/admin/financeiro" className="text-primary underline">Financeiro</Link>.
      </p>
    </div>
  );
}

// ── Brief ───────────────────────────────────────────────────────────────

const EMAIL_LABEL: Record<OwnerBrief['email_status'], string> = {
  sent: 'e-mail enviado',
  failed: 'e-mail falhou',
  not_configured: 'e-mail não configurado',
  not_sent: 'não entregue (prévia)',
};

function BriefSection() {
  const query = useBriefs();
  const generate = useGenerateBrief();
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isPending } = query;
  if (isPending && !data) return <LoadingRows />;
  if (query.isError && !data) return <QueryErrorState query={query} />;
  const briefs = data ?? [];
  const current = briefs.find((b) => b.id === selected) ?? briefs[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Gerado todo dia às 07:00, entregue no sino dos administradores e por e-mail. Só código — sem IA.
        </p>
        <Button size="sm" onClick={() => generate.mutate(undefined, { onSuccess: (b) => setSelected(b.id) })} disabled={generate.isPending}>
          {generate.isPending ? 'Gerando…' : 'Gerar agora (prévia)'}
        </Button>
      </div>
      {generate.isError && (
        <p role="alert" className="text-sm text-destructive">Não foi possível gerar o brief: {generate.error.message}</p>
      )}
      {briefs.length === 0 || !current ? (
        <EmptyState message="Nenhum brief gerado ainda." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <ul className="space-y-1" aria-label="Histórico de briefs">
            {briefs.map((b) => (
              <li key={b.id}>
                <button
                  type="button"
                  onClick={() => setSelected(b.id)}
                  aria-current={b.id === current.id}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${b.id === current.id ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50'}`}
                >
                  {formatWhen(b.generated_at)} {b.exceptions_count > 0 ? `· ${b.exceptions_count} exceção(ões)` : '· ok'}
                </button>
              </li>
            ))}
          </ul>
          <article className="rounded-lg border border-border bg-card p-4">
            <div className="mb-3 flex flex-wrap gap-2">
              <Badge variant={current.exceptions_count > 0 ? 'destructive' : 'default'}>
                {current.exceptions_count > 0 ? `${current.exceptions_count} exceção(ões)` : 'tudo em ordem'}
              </Badge>
              <Badge variant="outline">{current.trigger === 'manual' ? 'manual' : 'agendado'}</Badge>
              <Badge variant={current.email_status === 'failed' ? 'destructive' : 'muted'}>{EMAIL_LABEL[current.email_status]}</Badge>
            </div>
            <pre className="whitespace-pre-wrap break-words font-sans text-sm text-foreground">{current.text_body}</pre>
          </article>
        </div>
      )}
    </div>
  );
}

export function AdminOperacao() {
  const sections: SectionTab[] = [
    { key: 'rotinas', label: 'Rotinas', render: () => <RoutinesSection /> },
    { key: 'saude', label: 'Saúde', render: () => <HealthSection /> },
    { key: 'modelos', label: 'Modelos de IA', render: () => <ModelsSection /> },
    { key: 'custos', label: 'Custos', render: () => <CostsSection /> },
    { key: 'brief', label: 'Brief', render: () => <BriefSection /> },
  ];
  return (
    <SectionTabsPage
      basePath="/admin/operacao"
      title="Operação"
      description="Rotinas, saúde, modelos de IA, custos e o brief diário da plataforma"
      sections={sections}
    />
  );
}
