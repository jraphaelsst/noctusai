/**
 * Julia › Reengajamento — config padrão + réguas + tentativas (contract §6 W4).
 *
 * SW envelope `{data}`; errors `{error:{code,message}}`. Loading is two signals
 * off `data` in the consumers (never `isLoading`); lists keep previous data.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";

export type EsperaUnidade = "minutos" | "horas" | "dias";

export interface ReengajamentoConfig {
  minutos_ativo: boolean;
  minutos_intervalo: number; // 5..60 step 5 (60 = "1 hora")
  horas_ativo: boolean;
  horas_intervalo: number; // 1..11
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
  const qc = useQueryClient();
  return useMutation<ReengajamentoConfig, unknown, ReengajamentoConfig>({
    mutationFn: async (body) => (await api.put<{ data: ReengajamentoConfig }>(`${BASE}/config`, body)).data,
    onSuccess: (row) => qc.setQueryData(CONFIG_KEY, row),
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

function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: REGUAS_KEY });
}

export function useCriarRegua() {
  const inv = useInvalidar();
  return useMutation<Regua, unknown, ReguaInput>({
    mutationFn: async (body) => (await api.post<{ data: Regua }>(`${BASE}/reguas`, body)).data,
    onSuccess: inv,
  });
}

export function useAtualizarRegua(id: string) {
  const inv = useInvalidar();
  return useMutation<Regua, unknown, Partial<ReguaInput>>({
    mutationFn: async (body) => (await api.patch<{ data: Regua }>(`${BASE}/reguas/${id}`, body)).data,
    onSuccess: inv,
  });
}

export function useExcluirRegua() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/reguas/${id}`),
    onSuccess: inv,
  });
}

export function useAtivarRegua(id: string) {
  const inv = useInvalidar();
  return useMutation<Regua, unknown, boolean>({
    mutationFn: async (ativar) =>
      (await api.post<{ data: Regua }>(`${BASE}/reguas/${id}/${ativar ? "ativar" : "desativar"}`, {})).data,
    onSuccess: inv,
  });
}

export function useCriarTentativa(reguaId: string) {
  const inv = useInvalidar();
  return useMutation<ReguaTentativa, unknown, TentativaInput>({
    mutationFn: async (body) =>
      (await api.post<{ data: ReguaTentativa }>(`${BASE}/reguas/${reguaId}/tentativas`, body)).data,
    onSuccess: inv,
  });
}

export function useAtualizarTentativa(reguaId: string) {
  const inv = useInvalidar();
  return useMutation<ReguaTentativa, unknown, { id: string; body: Partial<TentativaInput> }>({
    mutationFn: async ({ id, body }) =>
      (await api.patch<{ data: ReguaTentativa }>(`${BASE}/reguas/${reguaId}/tentativas/${id}`, body)).data,
    onSuccess: inv,
  });
}

export function useExcluirTentativa(reguaId: string) {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/reguas/${reguaId}/tentativas/${id}`),
    onSuccess: inv,
  });
}
