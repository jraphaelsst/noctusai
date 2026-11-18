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
import type { ConversaEntrevista, Importacao, Onboarding, RelatorioAplicacao } from "@/api/studio/types-onboarding";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export interface AplicarVars {
  respostas: Record<number, unknown>;
  importados: number[];
  confirmados: number[];
}

const base = (key: string, product: string, orgId: string) =>
  `/api/studio/plataforma/agents/${seg(key)}/products/${seg(product)}/orgs/${seg(orgId)}/onboarding`;

/** The interviewer agent (a studio agent of the staff org); its threads list is where the interview conversation appears. */
export const ENTREVISTADOR_KEY = "onboarding-imob";
/** Live progress while an interview is open: ONE staff member, ONE company, only while the tab is visible (react-query
 * pauses a hidden tab) and only until the apply happened. A 5 s read of one small route; no stream exists for the ledger. */
export const ONBOARDING_POLL_MS = 5000;

export function useOnboarding(key: string, product: string, orgId: string) {
  const q = useQuery<Onboarding>({
    queryKey: studioKeys.onboarding(key, product, orgId),
    queryFn: () => api.get<Onboarding>(base(key, product, orgId)),
    enabled: !!key && !!product && !!orgId,
    retry: false,
    placeholderData: keepWithinAgent<Onboarding>(key),
    // poll-budget: 5s only while an interview is open and not yet applied, stops after the apply; 1 calls/tick (the progress GET, ~4 reads); worst 17280/day per open tab; hidden=paused
    refetchInterval: (query) => {
      const s = query.state.data?.sessao;
      return s && !s.aplicada ? ONBOARDING_POLL_MS : false;
    },
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
  return useCacheWriteMutation<RelatorioAplicacao, AplicarVars>({
    mutationFn: (vars) => api.post<RelatorioAplicacao>(`${base(key, product, orgId)}/aplicar`, vars),
    targets: [{ queryKey: studioKeys.onboarding(key, product, orgId) }],
    invalidate: [studioKeys.staffOrgSpecs(key, product, orgId), studioKeys.prontidao(key)],
  });
}

export function useIniciarEntrevista(key: string, product: string, orgId: string) {
  // The new conversation joins the interviewer's threads list and the progress gains its `sessao`: both re-read.
  return useCacheWriteMutation<ConversaEntrevista, void>({
    mutationFn: () => api.post<ConversaEntrevista>(`${base(key, product, orgId)}/conversa`, {}),
    targets: [{ queryKey: studioKeys.onboarding(key, product, orgId) }],
    invalidate: [["studio", ENTREVISTADOR_KEY, "conversations"]],
  });
}
