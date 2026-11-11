/**
 * Data hooks of `/avaliacao` (the owner's blind labelling of the scheduling classifier).
 *
 * Contract (backend `app/routers/classificacao_router.py`, bare bodies, tier `org`, admin only):
 *   GET  /api/classificacao/amostra?modo=cego            -> { modo, prompt_version, modelo, itens: [{intake_id, output_id, texto, recebida_em}] }
 *   POST /api/classificacao/rotulos {intake_id, output_id, rotulo, rodada} -> { evento_id, repetido, intake_id, output_id, rotulo, rodada }
 *   GET  /api/classificacao/rotulos/progresso            -> { rotuladas, por_rotulo: {agendamento, nao_agendamento, nao_sei} }
 *   GET  /api/classificacao/rotulos/concordancia         -> { grupos: [{prompt_version, modelo, total, nao_sei, decididos, concordam, concordancia, matriz}] }
 * The blind sample never carries the verdict; only the concordancia read does, and only as counts. Nothing here polls.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export type Rotulo = "agendamento" | "nao_agendamento" | "nao_sei";
export const ROTULOS: Rotulo[] = ["agendamento", "nao_agendamento", "nao_sei"];

export interface ItemAmostra {
  intake_id: string;
  output_id: string;
  texto: string;
  recebida_em: string;
}
export interface Amostra {
  modo: "cego";
  prompt_version: string;
  modelo: string;
  itens: ItemAmostra[];
}
export interface Progresso {
  rotuladas: number;
  por_rotulo: Record<Rotulo, number>;
}
export type Matriz = Record<"agendamento" | "outro", Record<Rotulo, number>>;
export interface GrupoConcordancia {
  prompt_version: string;
  modelo: string;
  total: number;
  nao_sei: number;
  decididos: number;
  concordam: number;
  concordancia: number | null;
  matriz: Matriz;
}
export interface RotuloSalvo {
  evento_id: string;
  repetido: boolean;
  intake_id: string;
  output_id: string;
  rotulo: Rotulo;
  rodada: number;
}
export interface RotuloVars {
  intake_id: string;
  output_id: string;
  rotulo: Rotulo;
  rodada: number;
}

export const KEYS = {
  amostra: ["avaliacao", "amostra"] as const,
  progresso: ["avaliacao", "progresso"] as const,
  concordancia: ["avaliacao", "concordancia"] as const,
};

/**
 * One draw of the stratified sample. It is NOT refetched on focus/reconnect (a re-draw would swap the message under
 * the labeller's eyes); the page tracks consumed items itself and asks for a new draw explicitly when the queue is
 * empty -- the server never re-offers a message the caller already labelled.
 */
export function useAmostra() {
  return useQuery<Amostra, Error>({
    queryKey: KEYS.amostra,
    queryFn: () => api.get("/api/classificacao/amostra?por_estrato=10&modo=cego") as Promise<Amostra>,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
}

export function useProgresso() {
  return useQuery<Progresso, Error>({
    queryKey: KEYS.progresso,
    queryFn: () => api.get("/api/classificacao/rotulos/progresso") as Promise<Progresso>,
    staleTime: 30_000,
    retry: false,
  });
}

export function useConcordancia(enabled: boolean) {
  return useQuery<{ grupos: GrupoConcordancia[] }, Error>({
    queryKey: KEYS.concordancia,
    queryFn: () => api.get("/api/classificacao/rotulos/concordancia") as Promise<{ grupos: GrupoConcordancia[] }>,
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * Record one label. The progress counter moves the instant the button is pressed (optimistic, rolled back on a
 * refusal) and the server's answer is the commit; the agreement read is derived, so it is refreshed in the background.
 */
export function useRegistrarRotulo() {
  return useCacheWriteMutation<RotuloSalvo, RotuloVars>({
    mutationFn: (vars) => api.post("/api/classificacao/rotulos", vars) as Promise<RotuloSalvo>,
    targets: ({ rotulo }) => [
      {
        queryKey: KEYS.progresso,
        optimistic: (old: Progresso | undefined) =>
          old && { rotuladas: old.rotuladas + 1, por_rotulo: { ...old.por_rotulo, [rotulo]: old.por_rotulo[rotulo] + 1 } },
      },
    ],
    invalidate: [KEYS.concordancia],
  });
}
