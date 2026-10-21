/** Julia › Modelos de mensagem — templates (contract §14 W12). Envelope `{data}`. */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export type ModeloStatus = "rascunho" | "enviado_meta" | "aprovado" | "rejeitado";

export const CATEGORIAS = [
  "Administrativo",
  "Campanha",
  "Cobrança",
  "Documentação",
  "Primeiro contato",
  "Reativação",
  "Visita",
  "Outros",
] as const;
export type Categoria = (typeof CATEGORIAS)[number];

export const CONTEUDO_MAX = 1024;

export const STATUS_LABEL: Record<ModeloStatus, string> = {
  rascunho: "Rascunho",
  enviado_meta: "Enviado à Meta",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
};

/** The 10 insertable parameters: label, `{{token}}` and a simulation example. */
export const PARAMETROS = [
  { label: "Nome da pessoa", token: "nome_pessoa", exemplo: "Maria" },
  { label: "Nome da Julia", token: "nome_julia", exemplo: "Julia" },
  { label: "Nome da imobiliária", token: "nome_imobiliaria", exemplo: "Imobiliária Exemplo" },
  { label: "Mensagem", token: "mensagem", exemplo: "Olá, tudo bem?" },
  { label: "Data da visita", token: "data_visita", exemplo: "20/10/2026" },
  { label: "Código do imóvel", token: "codigo_imovel", exemplo: "AP0123" },
  { label: "Link do imóvel", token: "link_imovel", exemplo: "https://exemplo.com/imovel/AP0123" },
  { label: "Nome do atendente", token: "nome_atendente", exemplo: "Carlos" },
  { label: "Imóvel da visita", token: "imovel_visita", exemplo: "Apartamento 2 quartos" },
  { label: "Data e horário da visita", token: "data_hora_visita", exemplo: "20/10/2026 às 15:00" },
] as const;

export interface Modelo {
  id: string;
  nome: string;
  categoria: Categoria;
  conteudo: string;
  status: ModeloStatus;
}
export interface ModeloInput {
  nome: string;
  categoria: Categoria;
  conteudo: string;
}

export const MODELOS_KEY = ["sw", "julia", "modelos"] as const;
const BASE = "/api/julia/modelos";

/** `{{token}}` placeholders found in a body, in order, de-duplicated. */
export function parametrosDoTexto(texto: string): string[] {
  const out: string[] = [];
  for (const m of texto.matchAll(/\{\{\s*([a-z_]+)\s*\}\}/g)) if (!out.includes(m[1])) out.push(m[1]);
  return out;
}

export function simular(texto: string, valores: Record<string, string>): string {
  return texto.replace(/\{\{\s*([a-z_]+)\s*\}\}/g, (_, t: string) => valores[t] || `{{${t}}}`);
}

export function useModelos() {
  return useQuery({
    queryKey: MODELOS_KEY,
    placeholderData: (prev) => prev,
    queryFn: async () => (await api.get<{ data: Modelo[] }>(BASE)).data,
  });
}

export function useCriarModelo() {
  return useCacheWriteMutation<Modelo, ModeloInput>({
    mutationFn: async (body) => (await api.post<{ data: Modelo }>(BASE, body)).data,
    targets: [{ queryKey: MODELOS_KEY, commit: (old, saved) => listOps.replace(old, saved.id, saved) }],
  });
}

export function useExcluirModelo() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: async (id) => api.delete(`${BASE}/${id}`),
    targets: (id) => [{ queryKey: MODELOS_KEY, optimistic: (old) => listOps.remove(old, id) }],
  });
}
