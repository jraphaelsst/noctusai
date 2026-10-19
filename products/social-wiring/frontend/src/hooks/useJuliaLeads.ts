/**
 * Julia › Leads (contract wave 3).
 *
 *   GET  /api/julia/leads?…filters…&page&page_size → {data:{items,total}}
 *   POST /api/julia/leads/{id}/enviar   → {data:{status_envio,lead_id}} | 409 ja_enviado | 422 contato_sem_telefone
 *   POST /api/julia/leads/enviar-lote   {ids≤100} → {data:{ok:[],erro:[{id,code}]}}
 *   GET  /api/julia/leads/{id}/resumo
 *   GET  /api/julia/leads/export.csv    (admin) — blob download
 *
 * The list keeps `placeholderData: prev` across filter/page changes
 * (two-signal loading, never `isLoading`).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@noctusai/seed/infra";

import { api } from "@/lib/api";
import { apiUrl } from "@/lib/apiBase";
import { mensagemErroServidor } from "@/lib/erroServidor";

export type StatusEnvio = "enviado" | "nao_pronto" | "erro";
export type GatilhoEnvio = "qualificado" | "visita" | "frio" | "captacao" | "invalido" | "manual";
export interface LeadJulia {
  id: string;
  nome?: string | null;
  atendido_pela_julia?: boolean;
  telefone?: string | null;
  email?: string | null;
  operacao?: "compra" | "aluguel" | "administracao" | null;
  codigo_imovel?: string | null;
  canal?: string | null;
  primeiro_contato_em?: string | null;
  status_envio: StatusEnvio;
  gatilho?: GatilhoEnvio | null;
  lead_id?: string | null;
  erro?: string | null;
}
export interface FiltrosLeads {
  de: string;
  ate: string;
  nome: string;
  email: string;
  telefone: string;
  imovel: string;
  link: string;
  operacao: string[];
  atendimento: string[];
  status: string[];
  canal: string[];
  campanha: string;
  anuncio: string;
}
export const PAGE_SIZE = 20;

export function filtrosVazios(): FiltrosLeads {
  return {
    de: "", ate: "", nome: "", email: "", telefone: "", imovel: "", link: "",
    operacao: [], atendimento: [], status: [], canal: [], campanha: "", anuncio: "",
  };
}
export function contarFiltros(f: FiltrosLeads): number {
  return Object.values(f).filter((v) => (Array.isArray(v) ? v.length > 0 : v.trim() !== "")).length;
}
/** Serialises filters; arrays repeat the key; blanks are dropped. */
export function queryDeFiltros(f: FiltrosLeads, extra: Record<string, string | number> = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else if (v.trim() !== "") p.set(k, v.trim());
  }
  for (const [k, v] of Object.entries(extra)) p.set(k, String(v));
  return p.toString();
}

export const LEADS_KEY = ["sw", "julia", "leads"] as const;

const MENSAGENS: Record<string, string> = {
  ja_enviado: "Este lead já foi enviado ao SW.",
  contato_sem_telefone: "Este contato não tem telefone — não é possível enviar ao SW.",
};
export function codigoErro(err: unknown): string | undefined {
  const c = (err as { body?: { error?: { code?: unknown } } } | null)?.body?.error?.code;
  return typeof c === "string" ? c : undefined;
}
export function mensagemCodigoLead(code: string | undefined, fallback: string): string {
  return (code && MENSAGENS[code]) || fallback;
}
export function mensagemErroLeads(err: unknown, fallback: string): string {
  const c = codigoErro(err);
  return c && MENSAGENS[c] ? MENSAGENS[c] : mensagemErroServidor(err, fallback);
}

export function useLeadsJulia(filtros: FiltrosLeads, page: number) {
  return useQuery({
    queryKey: [...LEADS_KEY, "lista", filtros, page] as const,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const qs = queryDeFiltros(filtros, { page, page_size: PAGE_SIZE });
      const res = await api.get<{ data: { items: LeadJulia[]; total: number } }>(`/api/julia/leads?${qs}`);
      return { items: res.data?.items ?? [], total: res.data?.total ?? 0 };
    },
  });
}

export function useEnviarLead() {
  const qc = useQueryClient();
  return useMutation<{ status_envio: string; lead_id: string | null }, unknown, string>({
    mutationFn: async (id) =>
      (await api.post<{ data: { status_envio: string; lead_id: string | null } }>(`/api/julia/leads/${id}/enviar`, {})).data,
    // 409 means it was already sent elsewhere — refresh either way.
    onSettled: () => qc.invalidateQueries({ queryKey: LEADS_KEY }),
  });
}

export interface ResultadoLote { ok: string[]; erro: { id: string; code: string }[] }
export function useEnviarLote() {
  const qc = useQueryClient();
  return useMutation<ResultadoLote, unknown, string[]>({
    mutationFn: async (ids) =>
      (await api.post<{ data: ResultadoLote }>("/api/julia/leads/enviar-lote", { ids })).data,
    onSettled: () => qc.invalidateQueries({ queryKey: LEADS_KEY }),
  });
}

export interface ResumoLead {
  resumo?: string | null;
  slots?: Record<string, unknown> | null;
  intencoes?: string[] | null;
}
export function useResumoLead(id: string | null) {
  return useQuery({
    queryKey: [...LEADS_KEY, "resumo", id] as const,
    enabled: !!id,
    queryFn: async () => (await api.get<{ data: ResumoLead }>(`/api/julia/leads/${id}/resumo`)).data,
  });
}

/** Admin CSV export — blob download (the seed `api` client is JSON-only). */
export async function baixarLeadsCsv(filtros: FiltrosLeads, ids?: string[]): Promise<void> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const qs = queryDeFiltros(filtros, ids?.length ? { ids: ids.join(",") } : {});
  const resp = await fetch(apiUrl(`/api/julia/leads/export.csv${qs ? `?${qs}` : ""}`), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Falha ao exportar os leads (HTTP ${resp.status})`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "leads-julia.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


export interface CanalOrigem { slug: string; label: string }

/** The org's real lead origins (SW lead_sources + Lais origin codes + stored canais) — GET /api/julia/leads/canais. */
export function useJuliaCanais() {
  return useQuery({
    queryKey: ["julia", "leads", "canais"],
    queryFn: async () => ((await api.get("/api/julia/leads/canais")).data ?? []) as CanalOrigem[],
    staleTime: 5 * 60_000,
  });
}
