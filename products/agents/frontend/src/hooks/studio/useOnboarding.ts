/**
 * Agent Studio — onboarding by interview, STAFF-only, one (agent, product, company) at a time.
 *
 *   GET  .../orgs/{org_id}/onboarding            checklist + progress
 *   POST .../orgs/{org_id}/onboarding/importar   proposals to confirm (writes nothing)
 *   POST .../orgs/{org_id}/onboarding/aplicar    ONE apply step -> per-item report
 *
 * The progress shown is always the server's answer. An apply changes the company's specs, so it refreshes the progress
 * AND the specs form entry it touches; a refused item is returned in the report, never swallowed.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { Importacao, Onboarding, RelatorioAplicacao } from "@/api/studio/types-onboarding";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

const base = (key: string, product: string, orgId: string) =>
  `/api/studio/plataforma/agents/${seg(key)}/products/${seg(product)}/orgs/${seg(orgId)}/onboarding`;

export function useOnboarding(key: string, product: string, orgId: string) {
  const q = useQuery<Onboarding>({
    queryKey: studioKeys.onboarding(key, product, orgId),
    queryFn: () => api.get<Onboarding>(base(key, product, orgId)),
    enabled: !!key && !!product && !!orgId,
    retry: false,
    placeholderData: keepWithinAgent<Onboarding>(key),
  });
  return toView(q);
}

export function useImportarOnboarding(key: string, product: string, orgId: string) {
  // A proposal, not a write: nothing cached changes.
  return useMutation<Importacao, unknown, string>({ // noc-allow: invalidate-only — a proposal to confirm, not a write: nothing cached changes
    mutationFn: (texto) => api.post<Importacao>(`${base(key, product, orgId)}/importar`, { texto }),
  });
}

export function useAplicarOnboarding(key: string, product: string, orgId: string) {
  // The answer is a per-item report (not a cached read): the progress and the specs form it changes are re-read from the
  // server (settled right after the write), never edited here.
  return useCacheWriteMutation<RelatorioAplicacao, Record<number, unknown>>({
    mutationFn: (respostas) => api.post<RelatorioAplicacao>(`${base(key, product, orgId)}/aplicar`, { respostas }),
    targets: [{ queryKey: studioKeys.onboarding(key, product, orgId) }],
    invalidate: [studioKeys.staffOrgSpecs(key, product, orgId), studioKeys.prontidao(key)],
  });
}
