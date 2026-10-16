/**
 * Lais › Envio (contract wave 3).
 *
 *   GET/PUT /api/lais/envio/regras      → {data:{regras:[{operacao, grupos}]}}
 *   GET/PUT /api/lais/envio/politicas   → {data: Politicas}
 *
 * `grupos` = OR'd groups of AND'd criteria (`[[{campo, operador, valor}]]`).
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export type OperadorCriterio = "=" | "preenchido" | ">=" | "<=" | "entre";
export interface Criterio {
  campo: string;
  operador: OperadorCriterio;
  /** number | [min, max] (entre) | boolean | string; null for `preenchido`. */
  valor: unknown;
}
export type Grupo = Criterio[];
export type OperacaoRegra = "compra" | "aluguel" | "ambas";
export interface RegraEnvio { operacao: OperacaoRegra; grupos: Grupo[] }
export interface RegrasEnvio { regras: RegraEnvio[] }

/** The locked base criterion — always first of the first group. */
export const CRITERIO_BASE: Criterio = { campo: "comportamento", operador: "=", valor: "qualificado" };
export const CRITERIO_BASE_ROTULO = "Comportamento = Qualificado via inteligência da Julia";

export interface CampoCriterio { campo: string; rotulo: string; numerico?: boolean; moeda?: boolean; booleano?: boolean }
export const CAMPOS_CRITERIO: CampoCriterio[] = [
  { campo: "visita_solicitada", rotulo: "Visita — Pré-agendada via formulário da Julia", booleano: true },
  { campo: "nome", rotulo: "Nome" },
  { campo: "email", rotulo: "E-mail" },
  { campo: "bairro", rotulo: "Bairro" },
  { campo: "tipo_imovel", rotulo: "Tipo do imóvel" },
  { campo: "orcamento", rotulo: "Orçamento", numerico: true, moeda: true },
  { campo: "renda", rotulo: "Renda", numerico: true, moeda: true },
  { campo: "quartos", rotulo: "Quartos", numerico: true },
  { campo: "vagas", rotulo: "Vagas", numerico: true },
];

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

export const ENVIO_KEY = ["sw", "lais", "envio"] as const;

const MENSAGENS: Record<string, string> = {
  criterio_invalido: "Há um critério incompleto ou inválido. Revise os campos.",
  regra_sem_comportamento: "Defina ao menos um critério no cartão Comportamento.",
};
export function mensagemErroEnvio(err: unknown, fallback: string): string {
  const code = (err as { body?: { error?: { code?: unknown } } } | null)?.body?.error?.code;
  if (typeof code === "string" && MENSAGENS[code]) return MENSAGENS[code];
  return mensagemErroServidor(err, fallback);
}

export function useEnvioRegras() {
  return useQuery({
    queryKey: [...ENVIO_KEY, "regras"] as const,
    queryFn: async () => (await api.get<{ data: RegrasEnvio }>("/api/lais/envio/regras")).data,
  });
}
export function useSalvarEnvioRegras() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, RegrasEnvio>({
    mutationFn: (body) => api.put("/api/lais/envio/regras", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ENVIO_KEY }),
  });
}

export function useEnvioPoliticas() {
  return useQuery({
    queryKey: [...ENVIO_KEY, "politicas"] as const,
    queryFn: async () => (await api.get<{ data: Politicas }>("/api/lais/envio/politicas")).data,
  });
}
export function useSalvarEnvioPoliticas() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, Politicas>({
    mutationFn: (body) => api.put("/api/lais/envio/politicas", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ENVIO_KEY }),
  });
}

/** Rules → the shape the wizard edits: one entry for "ambas", or compra+aluguel. */
export function regraDe(regras: RegrasEnvio | undefined, op: OperacaoRegra): Grupo[] {
  const r = regras?.regras?.find((x) => x.operacao === op);
  return r?.grupos?.length ? r.grupos : [[CRITERIO_BASE]];
}
export function separaOperacao(regras: RegrasEnvio | undefined): boolean {
  return !!regras?.regras?.some((r) => r.operacao === "compra" || r.operacao === "aluguel");
}
