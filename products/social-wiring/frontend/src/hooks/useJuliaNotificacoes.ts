/**
 * Julia › Notificações (contract wave 6).
 *
 *   GET  /api/julia/notificacoes?tipo&operacao&de&ate&page → {data:{items,total,nao_lidas}}
 *   POST /api/julia/notificacoes/lidas {ids|todas}         → 204
 *   GET /api/julia/notificacoes/preferencias → {data:{tipos:[{tipo,in_app}], lead_pronto}}
 *   PUT /api/julia/notificacoes/preferencias {tipos:{<tipo>: bool}} → same as GET
 *       (the "Notificar lead pronto para atendimento" toggle is the pseudo-tipo `lead_pronto`)
 *
 * Loading = two signals off `data` (never `isLoading`); the feed is keyed by
 * filters+page so it keeps `placeholderData: prev` while they change. The
 * header bell (seed `notifications.ts`) counts the same `julia_*` rows, so
 * marking read also invalidates its keys.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";

export const TIPOS_NOTIFICACAO = [
  { value: "pre_agendamento_visita", label: "Solicitação de pré-agendamento de visita", categoria: "VISITAS" },
  { value: "cobranca_atendimento", label: "Cobrança de atendimento", categoria: "ATENDIMENTO" },
  { value: "relatorio", label: "Relatórios da Julia", categoria: "RELATÓRIOS" },
  { value: "remarketing", label: "Remarketing", categoria: "COMERCIAL" },
  { value: "captacao", label: "Captação", categoria: "CAPTAÇÃO" },
  { value: "atualizacao_base_imoveis", label: "Atualização de base de imóveis", categoria: "IMÓVEIS" },
  { value: "novo_lead", label: "Novo lead gerado", categoria: "COMERCIAL" },
  { value: "novo_atendimento", label: "Novo atendimento", categoria: "ATENDIMENTO" },
  { value: "nova_mensagem", label: "Nova mensagem", categoria: "ATENDIMENTO" },
  { value: "avaliacao_google", label: "Avaliações no Google", categoria: "REPUTAÇÃO" },
  { value: "handoff", label: "Transferência para atendimento humano", categoria: "ATENDIMENTO" },
] as const;

export type TipoNotificacao = (typeof TIPOS_NOTIFICACAO)[number]["value"];
export type OperacaoFiltro = "" | "aluguel" | "compra";

export const PAGE_SIZE = 20;

export interface JuliaNotificacao {
  id: string;
  tipo: string;
  titulo?: string | null;
  mensagem?: string | null;
  is_read: boolean;
  link?: string | null;
  created_at: string;
}
export interface NotificacoesPage { items: JuliaNotificacao[]; total: number; nao_lidas: number }
export interface NotificacoesFiltro { tipo: string; operacao: OperacaoFiltro; de: string; ate: string; page: number }
export const FILTRO_VAZIO: NotificacoesFiltro = { tipo: "", operacao: "", de: "", ate: "", page: 1 };
export interface PreferenciaNotificacao { tipo: string; in_app: boolean }
export interface PreferenciasNotificacao { tipos: PreferenciaNotificacao[]; lead_pronto: boolean }

export function metaTipo(tipo: string) {
  const m = TIPOS_NOTIFICACAO.find((t) => t.value === tipo);
  return { label: m?.label ?? tipo, categoria: m?.categoria ?? "GERAL" };
}

const KEY = ["julia", "notificacoes"] as const;

export function useJuliaNotificacoes(f: NotificacoesFiltro) {
  return useQuery({
    queryKey: [...KEY, f],
    queryFn: async () => {
      const p = new URLSearchParams({ page: String(f.page) });
      if (f.tipo) p.set("tipo", f.tipo);
      if (f.operacao) p.set("operacao", f.operacao);
      if (f.de) p.set("de", f.de);
      if (f.ate) p.set("ate", f.ate);
      const r = await api.get(`/api/julia/notificacoes?${p}`);
      return (r.data ?? { items: [], total: 0, nao_lidas: 0 }) as NotificacoesPage;
    },
    placeholderData: keepPreviousData,
  });
}

export function useMarcarLidas() {
  return useCacheWriteMutation<unknown, { ids: string[] } | { todas: true }>({
    mutationFn: (body) => api.post("/api/julia/notificacoes/lidas", body),
    // Read state is drawn at once on every cached page (the preferences entry has no `items` and passes through);
    // the bell badge / counters are other families and settle.
    targets: [
      {
        queryKey: KEY,
        match: "prefix",
        optimistic: (old: NotificacoesPage | undefined, vars) => {
          if (!old?.items) return old;
          const todas = "todas" in vars;
          const ids = "ids" in vars ? new Set(vars.ids) : new Set<string>();
          const agora = old.items.filter((n) => !n.is_read && (todas || ids.has(n.id))).length;
          return {
            ...old,
            items: old.items.map((n) => (todas || ids.has(n.id) ? { ...n, is_read: true } : n)),
            nao_lidas: todas ? 0 : Math.max(0, old.nao_lidas - agora),
          };
        },
      },
    ],
    invalidate: [["notificacoes"], ["notificacoes-contagem"]],
  });
}

export function usePreferenciasNotificacao() {
  return useQuery({
    queryKey: [...KEY, "preferencias"],
    queryFn: async () =>
      ((await api.get("/api/julia/notificacoes/preferencias")).data ?? { tipos: [], lead_pronto: true }) as PreferenciasNotificacao,
    placeholderData: keepPreviousData,
  });
}

export function useSalvarPreferencias() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (tipos: Record<string, boolean>) =>
      (await api.put("/api/julia/notificacoes/preferencias", { tipos })).data as PreferenciasNotificacao,
    onSuccess: (data) => qc.setQueryData([...KEY, "preferencias"], data),
  });
}
