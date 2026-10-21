/**
 * Condomínios — the master list (migration 265). Built from Vista
 * `empreendimento` spellings, validated by the owner on /condominios.
 *
 *   GET    /api/condominios              list + stats
 *   GET    /api/condominios/{id}         one + aliases + audit events
 *   POST   /api/condominios/sugerir      admin: (re)build suggestions
 *   PATCH  /api/condominios/{id}         attributes (any member)
 *   POST   /api/condominios/{id}/{validar|descartar|reabrir|desfazer-fusao|renomear|fundir|aliases}
 *   DELETE /api/condominios/{id}/aliases/{aliasId}
 *   GET    /api/condominios/buscar?q=     imóvel-page picker (migration 300)
 *   POST   /api/condominios               create from the picker (deduped by name)
 *
 * Admin-only actions are 403 on the server (TRUSTED role row); the page only
 * hides the buttons.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

export type StatusValidacao = "sugerido" | "validado" | "descartado";
export type TipoCondominio = "horizontal" | "vertical" | "loteamento" | "misto";

export const STATUS_LABELS: Record<StatusValidacao, string> = {
  sugerido: "Sugerido",
  validado: "Validado",
  descartado: "Descartado",
};

export const TIPO_LABELS: Record<TipoCondominio, string> = {
  horizontal: "Horizontal",
  vertical: "Vertical",
  loteamento: "Loteamento",
  misto: "Misto",
};

export interface Condominio {
  id: string;
  nome: string;
  nome_normalizado: string;
  cidade: string | null;
  bairro: string | null;
  tipo: TipoCondominio | null;
  status_validacao: StatusValidacao;
  latitude: number | null;
  longitude: number | null;
  seguranca_nivel: number | null;
  portaria_24h: boolean | null;
  area_lazer: string | null;
  distancia_raposo_km: number | null;
  acesso_principal: string | null;
  observacoes: string | null;
  fundido_em_id: string | null;
  validado_em: string | null;
  imoveis_count: number;
  anuncios_venda_count: number;
  preco_m2_mediano: number | null;
  aliases_count: number;
}

export interface CondominioAlias {
  id: string;
  alias: string;
  alias_normalizado: string;
  origem: "sugestao" | "manual" | "fusao";
  imoveis_count: number;
}

export interface CondominioEvento {
  id: string;
  tipo: string;
  ator: string | null;
  detalhes: Record<string, unknown>;
  created_at: string;
}

export interface CondominioDetalhe extends Condominio {
  aliases: CondominioAlias[];
  eventos: CondominioEvento[];
}

export interface SugestaoResultado {
  empreendimentos_distintos: number;
  aliases_novos: number;
  condominios_criados: number;
  aliases_em_existentes: number;
}

/** `CondominioPatchBody` — the server forbids unknown keys. */
export interface CondominioPayload {
  cidade?: string | null;
  bairro?: string | null;
  tipo?: TipoCondominio | null;
  seguranca_nivel?: number | null;
  portaria_24h?: boolean | null;
  area_lazer?: string | null;
  distancia_raposo_km?: number | null;
  acesso_principal?: string | null;
  observacoes?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface CondominioFiltros {
  status?: StatusValidacao | "";
  cidade?: string;
  q?: string;
}

const BASE = "/api/condominios";
const ROOT = ["sw", "condominios"] as const;

// ─── Imóvel-page picker (migration 300) ─────────────────────────────────────

/** What an imóvel carries about its attached condomínio (`dados.condominio`,
 *  `Imovel.condominio`) and what the picker search returns per item. */
export interface CondominioResumo {
  id: string;
  nome: string;
  cidade: string | null;
  bairro: string | null;
  status_validacao: StatusValidacao;
}

/** `POST /api/condominios` — `criado: false` when a same-name one existed
 *  (the server returns it instead of forking a duplicate). */
export interface CondominioCriado extends CondominioResumo {
  criado: boolean;
}

export interface CondominioNovo {
  nome: string;
  cidade?: string | null;
  bairro?: string | null;
}

export const buscaCondominiosKey = (q: string) => [...ROOT, "busca", q.trim()] as const;

/** Search-as-you-type. `q` is expected already debounced by the caller.
 *  Keeps the previous term's items on screen while the next loads
 *  (lying-loading-state: `isPending && !data` is the only skeleton). */
export function useCondominioBusca(q: string) {
  const termo = q.trim();
  return useQuery({
    queryKey: buscaCondominiosKey(termo),
    queryFn: async () => {
      const res = await api.get<{ items: CondominioResumo[]; total: number }>(
        `${BASE}/buscar?q=${encodeURIComponent(termo)}`,
      );
      return res.items ?? [];
    },
    enabled: termo.length > 0,
    placeholderData: (prev) => prev,
  });
}

/** "Cadastrar condomínio “<texto>”". The server's answer is written straight
 *  into the search cache of the typed term (the dropdown shows it at once);
 *  the master list refreshes in the background. */
export function useCriarCondominio() {
  return useCacheWriteMutation<CondominioCriado, CondominioNovo>({
    mutationFn: (body) => api.post<CondominioCriado>(BASE, body),
    targets: (vars) => [
      {
        queryKey: buscaCondominiosKey(vars.nome),
        commit: (old: CondominioResumo[] | undefined, criado: CondominioCriado) => {
          const resumo: CondominioResumo = {
            id: criado.id,
            nome: criado.nome,
            cidade: criado.cidade,
            bairro: criado.bairro,
            status_validacao: criado.status_validacao,
          };
          return [resumo, ...(old ?? []).filter((c) => c.id !== resumo.id)];
        },
      },
    ],
    invalidate: [[...ROOT, "lista"]],
  });
}

export function useCondominios(filtros: CondominioFiltros = {}) {
  const status = filtros.status || null;
  const cidade = filtros.cidade || null;
  const q = filtros.q?.trim() || null;
  return useQuery({
    queryKey: [...ROOT, "lista", { status, cidade, q }],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (cidade) params.set("cidade", cidade);
      if (q) params.set("q", q);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const res = await api.get<{ items: Condominio[]; total: number }>(`${BASE}${qs}`);
      return res.items ?? [];
    },
    // Filter changes swap the key; keep the rows on screen while the next
    // set loads. → KB § PATTERNS/frontend/lying-loading-state.md
    placeholderData: (prev) => prev,
  });
}

