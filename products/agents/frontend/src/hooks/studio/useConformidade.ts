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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  const qc = useQueryClient();
  return useMutation<ConformidadeRegra, unknown, { regra: string; ativo?: boolean; politica?: "registrar" | "bloquear" }>({
    mutationFn: ({ regra, ...body }) => api.put<ConformidadeRegra>(`${base(key)}/regras/${seg(regra)}`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: studioKeys.conformidade(key) }),
  });
}
