/**
 * Lais › Visitas (contract wave 5).
 *
 *   GET/PUT /api/lais/visitas/config            member read / admin write
 *   GET     /api/lais/visitas?view=&data=       list for the visible window
 *   POST    /api/lais/visitas/{id}/confirmar | remarcar | cancelar → {data: visita}
 *
 * Loading = two signals off `data` (never `isLoading`); the window query is
 * keyed by view+date so it keeps `placeholderData: prev` while paging.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { mensagemErroServidor } from "@/lib/erroServidor";

export const DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"] as const;
export type Dia = (typeof DIAS)[number];
export const DIA_LABEL: Record<Dia, string> = {
  seg: "Segunda", ter: "Terça", qua: "Quarta", qui: "Quinta", sex: "Sexta", sab: "Sábado", dom: "Domingo",
};
export type Operacao = "geral" | "compra" | "aluguel";
export type VisitaStatus = "solicitada" | "confirmada" | "remarcada" | "cancelada";
export type VisitasView = "semana" | "dia";

export interface Faixa { inicio: string; fim: string }
export interface OperacaoConfig {
  ativo: boolean;
  cpf_obrigatorio: boolean;
  min_dias: number;
  min_horas: number;
  max_dias: number;
  grade: Record<Dia, Faixa[]>;
}
export interface VisitasConfig {
  separar_operacao: boolean;
  config: Partial<Record<Operacao, OperacaoConfig>>;
}
export interface Visita {
  id: string;
  contato_id?: string | null;
  contato_nome?: string | null;
  codigo_imovel?: string | null;
  operacao?: "compra" | "aluguel" | null;
  inicio: string;
  fim: string;
  status: VisitaStatus;
  responsavel_user_id?: string | null;
  responsavel_nome?: string | null;
}

export const VISITAS_KEY = ["sw", "lais", "visitas"] as const;
export const configKey = [...VISITAS_KEY, "config"] as const;

export function gradeVazia(): Record<Dia, Faixa[]> {
  return { seg: [], ter: [], qua: [], qui: [], sex: [], sab: [], dom: [] };
}
export function operacaoPadrao(): OperacaoConfig {
  return { ativo: false, cpf_obrigatorio: false, min_dias: 0, min_horas: 0, max_dias: 30, grade: gradeVazia() };
}
/** True when at least one operation accepts visit requests. */
export function visitasAtivas(c: VisitasConfig | undefined): boolean {
  return !!c && Object.values(c.config ?? {}).some((o) => o?.ativo);
}

const MENSAGENS: Record<string, string> = {
  transicao_invalida: "Esta visita não pode mais mudar para esse status (outra pessoa já a alterou). Atualizamos a lista.",
  view_invalida: "Visualização inválida. Use semana ou dia.",
};
export function mensagemErroVisitas(err: unknown, fallback: string): string {
  const code = (err as { body?: { error?: { code?: unknown } } } | null)?.body?.error?.code;
  if (typeof code === "string" && MENSAGENS[code]) return MENSAGENS[code];
  return mensagemErroServidor(err, fallback);
}
export const ehTransicaoInvalida = (err: unknown): boolean =>
  (err as { body?: { error?: { code?: unknown } } } | null)?.body?.error?.code === "transicao_invalida";

export function useVisitasConfig() {
  return useQuery({
    queryKey: configKey,
    queryFn: async () => (await api.get<{ data: VisitasConfig }>("/api/lais/visitas/config")).data,
  });
}

export function useSalvarVisitasConfig() {
  const qc = useQueryClient();
  return useMutation<unknown, unknown, VisitasConfig>({
    mutationFn: (body) => api.put("/api/lais/visitas/config", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: VISITAS_KEY }),
  });
}

export function useVisitas(view: VisitasView, data: string) {
  return useQuery({
    queryKey: [...VISITAS_KEY, "lista", view, data] as const,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const res = await api.get<{ data: Visita[] | { items: Visita[] } }>(
        `/api/lais/visitas?view=${view}&data=${data}`,
      );
      return Array.isArray(res.data) ? res.data : (res.data?.items ?? []);
    },
  });
}

export type VisitaAcao =
  | { id: string; acao: "confirmar" }
  | { id: string; acao: "remarcar"; inicio: string; fim: string }
  | { id: string; acao: "cancelar"; motivo: string };

export function useAcaoVisita() {
  const qc = useQueryClient();
  return useMutation<Visita, unknown, VisitaAcao>({
    mutationFn: async (a) => {
      const { id, acao, ...body } = a;
      return (await api.post<{ data: Visita }>(`/api/lais/visitas/${id}/${acao}`, body)).data;
    },
    // 409 transicao_invalida means someone else moved it: refresh either way.
    onSettled: () => qc.invalidateQueries({ queryKey: VISITAS_KEY }),
  });
}
