/**
 * "Uso & Custos" (`/admin/uso`): typed hooks over the platform-admin usage endpoints.
 *
 * Two cost sources, never mixed in the backend: platform agents (`public.ai_usage`, real spend, BRL priced at write time)
 * and our own Claude Code work (`dev_telemetry_claude`, API list price = "equivalente API", NOT an invoice).
 * Unmeasured = `null` (never 0). Filters live in the URL query string (shareable, survives reload).
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api } from './api';

// ── filters (URL-synced) ────────────────────────────────────────────────

export type Periodo = '24h' | '7d' | '30d' | 'custom';
export const PERIODOS: Array<{ key: Periodo; label: string }> = [
  { key: '24h', label: '24 horas' },
  { key: '7d', label: '7 dias' },
  { key: '30d', label: '30 dias' },
  { key: 'custom', label: 'Personalizado' },
];
const HOURS: Record<Exclude<Periodo, 'custom'>, number> = { '24h': 24, '7d': 168, '30d': 720 };

export interface UsageFilters {
  periodo: Periodo;
  from: string; // custom only, yyyy-mm-dd
  to: string;
  product: string;
  agent: string; // agent_key, or 'none'
  org: string;
  host: string;
  session: string;
  model: string;
  phase: string;
}
const KEYS = ['from', 'to', 'product', 'agent', 'org', 'host', 'session', 'model', 'phase'] as const;

export function useUsageFilters() {
  const [params, setParams] = useSearchParams();
  const raw = params.get('periodo');
  const periodo: Periodo = raw === '24h' || raw === '30d' || raw === 'custom' ? raw : '7d';
  const filters: UsageFilters = {
    periodo,
    ...(Object.fromEntries(KEYS.map((k) => [k, params.get(k) ?? ''])) as Omit<UsageFilters, 'periodo'>),
  };
  const set = (patch: Partial<UsageFilters>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(patch)) {
          if (v === '' || v === undefined || (k === 'periodo' && v === '7d')) next.delete(k);
          else next.set(k, String(v));
        }
        return next;
      },
      { replace: true },
    );
  const clear = () => setParams({}, { replace: true });
  const active = KEYS.filter((k) => filters[k] !== '' && !(periodo !== 'custom' && (k === 'from' || k === 'to')));
  return { filters, set, clear, activeCount: active.length + (periodo !== '7d' ? 1 : 0) };
}

/** The ISO window. Presets are anchored at the minute the preset was chosen (stable query keys, no refetch storm). */
export function useWindow(f: Pick<UsageFilters, 'periodo' | 'from' | 'to'>): { from: string; to: string } | null {
  return useMemo(() => {
    if (f.periodo === 'custom') {
      if (!f.from || !f.to) return null;
      const from = new Date(`${f.from}T00:00:00`);
      const to = new Date(`${f.to}T23:59:59`);
      if (Number.isNaN(+from) || Number.isNaN(+to) || to < from) return null;
      return { from: from.toISOString(), to: to.toISOString() };
    }
    const now = new Date();
    now.setSeconds(0, 0);
    return { from: new Date(+now - HOURS[f.periodo] * 3_600_000).toISOString(), to: now.toISOString() };
  }, [f.periodo, f.from, f.to]);
}

function qs(params: Record<string, string | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) u.set(k, v);
  const s = u.toString();
  return s ? `?${s}` : '';
}

// ── response types (contract: usage-dash-contract.md) ───────────────────

export interface UsageWindow { from: string; to: string; hours: number }
type Freshness = Record<string, string | null>;

