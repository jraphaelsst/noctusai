/**
 * Julia › Envio (julia-v2 Q6: ONE rubric, the send fires from the COMPUTED stage).
 *
 *   GET/PUT /api/julia/envio/regras      → {data:{diferenciar, regras:[{operacao, estagio_minimo, versao}]}}
 *                                           PUT body {diferenciar, regras:[{operacao, estagio_minimo}]}; the server
 *                                           refuses the retired `grupos` with 422 — this client never sends it
 *   GET/PUT /api/julia/envio/politicas   → {data: Politicas}
 *   GET /api/julia/qualificacao/estagios → the ordered stages of the standard agents runs for this org
 *        (SW proxy of agents' `GET /api/channels/agents/{key}/qualificacao/estagios`): label + order only.
 *        NOC-REMEDIATE[sw-estagios-proxy]: planned path, the backend slice julia-v2-sw-ferramentas adds it — 2026-10-20
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export type OperacaoRegra = "compra" | "aluguel" | "ambas";
export interface RegraEnvio { operacao: OperacaoRegra; estagio_minimo: string | null; versao?: number }
export interface RegrasEnvio { diferenciar?: boolean; regras: RegraEnvio[] }
export interface RegrasEnvioSalvar {
  diferenciar: boolean;
  regras: { operacao: OperacaoRegra; estagio_minimo: string }[];
}

/** One stage of the pinned standard as a consumer may see it: label and order only (never rule, points or text). */
export interface Estagio { chave: string; rotulo: string; ordem: number; conclusivo: boolean }

export type FriosModo = "intervalo" | "manha_seguinte";
export interface Politicas {
  frios: { ativo: boolean; modo: FriosModo; minutos: number };
  captacoes: "enviar" | "notificar";
  whatsapp_invalido: boolean;
  pesquisa: boolean;
}
/** 30 min … 10 h. */
export const FRIOS_MINUTOS = [30, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600] as const;
export const rotuloMinutos = (m: number): string =>
  m < 60 ? `${m} min` : m % 60 === 0 ? `${m / 60} ${m === 60 ? "hora" : "horas"}` : `${m} min`;

export const ENVIO_KEY = ["sw", "julia", "envio"] as const;

const MENSAGENS: Record<string, string> = {
  estagio_invalido: "Escolha a etapa a partir da qual o lead é enviado ao SW.",
  operacoes_invalidas: "Informe uma regra para compra e outra para aluguel, ou uma única regra para todas as operações.",
};
export function mensagemErroEnvio(err: unknown, fallback: string): string {
  const code = (err as { body?: { error?: { code?: unknown } } } | null)?.body?.error?.code;
  if (typeof code === "string" && MENSAGENS[code]) return MENSAGENS[code];
  return mensagemErroServidor(err, fallback);
}

export function useEnvioRegras() {
  return useQuery({
    queryKey: [...ENVIO_KEY, "regras"] as const,
    queryFn: async () => (await api.get<{ data: RegrasEnvio }>("/api/julia/envio/regras")).data,
  });
}
export function useSalvarEnvioRegras() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, RegrasEnvioSalvar>({ // noc-allow: invalidate-only — the PUT answer is not the read shape: the server normalises the rules (per-operation fallback, derived `diferenciar`)
    mutationFn: (body) => api.put("/api/julia/envio/regras", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ENVIO_KEY }),
  });
}

/** Ordered stages for the `estagio_minimo` dropdown. Accepts the SW envelope or a bare list. */
export function useQualificacaoEstagios() {
  return useQuery({
    queryKey: ["sw", "julia", "qualificacao", "estagios"] as const,
    retry: false,
    queryFn: async (): Promise<Estagio[]> => {
      const r = await api.get<{ data?: Estagio[] } | Estagio[]>("/api/julia/qualificacao/estagios");
      const lista = Array.isArray(r) ? r : (r?.data ?? []);
      return [...lista].sort((a, b) => a.ordem - b.ordem || a.chave.localeCompare(b.chave));
    },
  });
}

export function useEnvioPoliticas() {
  return useQuery({
    queryKey: [...ENVIO_KEY, "politicas"] as const,
    queryFn: async () => (await api.get<{ data: Politicas }>("/api/julia/envio/politicas")).data,
  });
}
export function useSalvarEnvioPoliticas() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, Politicas>({ // noc-allow: invalidate-only — the PUT answer is not the read shape (`{data: Politicas}`): the server normalises and clamps the policies
    mutationFn: (body) => api.put("/api/julia/envio/politicas", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ENVIO_KEY }),
  });
}

/** The stage a rule fires from, per operation (null = no rule yet). */
export function estagioDe(regras: RegrasEnvio | undefined, op: OperacaoRegra): string | null {
  return regras?.regras?.find((x) => x.operacao === op)?.estagio_minimo ?? null;
}
export function separaOperacao(regras: RegrasEnvio | undefined): boolean {
  return regras?.diferenciar ?? !!regras?.regras?.some((r) => r.operacao === "compra" || r.operacao === "aluguel");
}
export const rotuloOperacao = (op: OperacaoRegra) =>
  op === "ambas" ? "Compra e aluguel" : op === "compra" ? "Compra" : "Aluguel";
