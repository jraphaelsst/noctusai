/** `GET /api/metricas/atendimentos` — the "Funil de atendimento" card (CONTRACT §3.5). */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { MetricasFunil } from "@/types/cardHub";

export function useMetricasFunil(params: { de?: string; ate?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.de) qs.set("de", params.de);
  if (params.ate) qs.set("ate", params.ate);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return useQuery({
    queryKey: ["sw", "metricas", "atendimentos", params.de ?? null, params.ate ?? null],
    queryFn: () => api.get<MetricasFunil>(`/api/metricas/atendimentos${suffix}`),
  });
}
