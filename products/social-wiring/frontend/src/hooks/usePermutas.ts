/**
 * Permutas — property swapping, matched by the shared engine (migration 101).
 *
 * Two resources behind one prefix:
 *
 *   /api/permutas           the registry — who is open to a swap and what for
 *   /api/permutas/matches   the scored pairs the engine produced
 *
 * 🔴 `sem_semantica` IS NOT A DIAGNOSTIC, IT IS PART OF THE ANSWER.
 * A run with no embeddings still returns a full list of plausible matches —
 * scored on rules alone, which cannot read the free text where this corpus
 * keeps its real constraints ("casa sem escada", "quintal amplo", "permuta de
 * 30% a 50%"). erp shipped exactly that state for months without noticing,
 * because a rule-only score looks completely normal. The page surfaces the
 * count so "the AI half did not run" is visible rather than inferred.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

/** 'imovel' — a catalog listing whose owner accepts a swap.
 *  'permuta_imovel' — a property brought AS swap currency.
 *  Both are matchable, and a listing is frequently both at once: 77 of the 82
 *  legacy matches paired two listings with each other. */
export type Natureza = "imovel" | "permuta_imovel" | "permuta_automovel";

export type Etapa =
  | "sugerido"
  | "avaliacao"
  | "negociacao"
  | "fechado"
  | "rejeitado";

/** `sugerido` is the engine's; everything else is a human decision, and a
 *  re-run may only rewrite rows still at `sugerido`. */
export const ETAPAS: Etapa[] = [
  "sugerido",
  "avaliacao",
  "negociacao",
  "fechado",
  "rejeitado",
];

export const ETAPA_LABELS: Record<Etapa, string> = {
  sugerido: "Sugerido",
  avaliacao: "Em avaliação",
  negociacao: "Em negociação",
  fechado: "Fechado",
  rejeitado: "Descartado",
};

export interface PermutaInteresse {
  id: string;
  tipo: string;
  tipo_imovel: string | null;
  zona: string | null;
  cidade: string | null;
  bairro: string | null;
  valor_minimo: number | null;
  valor_maximo: number | null;
  /** The proportion of the deal the swap should cover — "estuda permuta de
   *  30% a 50%" is the most common note in this data and the legacy schema
   *  had nowhere to put it. */
  percentual_min: number | null;
  percentual_max: number | null;
  observacoes: string | null;
}

export interface PermutaAtivo {
  id: string;
  natureza: Natureza;
  imovel_codigo: string | null;
  codigo: string | null;
  corretor_id: string | null;
  proprietario_nome: string | null;
  proprietario_telefone: string | null;
  tipo_imovel: string | null;
  cidade: string | null;
  bairro: string | null;
  uf: string | null;
  zona: string | null;
  valor: number | null;
  observacoes: string | null;
  status: string;
  origem: string;
  /** Never the vectors themselves — 1536 floats each, and nothing plots them. */
  tem_embedding: boolean;
  tem_embedding_interesses: boolean;
  interesses: PermutaInteresse[];
}

/** The display summary both sides of a match resolve to. Catalog data wins
 *  over the intent row's copies — `imoveis` is the synced source of truth. */
export interface AtivoResumo {
  id: string;
  natureza: Natureza;
  imovel_codigo: string | null;
  codigo: string | null;
  titulo?: string | null;
  tipo_imovel: string | null;
  cidade: string | null;
  bairro: string | null;
  uf: string | null;
  valor: number | null;
  quartos: number | null;
  vagas: number | null;
  area_total: number | null;
  condominio_nome: string | null;
  observacoes: string | null;
  proprietario_nome: string | null;
  foto?: string | null;
  corretores?: { nome?: string; email?: string; codigo?: string }[];
}

export interface PermutaMatch {
  id: string;
  ativo_origem_id: string;
  ativo_destino_id: string;
  score: number;
  justificativa: string;
  detalhes: {
    compatibilidade_regiao?: number;
    compatibilidade_preco?: number;
    compatibilidade_specs?: number;
    alinhamento_interesses?: number;
    qualidade_anuncio?: number;
    gap_valor?: number;
    embedding_similarity?: number;
    /** False means this pair was scored on rules alone. */
    semantica_disponivel?: boolean;
  };
  score_breakdown: Record<string, number>;
  is_bilateral: boolean;
  etapa: Etapa;
  observacoes: string;
  origem: "motor" | "permutas_legacy" | "manual";
  created_at: string;
  decidido_em: string | null;
  ativo_origem: AtivoResumo | null;
  ativo_destino: AtivoResumo | null;
}

export interface GerarResultado {
  encontrados: number;
  gravados: number;
  protegidos: number;
  imoveis_avaliados: number;
  permutas_avaliadas: number;
  /** Pairs scored without embeddings — see the file header. */
  sem_semantica: number;
  /** Intents whose catalog listing has been de-listed and so cannot match.
   *  Reported because dropping them silently reads as "no matches". */
  imoveis_nao_resolvidos: string[];
}

export interface EmbutirResultado {
  processados: number;
  pendentes: number;
  sem_texto: number;
  nao_resolvidos: number;
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const BASE = "/api/permutas";

const ATIVOS_KEY = (natureza?: Natureza) =>
  ["sw", "permutas", "ativos", { natureza: natureza ?? null }] as const;
const MATCHES_KEY = (etapa?: Etapa) =>
  ["sw", "permutas", "matches", { etapa: etapa ?? null }] as const;

// ─── Queries ────────────────────────────────────────────────────────────────

export function usePermutaAtivos(natureza?: Natureza) {
  return useQuery({
    queryKey: ATIVOS_KEY(natureza),
    queryFn: async () => {
      const qs = natureza ? `?natureza=${encodeURIComponent(natureza)}` : "";
      const res = await api.get<{ items: PermutaAtivo[]; total: number }>(
        `${BASE}${qs}`,
      );
      return res.items ?? [];
    },
    // The list is keyed on `natureza`, so switching the filter changes the key
    // and would otherwise flash an empty list over data that is about to
    // arrive. → KB § PATTERNS/frontend/lying-loading-state.md
    placeholderData: (prev) => prev,
  });
}

export function usePermutaMatches(etapa?: Etapa) {
  return useQuery({
    queryKey: MATCHES_KEY(etapa),
    queryFn: async () => {
      const qs = etapa ? `?etapa=${encodeURIComponent(etapa)}` : "";
      const res = await api.get<{ items: PermutaMatch[]; total: number }>(
        `${BASE}/matches${qs}`,
      );
      return res.items ?? [];
    },
    placeholderData: (prev) => prev,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** Invalidate every permutas query — a run touches matches, and moving a
 *  match's stage changes which stage-filtered lists it belongs to. */
function invalidarTudo(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["sw", "permutas"] });
}

export function useGerarMatches() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { ativo_id?: string; score_minimo?: number } = {}) =>
      api.post<GerarResultado>(`${BASE}/gerar`, body),
    onSuccess: () => invalidarTudo(qc),
  });
}

export function useGerarEmbeddings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { apenas_pendentes?: boolean } = {}) =>
      api.post<EmbutirResultado>(`${BASE}/embeddings`, body),
    onSuccess: () => invalidarTudo(qc),
  });
}

export function useMoverEtapa() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      matchId,
      etapa,
      observacoes,
    }: {
      matchId: string;
      etapa: Etapa;
      observacoes?: string;
    }) =>
      api.patch<PermutaMatch>(`${BASE}/matches/${matchId}`, {
        etapa,
        ...(observacoes !== undefined ? { observacoes } : {}),
      }),
    onSuccess: () => invalidarTudo(qc),
  });
}
