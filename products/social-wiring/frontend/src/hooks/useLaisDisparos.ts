/** Lais › Disparos em massa (contract §14 W12). Envelope `{data, meta?}`. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Transporte } from "@/hooks/useLaisTransporte";

export type DisparoTipo = "remarketing" | "atualizacao_anuncios";
export type DisparoStatus = "rascunho" | "agendado" | "enviado" | "cancelado" | "erro";
export type AlvoStatus = "pendente" | "enviado" | "respondido" | "enviado_sw" | "erro";

export const TIPO_LABEL: Record<DisparoTipo, string> = {
  remarketing: "Remarketing",
  atualizacao_anuncios: "Atualização de anúncios",
};
export const STATUS_LABEL: Record<DisparoStatus, string> = {
  rascunho: "Rascunho",
  agendado: "Agendado",
  enviado: "Enviado",
  cancelado: "Cancelado",
  erro: "Erro",
};
export const SEGMENTOS = [
  { value: "leads_3_15", label: "Leads de 3 a 15 dias sem resposta" },
  { value: "leads_7_30", label: "Leads de 7 a 30 dias sem resposta" },
] as const;

export interface Disparo {
  id: string;
  nome: string;
  status: DisparoStatus;
  tipo: DisparoTipo;
  contatos: number;
  segmento?: string;
  template_id?: string | null;
  agendado_para?: string | null;
}
export interface DisparoAlvo {
  id: string;
  nome: string;
  status: AlvoStatus;
}
export interface DisparoDetalhe extends Disparo {
  alvos?: DisparoAlvo[];
}
export interface DisparoInput {
  nome: string;
  tipo: DisparoTipo;
  segmento: string;
  template_id: string;
  agendado_para?: string | null;
}
export interface DisparosList {
  items: Disparo[];
  transporte?: Transporte;
}

export const DISPAROS_KEY = ["sw", "lais", "disparos"] as const;
const BASE = "/api/lais/disparos";

export function useDisparos() {
  return useQuery<DisparosList>({
    queryKey: DISPAROS_KEY,
    placeholderData: (prev) => prev,
    queryFn: async () => {
      const r = await api.get<{ data: Disparo[]; meta?: { transporte?: Transporte } }>(BASE);
      return { items: r.data, transporte: r.meta?.transporte };
    },
  });
}

export function useDisparo(id: string | null) {
  return useQuery({
    queryKey: [...DISPAROS_KEY, id ?? "_none"],
    enabled: !!id,
    placeholderData: (prev) => prev,
    queryFn: async () => (await api.get<{ data: DisparoDetalhe }>(`${BASE}/${id}`)).data,
  });
}

function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: DISPAROS_KEY });
}

export function useCriarDisparo() {
  const inv = useInvalidar();
  return useMutation<Disparo, unknown, DisparoInput>({
    mutationFn: async (body) => (await api.post<{ data: Disparo }>(BASE, body)).data,
    onSuccess: inv,
  });
}

export function useEnviarDisparo() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, string>({
    mutationFn: async (id) => api.post(`${BASE}/${id}/enviar`, {}),
    onSuccess: inv,
  });
}

export function useCancelarDisparo() {
  const inv = useInvalidar();
  return useMutation<unknown, unknown, string>({
    mutationFn: async (id) => api.post(`${BASE}/${id}/cancelar`, {}),
    onSuccess: inv,
  });
}
