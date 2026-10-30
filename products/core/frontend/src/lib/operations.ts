/**
 * Core Operação — typed client + react-query hooks for `/api/admin/operations`
 * (routines, run history, model catalog, costs, owner brief) and the existing
 * `/api/fleet` health read.
 *
 * The HTTP client arrives through `OperationsApiContext` (default: the app's
 * `api`), so tests render the page with a fake client instead of mocking
 * modules. Loading flags follow the two-signal rule:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '@noctusai/lib/cache-writes';
import { api } from './api';
import type { HttpClient } from './billing';

export type RunStatus = 'ok' | 'error' | 'skipped';

export interface RunSummary {
  started_at: string;
  finished_at?: string | null;
  status: RunStatus;
  error?: string | null;
  duration_ms?: number | null;
}

export interface RoutineJob {
  job: string;
  cron: string | null;
  interval_seconds: number | null;
  timezone: string | null;
  last_seen_at: string | null;
  registered: boolean;
  last_run: RunSummary | null;
  runs_24h: number;
  errors_24h: number;
  overdue: boolean;
  expected_at: string | null;
}

export interface RoutineProduct {
  product: string;
  active: boolean;
  failing: number;
  jobs: RoutineJob[];
}

export interface BriefStatus {
  job: string;
  last_ok_at: string | null;
  last_generated_at: string | null;
  missing: boolean;
  deadman_hours: number;
}

export interface Routines {
  generated_at: string;
  timezone: string;
  window_hours: number;
  brief: BriefStatus;
  products: RoutineProduct[];
  totals: { jobs: number; runs_24h: number; errors_24h: number; overdue: number };
}

export interface CatalogModel {
  id: string;
  label: string;
  provider: string;
  kind: string;
  stub: boolean;
  description: string;
  cost_per_1m_input_tokens: number | null;
  cost_per_1m_output_tokens: number | null;
  supports_batch: boolean;
  tag_performance: string | null;
  priced: boolean;
}

export interface CostLedgerOrg {
  org_id: string;
  org_name: string;
  amount_brl: number;
  pending_fx: number;
  by_category: Record<string, number>;
}

export interface CostLedgerSummary {
  per_org: CostLedgerOrg[];
  total_brl: number;
  pending_fx: number;
}

export interface LlmSpend {
  available: boolean;
  error: string | null;
  source?: string;
  per_product: Array<{ product: string; calls: number; cost_usd: number }>;
  total_usd: number | null;
  calls: number | null;
}

export interface Costs {
  timezone: string;
  yesterday: { from: string; to: string };
  llm_yesterday: LlmSpend;
  cost_ledger_yesterday: CostLedgerSummary;
  cost_ledger_month: CostLedgerSummary;
}

export interface OwnerBrief {
  id: string;
  generated_at: string;
  trigger: 'schedule' | 'manual';
  text_body: string;
  exceptions_count: number;
  in_app_sent: number;
  email_status: 'sent' | 'failed' | 'not_configured' | 'not_sent';
}

export interface FleetProduct {
  slug: string;
  container: string;
  display: string;
  state: string;
  health: string;
  running: boolean;
}

export function createOperationsApi(http: HttpClient) {
  const unwrap = async <T,>(p: Promise<{ data: T }>) => (await p).data;
  return {
    routines: () => unwrap<Routines>(http.get('/api/admin/operations/routines')),
    runs: (product: string, job: string) =>
      unwrap<Array<RunSummary & { job: string; product: string }>>(
        http.get(
          `/api/admin/operations/runs?product=${encodeURIComponent(product)}&job=${encodeURIComponent(job)}&limit=20`,
        ),
      ),
    models: () => unwrap<CatalogModel[]>(http.get('/api/admin/operations/models')),
    costs: () => unwrap<Costs>(http.get('/api/admin/operations/costs')),
    briefs: () => unwrap<OwnerBrief[]>(http.get('/api/admin/operations/briefs?limit=30')),
    generateBrief: () => unwrap<OwnerBrief>(http.post('/api/admin/operations/briefs')),
    fleet: async () => {
      const res = (await http.get('/api/fleet')) as { products?: FleetProduct[] } | null;
      return res?.products ?? [];
    },
  };
}

export type OperationsApi = ReturnType<typeof createOperationsApi>;

const OperationsApiContext = createContext<OperationsApi>(createOperationsApi(api));

export function OperationsApiProvider({ value, children }: { value: OperationsApi; children: ReactNode }) {
  return createElement(OperationsApiContext.Provider, { value }, children);
}

export function useOperationsApi(): OperationsApi {
  return useContext(OperationsApiContext);
}

const KEY = ['core-operations'] as const;

export function useRoutines() {
  const o = useOperationsApi();
  return useQuery({ queryKey: [...KEY, 'routines'], queryFn: o.routines, refetchInterval: 60_000 });
}

export function useJobRuns(product: string, job: string, enabled: boolean) {
  const o = useOperationsApi();
  return useQuery({ queryKey: [...KEY, 'runs', product, job], queryFn: () => o.runs(product, job), enabled });
}

export function useCatalogModels() {
  const o = useOperationsApi();
  return useQuery({ queryKey: [...KEY, 'models'], queryFn: o.models, staleTime: 5 * 60_000 });
}

export function useCosts() {
  const o = useOperationsApi();
  return useQuery({ queryKey: [...KEY, 'costs'], queryFn: o.costs });
}

export function useBriefs() {
  const o = useOperationsApi();
  return useQuery({ queryKey: [...KEY, 'briefs'], queryFn: o.briefs });
}

export function useFleetHealth() {
  const o = useOperationsApi();
  return useQuery({ queryKey: ['fleet', 'operations'], queryFn: o.fleet, staleTime: 10_000 });
}

/** Generate a brief now (stored, not delivered). The server answers with the
 *  stored row, which is committed to the top of the history at once. */
export function useGenerateBrief() {
  const o = useOperationsApi();
  return useCacheWriteMutation<OwnerBrief, void>({
    mutationFn: () => o.generateBrief(),
    targets: () => [
      {
        queryKey: [...KEY, 'briefs'],
        commit: (old: OwnerBrief[] | undefined, brief) => listOps.replace(old, brief.id, brief, 'prepend'),
      },
    ],
  });
}
