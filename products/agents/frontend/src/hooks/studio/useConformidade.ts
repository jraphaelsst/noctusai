/**
 * Agent Studio — conformance rules and violations (CONTRACT §3.5 E3).
 *
 * NOC-REMEDIATE[julia-studio-conformidade-api]: the backend ships the stores
 * (`stores/conformidade.py`: `regras`, `definir_regra`, `listar_violacoes`) but NO HTTP route.
 * The two paths below are PROPOSED; until they exist the tab answers its honest "indisponível"
 * state (404/405 mapped by the tab, never faked data). — 2026-10-20
 *
 *   GET|PUT /api/studio/agents/{key}/conformidade/regras/{regra}   {ativo?, politica?}
 *   GET     /api/studio/agents/{key}/conformidade/violacoes?thread_id=&limite=
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { ConformidadeRegra, ConformidadeViolacao } from "@/api/studio/types-julia";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

const base = (key: string) => `/api/studio/agents/${seg(key)}/conformidade`;

export function useConformidadeRegras(key: string) {
  const q = useQuery<{ items: ConformidadeRegra[] }>({
    queryKey: [...studioKeys.conformidade(key), "regras"],
    queryFn: () => api.get<{ items: ConformidadeRegra[] }>(`${base(key)}/regras`),
    enabled: !!key,
    retry: false,
    placeholderData: keepWithinAgent<{ items: ConformidadeRegra[] }>(key),
  });
  return { ...toView(q), data: q.data?.items };
}

export function useConformidadeViolacoes(key: string) {
  const q = useQuery<{ items: ConformidadeViolacao[] }>({
    queryKey: [...studioKeys.conformidade(key), "violacoes"],
    queryFn: () => api.get<{ items: ConformidadeViolacao[] }>(`${base(key)}/violacoes`, { limite: 100 }),
    enabled: !!key,
    retry: false,
    placeholderData: keepWithinAgent<{ items: ConformidadeViolacao[] }>(key),
  });
  return { ...toView(q), data: q.data?.items };
}

export function useDefinirRegra(key: string) {
  type Vars = { regra: string; ativo?: boolean; politica?: "registrar" | "bloquear" };
  type Cached = { items: ConformidadeRegra[] };
  const swap = (old: Cached | undefined, regra: string, next: (r: ConformidadeRegra) => ConformidadeRegra) =>
    listOps.within(old, "items", (l: ConformidadeRegra[]) => l.map((r) => (r.regra === regra ? next(r) : r)));
  return useCacheWriteMutation<ConformidadeRegra, Vars>({
    mutationFn: ({ regra, ...body }) => api.put<ConformidadeRegra>(`${base(key)}/regras/${seg(regra)}`, body),
    // The toggle / policy is exactly what the server stores: draw it on the click, replace with its answer.
    targets: ({ regra }) => [
      {
        queryKey: [...studioKeys.conformidade(key), "regras"],
        optimistic: (old: Cached | undefined, { regra: _r, ...changes }: Vars) =>
          swap(old, regra, (r) => ({
            ...r,
            ...(changes.ativo !== undefined ? { ativo: changes.ativo } : {}),
            ...(changes.politica !== undefined ? { politica: changes.politica } : {}),
          })),
        commit: (old: Cached | undefined, saved: ConformidadeRegra) => swap(old, regra, () => saved),
      },
    ],
    // Violations are derived from the rules — refreshed in the background.
    invalidate: [[...studioKeys.conformidade(key), "violacoes"]],
  });
}