export interface AgentTotals {
  calls: number; errors?: number; input_tokens: number; output_tokens: number;
  cost_usd: number; cost_brl: number | null;
}
export interface PerAgent {
  agent_key: string | null; calls: number; cost_usd: number; cost_brl: number | null;
  input_tokens: number; output_tokens: number; conversations: number;
}
export interface PerFeature extends AgentTotals { feature: string | null }
export interface ByModel extends AgentTotals { provider: string | null; model: string | null }
export interface PerProductRow extends AgentTotals {
  product: string;
  per_agent?: PerAgent[];
  per_feature?: PerFeature[];
  by_model?: ByModel[];
}
export interface PerSession {
  conversation_id: string | null; product: string; agent_key: string | null; org_id: string | null;
  calls: number; cost_usd: number; cost_brl: number | null; first: string; last: string;
}
export interface LlmUsage {
  window: UsageWindow;
  freshness?: Freshness;
  totals: AgentTotals;
  attribution?: { calls_with_agent: number; calls_without_agent: number };
  per_org: Array<{ org_id: string; per_product: PerProductRow[] } & AgentTotals>;
  per_product: Record<string, AgentTotals> | PerProductRow[];
  per_session?: PerSession[];
}

export interface DevTotals {
  requests: number; input_tokens: number; output_tokens: number; thinking_tokens: number;
  cache_read_tokens: number; cache_write_tokens: number; cost_usd: number; prompt_chars: number;
  output_chars: number; tool_result_chars: number; tool_calls: number; cost_usd_per_hour: number | null;
}
export interface DevUsage {
  window: UsageWindow;
  freshness?: Freshness;
  totals: DevTotals;
  per_session: Array<DevTotals & { session_id: string; project: string | null; host: string | null; subagents: number; first: string; last: string }>;
  per_agent: Array<DevTotals & { session_id: string; agent_id: string }>;
  per_model: Array<DevTotals & { model: string }>;
  series: Array<{ hour: string; cost_usd: number; input_tokens: number; output_tokens: number; requests: number }>;
  filters_available: { hosts: string[]; projects: string[]; models: string[] };
}

export interface MachinePoint {
  ts: string; phase: string | null; cpu_idle_pct: number | null; reclaimable_mb: number | null;
  swapout_per_s: number | null; load_1m: number | null; claude_sessions: number | null;
  busy_slots: number | null; overloaded: boolean | null;
}
export interface MachineUsage {
  window: UsageWindow;
  freshness?: Freshness;
  series: MachinePoint[];
  marks: Array<{ ts: string; kind: string; label: string; payload?: unknown }>;
  filters_available: { hosts: string[]; phases: string[] };
}

export interface JobRow {
  ts: string; job: string; kind: string | null; target: string | null; event: string; phase: string | null;
  admitted: boolean | null; waited_s: number | null; duration_s: number | null; peak_rss_mb: number | null;
  exit_code: number | null; false_red_count: number | null; real_red_count: number | null;
}
export interface JobsUsage {
  window: UsageWindow;
  freshness?: Freshness;
  jobs: JobRow[];
  per_phase: Array<{
    phase: string; runs: number; not_admitted: number; mean_duration_s: number | null; mean_waited_s: number | null;
    max_peak_rss_mb: number | null; fail_rate: number | null; false_red_total: number | null; jobs_per_hour: number | null;
  }>;
  slowdown: Array<{ kind_target: string; phase: string; mean_duration_s: number; baseline_phase: string; baseline_mean_s: number; factor: number | null }>;
  filters_available: { hosts: string[]; phases: string[]; kinds: string[] };
}

export interface FxRate { usd_brl: number | null; date: string | null }

// ── hooks ───────────────────────────────────────────────────────────────

const STALE = 60_000;
const get = async <T,>(path: string): Promise<T> => (await api.get(path)).data as T;

export function useLlmUsage(f: UsageFilters, w: { from: string; to: string } | null) {
  const path = `/api/admin/llm-usage${qs({ from: w?.from, to: w?.to, product: f.product, agent_key: f.agent, org_id: f.org })}`;
  return useQuery({ queryKey: ['core-usage', 'llm', path], queryFn: () => get<LlmUsage>(path), enabled: !!w, retry: false, staleTime: STALE, placeholderData: (p) => p });
}

export function useDevUsage(f: UsageFilters, w: { from: string; to: string } | null) {
  const path = `/api/admin/usage/dev${qs({ from: w?.from, to: w?.to, host: f.host, session_id: f.session, model: f.model })}`;
  return useQuery({ queryKey: ['core-usage', 'dev', path], queryFn: () => get<DevUsage>(path), enabled: !!w, retry: false, staleTime: STALE, placeholderData: (p) => p });
}

