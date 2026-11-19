/**
 * Julia › Reengajamento — config padrão + réguas + tentativas (contract §6 W4).
 *
 * SW envelope `{data}`; errors `{error:{code,message}}`. Loading is two signals
 * off `data` in the consumers (never `isLoading`); lists keep previous data.
 */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";

export type EsperaUnidade = "minutos" | "horas" | "dias";

export interface ReengajamentoConfig {
  minutos_ativo: boolean;
  minutos_intervalo: number; // 5..60 step 5 (60 = "1 hora")
  horas_ativo: boolean;
  horas_intervalo: number; // 1..11
  /** Lais study S1: Julia speaks first to a new portal (OLX / ImovelWeb) lead. Off until the owner turns it on. */
  portal_primeiro_contato_ativo: boolean;
  /** Business hours (America/Sao_Paulo): messages outside them wait for the next opening. "HH:MM"; opening < closing. */
  horario_abertura: string;
  horario_fechamento: string;
  /** ISO weekdays served: 1 = segunda .. 7 = domingo. At least one. */
  dias_atendimento: number[];
  /** Optional opener for a portal lead; must carry {link}. null/"" = the org's mensagem inicial. Send "" to clear. */
  portal_primeiro_contato_texto: string | null;
}

export const DIAS_SEMANA = [
  { dia: 1, sigla: "Seg", nome: "segunda-feira" },
  { dia: 2, sigla: "Ter", nome: "terça-feira" },
  { dia: 3, sigla: "Qua", nome: "quarta-feira" },
  { dia: 4, sigla: "Qui", nome: "quinta-feira" },
  { dia: 5, sigla: "Sex", nome: "sexta-feira" },
  { dia: 6, sigla: "Sáb", nome: "sábado" },
  { dia: 7, sigla: "Dom", nome: "domingo" },
] as const;
export const FUSO_ATENDIMENTO = "America/Sao_Paulo";

/** Client-side mirror of the server rule, so the refusal shows before the round trip (the server stays the authority). */
export function validarHorario(abertura: string, fechamento: string, dias: number[]): string | null {
  if (!/^\d{2}:\d{2}$/.test(abertura) || !/^\d{2}:\d{2}$/.test(fechamento)) return "Informe os horários de abertura e fechamento.";
  if (abertura >= fechamento) return "A abertura precisa ser antes do fechamento no mesmo dia (horário que passa da meia-noite não é suportado).";
  if (dias.length === 0) return "Escolha ao menos um dia da semana.";
  return null;
}

/** The portal opener must carry the privacy-notice link (LGPD); blank is fine (= the default message). */
export function validarTextoPortal(texto: string): string | null {
  const t = texto.trim();
  if (!t) return null;
  if (!t.includes("{link}")) return "A mensagem precisa conter {link}: é o link do aviso de privacidade (LGPD).";
  if (t.length > TEXTO_MAX) return `A mensagem pode ter no máximo ${TEXTO_MAX} caracteres.`;
  return null;
}

export interface ReguaTentativa {
  id: string;
  regua_id?: string;
  ordem: number;
  espera_valor: number;
  espera_unidade: EsperaUnidade;
  texto: string | null;
  template_id: string | null;
  ativa: boolean;
}

export interface Regua {
  id: string;
  nome: string;
  ativa: boolean;
  compra: boolean;
  aluguel: boolean;
  tentativas?: ReguaTentativa[];
  tentativas_count?: number;
}

export interface ReguaInput {
  nome: string;
  compra: boolean;
  aluguel: boolean;
}

export interface TentativaInput {
  espera_valor: number;
  espera_unidade: EsperaUnidade;
  texto?: string | null;
  template_id?: string | null;
  ativa?: boolean;
}

export const MAX_TENTATIVAS = 3;
export const TEXTO_MAX = 1024;
export const MINUTOS_OPCOES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60] as const;
export const HORAS_OPCOES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] as const;

const BASE = "/api/julia/reengajamento";
export const CONFIG_KEY = ["sw", "julia", "reengajamento", "config"] as const;
export const REGUAS_KEY = ["sw", "julia", "reengajamento", "reguas"] as const;
const reguaKey = (id: string) => [...REGUAS_KEY, id] as const;

/** pt-BR sentence per refusal code of this page. */
const MENSAGENS: Record<string, string> = {
  regua_sem_tentativa: "Adicione ao menos uma tentativa de contato ativa antes de ativar a régua.",
  limite_tentativas: `Cada régua aceita no máximo ${MAX_TENTATIVAS} tentativas de contato.`,
  ultima_tentativa_ativa: "Uma régua ativa precisa de ao menos uma tentativa ativa. Desative a régua primeiro.",
};

export function codigoErroReengajamento(err: unknown): string | null {
  const c = (err as { body?: { error?: { code?: unknown } } } | null | undefined)?.body?.error?.code;
  return typeof c === "string" ? c : null;
}

export function mensagemErroReengajamento(err: unknown, fallback: string): string {
  const c = codigoErroReengajamento(err);
  if (c && MENSAGENS[c]) return MENSAGENS[c];
  return mensagemErroJulia(err, fallback);
}

export function useReengajamentoConfig() {
  return useQuery({
    queryKey: CONFIG_KEY,
    placeholderData: (prev) => prev,
    queryFn: async () => (await api.get<{ data: ReengajamentoConfig }>(`${BASE}/config`)).data,
  });
}

