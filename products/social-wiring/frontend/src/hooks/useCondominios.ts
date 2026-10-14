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
 *
 * Admin-only actions are 403 on the server (TRUSTED role row); the page only
 * hides the buttons.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

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

function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ROOT });
}

export function useSugerirCondominios() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: () => api.post<SugestaoResultado>(`${BASE}/sugerir`, {}),
    onSuccess: invalidar,
  });
}

export function useAtualizarCondominio() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CondominioPayload }) =>
      api.patch<Condominio>(`${BASE}/${id}`, body),
    onSuccess: invalidar,
  });
}

export type AcaoStatus = "validar" | "descartar" | "reabrir" | "desfazer-fusao";

export function useAcaoCondominio() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, acao }: { id: string; acao: AcaoStatus }) =>
      api.post<Condominio>(`${BASE}/${id}/${acao}`, {}),
    onSuccess: invalidar,
  });
}

export function useRenomearCondominio() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, nome }: { id: string; nome: string }) =>
      api.post<Condominio>(`${BASE}/${id}/renomear`, { nome }),
    onSuccess: invalidar,
  });
}

export function useFundirCondominio() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, destinoId }: { id: string; destinoId: string }) =>
      api.post<{ aliases_movidos: number }>(`${BASE}/${id}/fundir`, { destino_id: destinoId }),
    onSuccess: invalidar,
  });
}

export function useAdicionarAlias() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, alias }: { id: string; alias: string }) =>
      api.post<CondominioAlias>(`${BASE}/${id}/aliases`, { alias }),
    onSuccess: invalidar,
  });
}

export function useRemoverAlias() {
  const invalidar = useInvalidar();
  return useMutation({
    mutationFn: ({ id, aliasId }: { id: string; aliasId: string }) =>
      api.delete<unknown>(`${BASE}/${id}/aliases/${aliasId}`),
    onSuccess: invalidar,
  });
}