export function useMachineUsage(f: UsageFilters, w: { from: string; to: string } | null) {
  const path = `/api/admin/usage/machine${qs({ from: w?.from, to: w?.to, host: f.host, phase: f.phase })}`;
  return useQuery({ queryKey: ['core-usage', 'machine', path], queryFn: () => get<MachineUsage>(path), enabled: !!w, retry: false, staleTime: STALE, placeholderData: (p) => p });
}

export function useJobsUsage(f: UsageFilters, w: { from: string; to: string } | null) {
  const path = `/api/admin/usage/jobs${qs({ from: w?.from, to: w?.to, host: f.host, phase: f.phase })}`;
  return useQuery({ queryKey: ['core-usage', 'jobs', path], queryFn: () => get<JobsUsage>(path), enabled: !!w, retry: false, staleTime: STALE, placeholderData: (p) => p });
}

export function useUsageFx() {
  return useQuery({ queryKey: ['core-usage', 'fx'], queryFn: () => get<FxRate>('/api/admin/usage/fx'), retry: false, staleTime: 10 * 60_000 });
}

/** Normalise `per_product` (slug-keyed dict today, list per the contract) into rows enriched from `per_org[].per_product`. */
export function productRows(d: LlmUsage): PerProductRow[] {
  const merged = new Map<string, PerProductRow>();
  const base: PerProductRow[] = Array.isArray(d.per_product)
    ? d.per_product
    : Object.entries(d.per_product ?? {}).map(([product, t]) => ({ product, ...t }));
  for (const r of base) merged.set(r.product, { ...r });
  const hadAgents = new Set(base.filter((r) => r.per_agent).map((r) => r.product));
  for (const org of d.per_org ?? []) {
    for (const p of org.per_product ?? []) {
      const cur = merged.get(p.product) ?? ({ product: p.product, calls: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0, cost_brl: 0 } as PerProductRow);
      if (!merged.has(p.product)) merged.set(p.product, cur);
      if (!hadAgents.has(p.product) && p.per_agent) {
        const acc = new Map((cur.per_agent ?? []).map((a) => [String(a.agent_key), { ...a }]));
        for (const a of p.per_agent) {
          const c = acc.get(String(a.agent_key));
          if (!c) { acc.set(String(a.agent_key), { ...a }); continue; }
          c.calls += a.calls; c.input_tokens += a.input_tokens; c.output_tokens += a.output_tokens;
          c.cost_usd += a.cost_usd; c.conversations += a.conversations;
          c.cost_brl = c.cost_brl == null || a.cost_brl == null ? null : c.cost_brl + a.cost_brl;
        }
        cur.per_agent = [...acc.values()].sort((x, y) => (y.cost_brl ?? 0) - (x.cost_brl ?? 0));
      }
      cur.per_feature = sumBy([...(cur.per_feature ?? []), ...(p.per_feature ?? [])], (x) => x.feature ?? '');
      cur.by_model = sumBy([...(cur.by_model ?? []), ...(p.by_model ?? [])], (x) => `${x.provider}/${x.model}`);
    }
  }
  return [...merged.values()].sort((a, b) => (b.cost_brl ?? 0) - (a.cost_brl ?? 0));
}

function sumBy<T extends AgentTotals>(rows: T[], key: (r: T) => string): T[] {
  const m = new Map<string, T>();
  for (const r of rows) {
    const k = key(r);
    const c = m.get(k);
    if (!c) { m.set(k, { ...r }); continue; }
    c.calls += r.calls; c.input_tokens += r.input_tokens; c.output_tokens += r.output_tokens; c.cost_usd += r.cost_usd;
    c.cost_brl = c.cost_brl == null || r.cost_brl == null ? null : c.cost_brl + r.cost_brl;
  }
  return [...m.values()].sort((a, b) => (b.cost_brl ?? 0) - (a.cost_brl ?? 0));
}