export function useSalvarReengajamentoConfig() {
  // One row, replaced by the server's answer (it carries the normalised hours). Nothing is applied optimistically, so a
  // refusal (422) leaves the cache untouched and reaches the caller's onError.
  return useCacheWriteMutation<ReengajamentoConfig, ReengajamentoConfig>({
    mutationFn: async (body) => (await api.put<{ data: ReengajamentoConfig }>(`${BASE}/config`, body)).data,
    targets: [{ queryKey: CONFIG_KEY, commit: (_old: ReengajamentoConfig | undefined, saved) => saved }],
  });
}

export function useReguas() {
  return useQuery({
    queryKey: REGUAS_KEY,
    placeholderData: (prev) => prev,
    queryFn: async () => (await api.get<{ data: Regua[] }>(`${BASE}/reguas`)).data,
  });
}

export function useRegua(id: string | undefined) {
  return useQuery({
    queryKey: reguaKey(id ?? "_none"),
    enabled: !!id,
    placeholderData: (prev) => prev,
    queryFn: async () => (await api.get<{ data: Regua }>(`${BASE}/reguas/${id}`)).data,
  });
}

/** Lists keep the settle refresh for server-computed fields (`tentativas_count`, readiness). */
const REGUAS_SETTLE = [REGUAS_KEY];

export function useCriarRegua() {
  return useCacheWriteMutation<Regua, ReguaInput>({
    mutationFn: async (body) => (await api.post<{ data: Regua }>(`${BASE}/reguas`, body)).data,
    targets: [{ queryKey: REGUAS_KEY, commit: (old: Regua[] | undefined, saved) => listOps.append(old, saved) }],
  });
}

export function useAtualizarRegua(id: string) {
  return useCacheWriteMutation<Regua, Partial<ReguaInput>>({
    mutationFn: async (body) => (await api.patch<{ data: Regua }>(`${BASE}/reguas/${id}`, body)).data,
    // Patch (not replace): a list row may not carry the `tentativas` the answer omits.
    targets: (body) => [
      {
        queryKey: REGUAS_KEY,
        optimistic: (old: Regua[] | undefined) => listOps.patch(old, id, body),
        commit: (old: Regua[] | undefined, saved) => listOps.patch(old, id, saved),
      },
      {
        queryKey: reguaKey(id),
        optimistic: (old: Regua | undefined) => listOps.merge(old, body),
        commit: (old: Regua | undefined, saved) => listOps.merge(old, saved),
      },
    ],
  });
}

export function useExcluirRegua() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/reguas/${id}`),
    targets: (id) => [{ queryKey: REGUAS_KEY, optimistic: (old: Regua[] | undefined) => listOps.remove(old, id) }],
  });
}

export function useAtivarRegua(id: string) {
  return useCacheWriteMutation<Regua, boolean>({
    mutationFn: async (ativar) =>
      (await api.post<{ data: Regua }>(`${BASE}/reguas/${id}/${ativar ? "ativar" : "desativar"}`, {})).data,
    // The server may refuse (no active attempt): rollback restores, the answer commits.
    targets: (ativar) => [
      {
        queryKey: REGUAS_KEY,
        optimistic: (old: Regua[] | undefined) => listOps.patch(old, id, { ativa: ativar }),
        commit: (old: Regua[] | undefined, saved) => listOps.patch(old, id, saved),
      },
      {
        queryKey: reguaKey(id),
        optimistic: (old: Regua | undefined) => listOps.merge(old, { ativa: ativar }),
        commit: (old: Regua | undefined, saved) => listOps.merge(old, saved),
      },
    ],
  });
}

export function useCriarTentativa(reguaId: string) {
  return useCacheWriteMutation<ReguaTentativa, TentativaInput>({
    mutationFn: async (body) =>
      (await api.post<{ data: ReguaTentativa }>(`${BASE}/reguas/${reguaId}/tentativas`, body)).data,
    targets: [
      {
        queryKey: reguaKey(reguaId),
        commit: (old: Regua | undefined, saved) =>
          listOps.within(old, "tentativas", (l) => listOps.replace(l, saved.id, saved)),
      },
    ],
    invalidate: REGUAS_SETTLE,
  });
}

export function useAtualizarTentativa(reguaId: string) {
  return useCacheWriteMutation<ReguaTentativa, { id: string; body: Partial<TentativaInput> }>({
    mutationFn: async ({ id, body }) =>
      (await api.patch<{ data: ReguaTentativa }>(`${BASE}/reguas/${reguaId}/tentativas/${id}`, body)).data,
    targets: ({ id, body }) => [
      {
        queryKey: reguaKey(reguaId),
        optimistic: (old: Regua | undefined) =>
          listOps.within(old, "tentativas", (l) => listOps.patch(l, id, body)),
        commit: (old: Regua | undefined, saved) =>
          listOps.within(old, "tentativas", (l) => listOps.replace(l, saved.id, saved)),
      },
    ],
    invalidate: REGUAS_SETTLE,
  });
}

export function useExcluirTentativa(reguaId: string) {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/reguas/${reguaId}/tentativas/${id}`),
    targets: (id) => [
      {
        queryKey: reguaKey(reguaId),
        optimistic: (old: Regua | undefined) => listOps.within(old, "tentativas", (l) => listOps.remove(l, id)),
      },
    ],
    invalidate: REGUAS_SETTLE,
  });
}