export function useCondominio(id: string | null) {
  return useQuery({
    queryKey: [...ROOT, "detalhe", id],
    queryFn: () => api.get<CondominioDetalhe>(`${BASE}/${id}`),
    enabled: !!id,
  });
}

const LISTAS_KEY = [...ROOT, "lista"] as const;
const detalheKey = (id: string) => [...ROOT, "detalhe", id] as const;

/** A saved `Condominio` row: patched into every cached list and merged into its detail. */
const rowTargets = (id: string) => [
  {
    queryKey: LISTAS_KEY,
    match: "prefix" as const,
    commit: (old: Condominio[] | undefined, saved: Condominio) => listOps.patch(old, id, saved),
  },
  {
    queryKey: detalheKey(id),
    commit: (old: CondominioDetalhe | undefined, saved: Condominio) => listOps.merge(old, saved),
  },
];

export function useSugerirCondominios() {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — rebuilds suggestions server-side; the answer is counts, the new rows are only known by refetching
    mutationFn: () => api.post<SugestaoResultado>(`${BASE}/sugerir`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }),
  });
}

export function useAtualizarCondominio() {
  return useCacheWriteMutation<Condominio, { id: string; body: CondominioPayload }>({
    mutationFn: ({ id, body }) => api.patch<Condominio>(`${BASE}/${id}`, body),
    targets: ({ id }) => rowTargets(id),
    invalidate: [ROOT],
  });
}

export type AcaoStatus = "validar" | "descartar" | "reabrir" | "desfazer-fusao";

export function useAcaoCondominio() {
  return useCacheWriteMutation<Condominio, { id: string; acao: AcaoStatus }>({
    mutationFn: ({ id, acao }) => api.post<Condominio>(`${BASE}/${id}/${acao}`, {}),
    targets: ({ id }) => rowTargets(id),
    invalidate: [ROOT],
  });
}

export function useRenomearCondominio() {
  return useCacheWriteMutation<Condominio, { id: string; nome: string }>({
    mutationFn: ({ id, nome }) => api.post<Condominio>(`${BASE}/${id}/renomear`, { nome }),
    targets: ({ id }) => [
      {
        ...rowTargets(id)[0],
        optimistic: (old: Condominio[] | undefined, vars: { id: string; nome: string }) =>
          listOps.patch(old, vars.id, { nome: vars.nome }),
      },
      rowTargets(id)[1],
    ],
    invalidate: [ROOT],
  });
}

export function useFundirCondominio() {
  return useCacheWriteMutation<{ aliases_movidos: number }, { id: string; destinoId: string }>({
    mutationFn: ({ id, destinoId }) =>
      api.post<{ aliases_movidos: number }>(`${BASE}/${id}/fundir`, { destino_id: destinoId }),
    // The merged-away condomínio leaves the lists; the destination's aliases/counts settle.
    targets: ({ id }) => [
      {
        queryKey: LISTAS_KEY,
        match: "prefix",
        commit: (old: Condominio[] | undefined) => listOps.remove(old, id),
      },
    ],
    invalidate: [ROOT],
  });
}

export function useAdicionarAlias() {
  return useCacheWriteMutation<CondominioAlias, { id: string; alias: string }>({
    mutationFn: ({ id, alias }) => api.post<CondominioAlias>(`${BASE}/${id}/aliases`, { alias }),
    targets: ({ id }) => [
      {
        queryKey: detalheKey(id),
        commit: (old: CondominioDetalhe | undefined, saved) =>
          listOps.within(old, "aliases", (l) => listOps.replace(l, saved.id, saved)),
      },
    ],
    invalidate: [ROOT],
  });
}

export function useRemoverAlias() {
  return useCacheWriteMutation<unknown, { id: string; aliasId: string }>({
    mutationFn: ({ id, aliasId }) => api.delete<unknown>(`${BASE}/${id}/aliases/${aliasId}`),
    targets: ({ id, aliasId }) => [
      {
        queryKey: detalheKey(id),
        optimistic: (old: CondominioDetalhe | undefined) =>
          listOps.within(old, "aliases", (l) => listOps.remove(l, aliasId)),
      },
    ],
    invalidate: [ROOT],
  });
}
