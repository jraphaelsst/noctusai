/** Julia › Disparos em massa (contract §14 W12). Envelope `{data, meta?}`. */
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import type { Transporte } from "@/hooks/useJuliaTransporte";

export type DisparoTipo = "remarketing" | "atualizacao_anuncios";
export type DisparoStatus = "rascunho" | "agendado" | "enviando" | "enviado" | "cancelado" | "erro";
export type AlvoStatus = "pendente" | "enviado" | "respondido" | "enviado_sw" | "erro";

export const TIPO_LABEL: Record<DisparoTipo, string> = {
  remarketing: "Remarketing",
  atualizacao_anuncios: "Atualização de anúncios",
};
export const STATUS_LABEL: Record<DisparoStatus, string> = {
  rascunho: "Rascunho",
  agendado: "Agendado",
  enviando: "Enviando",
  enviado: "Enviado",
  cancelado: "Cancelado",
  erro: "Erro",
};
export const SEGMENTOS = [
  { value: "leads_3_15", label: "Leads de 3 a 15 dias sem resposta" },
  { value: "leads_7_30", label: "Leads de 7 a 30 dias sem resposta" },
  { value: "proprietarios", label: "Proprietários de imóveis anunciados" },
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

export const DISPAROS_KEY = ["sw", "julia", "disparos"] as const;
const BASE = "/api/julia/disparos";

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

/** Status change shown on the list row and on the open detail, then confirmed by the settle. */
const mudarStatus = (id: string, status: DisparoStatus) => [
  {
    queryKey: DISPAROS_KEY,
    optimistic: (old: DisparosList | undefined) =>
      old ? listOps.within(old, "items", (l) => listOps.patch(l, id, { status }) ?? l) : old,
  },
  {
    queryKey: [...DISPAROS_KEY, id],
    optimistic: (old: DisparoDetalhe | undefined) => listOps.merge(old, { status }),
  },
];

export function useCriarDisparo() {
  return useCacheWriteMutation<Disparo, DisparoInput>({
    mutationFn: async (body) => (await api.post<{ data: Disparo }>(BASE, body)).data,
    targets: [
      {
        queryKey: DISPAROS_KEY,
        commit: (old: DisparosList | undefined, saved) =>
          old ? listOps.within(old, "items", (l) => listOps.replace(l, saved.id, saved) ?? l) : old,
      },
    ],
  });
}

export function useEnviarDisparo() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.post(`${BASE}/${id}/enviar`, {}),
    // The send starts server-side: it reads "enviando" until the worker finishes.
    targets: (id) => mudarStatus(id, "enviando"),
  });
}

export function useCancelarDisparo() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.post(`${BASE}/${id}/cancelar`, {}),
    targets: (id) => mudarStatus(id, "cancelado"),
  });
}
