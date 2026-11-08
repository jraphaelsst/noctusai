/**
 * Agentes da plataforma (platform admin only, server-enforced by `require_platform_admin`): the platform's own
 * internal AI calls, each with a vendor, a model and ONE whole-prompt field.
 *
 *   GET   /api/studio/plataforma/agentes            list
 *   GET   /api/studio/plataforma/agentes/{chave}    detail = list row + `prompt` + `estatisticas`
 *   PATCH /api/studio/plataforma/agentes/{chave}    `{prompt?, modelo?, vendor?}` (vendor change => vendor+modelo together)
 *   GET   /api/studio/plataforma/modelos            `?vendor=&capacidade=` models tagged with their vendor
 *
 * `chave` is a dotted logical id (`agents.eval_improver`) — always URL-encoded in routes. A save puts the
 * server's answer in the detail AND in the list row (no invalidate-only).
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import { seg, toView } from "@/hooks/studio/keys";

export type Vendor = "anthropic" | "openai";

export const VENDORS: ReadonlyArray<{ valor: Vendor; rotulo: string }> = [
  { valor: "anthropic", rotulo: "Anthropic" },
  { valor: "openai", rotulo: "OpenAI" },
];

export interface AgentePlataforma {
  chave: string;
  nome: string;
  descricao: string | null;
  vendor: Vendor;
  modelo: string;
  capacidade: string;
  ativo: boolean;
  atualizado_em: string | null;
  atualizado_por: string | null;
}

export interface EstatisticaModelo {
  vendor: Vendor;
  modelo: string;
  n: number;
  p50_latencia_ms: number | null;
  custo_medio_usd: number | null;
  taxa_erro: number | null;
}

export interface AgentePlataformaDetalhe extends AgentePlataforma {
  prompt: string;
  estatisticas: EstatisticaModelo[];
}

export interface ModeloPlataforma {
  vendor: Vendor;
  modelo: string;
  nome?: string | null;
  capacidade?: string | null;
}

export interface AgentePlataformaPatch {
  prompt?: string;
  modelo?: string;
  vendor?: Vendor;
}

const BASE = "/api/studio/plataforma";

export const plataformaAgentesKeys = {
  all: ["agents", "plataforma", "agentes"] as const,
  list: () => ["agents", "plataforma", "agentes", "list"] as const,
  detail: (chave: string) => ["agents", "plataforma", "agentes", "detail", chave] as const,
  modelos: (vendor: string, capacidade: string) => ["agents", "plataforma", "modelos", vendor, capacidade] as const,
};

/** `toView` plus the two fields `QueryErrorState` reads to word the retry. */
function withRetryInfo<T>(q: ReturnType<typeof useQuery<T>>) {
  return { ...toView(q), isFetching: q.isFetching, failureCount: q.failureCount };
}

export function usePlataformaAgentes() {
  const q = useQuery<AgentePlataforma[]>({
    queryKey: plataformaAgentesKeys.list(),
    queryFn: () => api.get<AgentePlataforma[]>(`${BASE}/agentes`),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return withRetryInfo(q);
}

export function usePlataformaAgente(chave: string | null) {
  const q = useQuery<AgentePlataformaDetalhe>({
    queryKey: plataformaAgentesKeys.detail(chave ?? ""),
    queryFn: () => api.get<AgentePlataformaDetalhe>(`${BASE}/agentes/${seg(chave ?? "")}`),
    enabled: Boolean(chave),
    retry: false,
  });
  return withRetryInfo(q);
}

export function usePlataformaModelos(vendor: Vendor, capacidade: string | undefined) {
  const q = useQuery<ModeloPlataforma[]>({
    queryKey: plataformaAgentesKeys.modelos(vendor, capacidade ?? ""),
    queryFn: () => {
      const qs = new URLSearchParams({ vendor });
      if (capacidade) qs.set("capacidade", capacidade);
      return api.get<ModeloPlataforma[]>(`${BASE}/modelos?${qs.toString()}`);
    },
    enabled: Boolean(capacidade),
    retry: false,
  });
  return toView(q);
}

export function useSalvarPlataformaAgente() {
  return useCacheWriteMutation<AgentePlataformaDetalhe, { chave: string; patch: AgentePlataformaPatch }>({
    mutationFn: ({ chave, patch }) => api.patch<AgentePlataformaDetalhe>(`${BASE}/agentes/${seg(chave)}`, patch),
    targets: ({ chave }) => [
      {
        queryKey: plataformaAgentesKeys.detail(chave),
        commit: (old: AgentePlataformaDetalhe | undefined, saved) => ({ ...(old ?? saved), ...saved }),
      },
      {
        queryKey: plataformaAgentesKeys.list(),
        commit: (old: AgentePlataforma[] | undefined, saved) =>
          listOps.patch<AgentePlataforma>(
            old,
            saved.chave,
            {
              vendor: saved.vendor,
              modelo: saved.modelo,
              atualizado_em: saved.atualizado_em,
              atualizado_por: saved.atualizado_por,
            },
            "chave",
          ),
      },
    ],
  });
}
