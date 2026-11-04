/**
 * Julia v3 (CONTRACT §12.5/§12.7) — report destination, catalog source, and the per-lead reports.
 *
 *   GET|PUT /api/julia/relatorio-destino    org admin write: {modo: numero|responsavel, numero_e164}
 *   GET|PUT /api/julia/catalogo-fonte       org admin write: {fonte: vista|espelho}
 *   GET     /api/julia/contatos/{id}/relatorios   newest first
 *
 * Envelope `{data: …}`. The offered-properties field access lives in ONE adapter (`imoveisOferecidos`) so a backend
 * rename is a one-line change.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api } from "@/lib/api";

export type ModoRelatorioDestino = "numero" | "responsavel";
export interface RelatorioDestino {
  modo: ModoRelatorioDestino;
  numero_e164: string | null;
}
export type FonteCatalogo = "vista" | "espelho";
export interface CatalogoFonte {
  fonte: FonteCatalogo;
}
export type TipoRelatorio = "handoff" | "conclusao" | "alerta";
export type EnvioStatus = "pendente" | "enviado" | "falhou" | "sem_destino";
export interface RelatorioJulia {
  id: string;
  tipo: TipoRelatorio;
  texto: string;
  dados: Record<string, unknown> | null;
  destino_e164: string | null;
  envio_status: EnvioStatus;
  envio_erro: string | null;
  created_at: string;
}
export interface ImovelOferecido {
  codigo: string;
  link: string | null;
}

export const RELATORIO_DESTINO_KEY = ["sw", "julia", "relatorio-destino"] as const;
export const CATALOGO_FONTE_KEY = ["sw", "julia", "catalogo-fonte"] as const;
export const juliaRelatoriosKey = (contatoId: string | null) => ["sw", "julia", "relatorios-lead", contatoId] as const;

/** The ONLY place that knows how offered properties arrive on a lead/contato payload. */
export function imoveisOferecidos(payload: unknown): ImovelOferecido[] {
  const p = (payload ?? {}) as {
    imoveis_oferecidos?: unknown;
    imoveis_oferecidos_links?: unknown;
  };
  const links = new Map<string, string | null>();
  if (Array.isArray(p.imoveis_oferecidos_links)) {
    for (const it of p.imoveis_oferecidos_links as { codigo?: unknown; link?: unknown }[]) {
      if (it && typeof it.codigo === "string") links.set(it.codigo, typeof it.link === "string" ? it.link : null);
    }
  }
  const codigos = Array.isArray(p.imoveis_oferecidos)
    ? (p.imoveis_oferecidos as unknown[]).filter((c): c is string => typeof c === "string")
    : [...links.keys()];
  return codigos.map((codigo) => ({ codigo, link: links.get(codigo) ?? null }));
}

export function useRelatorioDestino() {
  return useQuery({
    queryKey: RELATORIO_DESTINO_KEY,
    queryFn: async () => (await api.get<{ data: RelatorioDestino }>("/api/julia/relatorio-destino")).data,
  });
}

export function useSalvarRelatorioDestino() {
  return useCacheWriteMutation<{ data: RelatorioDestino }, RelatorioDestino>({
    mutationFn: (body) => api.put<{ data: RelatorioDestino }>("/api/julia/relatorio-destino", body),
    targets: (body) => [{ queryKey: RELATORIO_DESTINO_KEY, optimistic: () => body, commit: (_old: RelatorioDestino | undefined, res: { data: RelatorioDestino }) => res.data }],
  });
}

export function useCatalogoFonte() {
  return useQuery({
    queryKey: CATALOGO_FONTE_KEY,
    queryFn: async () => (await api.get<{ data: CatalogoFonte }>("/api/julia/catalogo-fonte")).data,
  });
}

export function useSalvarCatalogoFonte() {
  return useCacheWriteMutation<{ data: CatalogoFonte }, CatalogoFonte>({
    mutationFn: (body) => api.put<{ data: CatalogoFonte }>("/api/julia/catalogo-fonte", body),
    targets: (body) => [{ queryKey: CATALOGO_FONTE_KEY, optimistic: () => body, commit: (_old: CatalogoFonte | undefined, res: { data: CatalogoFonte }) => res.data }],
  });
}

export function useJuliaRelatorios(contatoId: string | null) {
  return useQuery({
    queryKey: juliaRelatoriosKey(contatoId),
    enabled: !!contatoId,
    retry: false,
    queryFn: async () =>
      (await api.get<{ data: RelatorioJulia[] }>(`/api/julia/contatos/${encodeURIComponent(contatoId as string)}/relatorios`)).data,
    placeholderData: (prev) => prev,
  });
}
