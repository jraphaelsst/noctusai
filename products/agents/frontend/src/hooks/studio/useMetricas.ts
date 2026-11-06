/**
 * Agent Studio — turn metrics (cost / speed / size), PLATFORM ADMIN only, agents app only.
 * CONTRACT §14: `GET /api/studio/agents/{key}/metricas[/turnos|/threads[/{thread_id}]]`.
 *
 * Read-only: nothing here writes, so there are no cache writes. Windows move (`desde`/`ate` are part of the
 * key), so `placeholderData` keeps the previous window on screen WITHIN the same agent while the next loads
 * (`isRefreshing`, never an early return). A 403 is not retried.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  MetricasOrigem,
  MetricasResumoOut,
  MetricasThreadOut,
  MetricasThreadsOut,
  MetricasTurnosOut,
} from "@/api/studio/types-metricas";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export interface MetricasFiltro {
  /** ISO instant; omitted = the server default (7 days). */
  desde?: string;
  ate?: string;
  org_id?: string;
  origem: MetricasOrigem;
}

const base = (key: string) => `/api/studio/agents/${seg(key)}/metricas`;

function params(f: MetricasFiltro, extra: Record<string, string | number> = {}): Record<string, string | number> {
  const p: Record<string, string | number> = { origem: f.origem, ...extra };
  if (f.desde) p.desde = f.desde;
  if (f.ate) p.ate = f.ate;
  if (f.org_id) p.org_id = f.org_id;
  return p;
}

export function useMetricasResumo(key: string, filtro: MetricasFiltro) {
  const q = useQuery<MetricasResumoOut>({
    queryKey: studioKeys.metricas(key, filtro),
    queryFn: () => api.get<MetricasResumoOut>(base(key), params(filtro)),
    enabled: !!key,
    retry: false,
    placeholderData: keepWithinAgent<MetricasResumoOut>(key),
  });
  return toView(q);
}

export function useMetricasTurnos(key: string, filtro: MetricasFiltro, pagina: number, limite = 25) {
  const q = useQuery<MetricasTurnosOut>({
    queryKey: studioKeys.metricasTurnos(key, filtro, pagina, limite),
    queryFn: () => api.get<MetricasTurnosOut>(`${base(key)}/turnos`, params(filtro, { pagina, limite })),
    enabled: !!key,
    retry: false,
    placeholderData: keepWithinAgent<MetricasTurnosOut>(key),
  });
  return toView(q);
}

export function useMetricasThreads(key: string, filtro: MetricasFiltro, enabled = true) {
  const q = useQuery<MetricasThreadsOut>({
    queryKey: studioKeys.metricasThreads(key, filtro),
    queryFn: () => api.get<MetricasThreadsOut>(`${base(key)}/threads`, params(filtro)),
    enabled: !!key && enabled,
    retry: false,
    placeholderData: keepWithinAgent<MetricasThreadsOut>(key),
  });
  return toView(q);
}

export function useMetricasThread(key: string, threadId: string | null, origem: MetricasOrigem = "todos") {
  const q = useQuery<MetricasThreadOut>({
    queryKey: studioKeys.metricasThread(key, threadId ?? "", origem),
    queryFn: () => api.get<MetricasThreadOut>(`${base(key)}/threads/${seg(threadId as string)}`, { origem }),
    enabled: !!key && !!threadId,
    retry: false,
    // A different thread must never show under the previous one.
    placeholderData: undefined,
  });
  return toView(q);
}
