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

export const NATUREZA_LABELS: Record<Natureza, string> = {
  imovel: "Imóvel do catálogo",
  permuta_imovel: "Imóvel oferecido em permuta",
  permuta_automovel: "Automóvel oferecido em permuta",
};

/** The DB CHECK on `permuta_ativos.status` (migration 101). Only `ativo`
 *  rows are listed by default and only `ativo` rows feed the engine. */
export type StatusAtivo = "ativo" | "pausado" | "concluido" | "arquivado";

export const STATUS_ATIVO_LABELS: Record<StatusAtivo, string> = {
  ativo: "Ativo",
  pausado: "Pausado",
  concluido: "Concluído",
  arquivado: "Arquivado",
};

export interface PermutaAtivo {
  id: string;
  natureza: Natureza;
  imovel_codigo: string | null;
  codigo: string | null;
  corretor_id: string | null;
  proprietario_nome: string | null;
  proprietario_telefone: string | null;
  proprietario_email?: string | null;
  tipo_imovel: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  cidade: string | null;
  bairro: string | null;
  uf: string | null;
  zona: string | null;
  condominio_nome?: string | null;
  valor: number | null;
  area_total?: number | null;
  area_privativa?: number | null;
  quartos?: number | null;
  suites?: number | null;
  vagas?: number | null;
  faixa_preco_min?: number | null;
  faixa_preco_max?: number | null;
  regiao_preferida?: string[] | null;
  aceita_completar_diferenca?: boolean | null;
  limite_complemento?: number | null;
  percentual_min?: number | null;
  percentual_max?: number | null;
  /** The free text the semantic matching embeds as "what this ativo wants"
   *  (`adapter.texto_interesses_para_embedding` leads with it). */
  observacoes: string | null;
  /** DERIVED, read-only: the text last sent to the embedding model. Not
   *  accepted by the create/patch body (`StrictHttpModel` would 422 it). */
  interesses_descricao?: string | null;
  status: string;
  origem: string;
  /** Never the vectors themselves — 1536 floats each, and nothing plots them. */
  tem_embedding: boolean;
  tem_embedding_interesses: boolean;
  interesses: PermutaInteresse[];
  /** Registry list only: the catalog listing a natureza='imovel' row points
   *  at, kept OFF the row's own columns so an edit never writes catalog data
   *  back into the intent. `null` = código not (or no longer) in the
   *  catalog. Absent on an older backend. */
  catalogo?: {
    titulo: string | null;
    categoria: string | null;
    bairro: string | null;
    cidade: string | null;
    uf: string | null;
    valor_venda: number | null;
  } | null;
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

/** One accepted-in-exchange criterion — `InteresseBody` in schemas.py. */
export interface InteressePayload {
  tipo?: string;
  tipo_imovel?: string | null;
  zona?: string | null;
  cidade?: string | null;
  bairro?: string | null;
  valor_minimo?: number | null;
  valor_maximo?: number | null;
  percentual_min?: number | null;
  percentual_max?: number | null;
  marca?: string | null;
  modelo?: string | null;
  ano_min?: number | null;
  ano_max?: number | null;
  observacoes?: string | null;
}

/** `AtivoCreateBody` / `AtivoPatchBody` in schemas.py — the server forbids
 *  unknown keys, so this type is the whole contract. On a PATCH an omitted
 *  key is left alone, an explicit `null` clears it, and `interesses` (when
 *  present) REPLACES the set. */
export interface AtivoPayload {
  natureza?: Natureza;
  imovel_codigo?: string | null;
  codigo?: string | null;
  corretor_id?: string | null;
  proprietario_nome?: string | null;
  proprietario_telefone?: string | null;
  proprietario_email?: string | null;
  tipo_imovel?: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  uf?: string | null;
  zona?: string | null;
  condominio_nome?: string | null;
  valor?: number | null;
  area_total?: number | null;
  area_privativa?: number | null;
  quartos?: number | null;
  suites?: number | null;
  vagas?: number | null;
  faixa_preco_min?: number | null;
  faixa_preco_max?: number | null;
  regiao_preferida?: string[] | null;
  aceita_completar_diferenca?: boolean | null;
  limite_complemento?: number | null;
  percentual_min?: number | null;
  percentual_max?: number | null;
  observacoes?: string | null;
  status?: StatusAtivo | null;
  interesses?: InteressePayload[] | null;
}

// ─── Keys ───────────────────────────────────────────────────────────────────

const BASE = "/api/permutas";

const ATIVOS_KEY = (natureza?: Natureza, incluirInativos = false) =>
  [
    "sw",
    "permutas",
    "ativos",
    { natureza: natureza ?? null, incluirInativos },
  ] as const;
const MATCHES_KEY = (etapa?: Etapa) =>
  ["sw", "permutas", "matches", { etapa: etapa ?? null }] as const;

// ─── Queries ────────────────────────────────────────────────────────────────

export function usePermutaAtivos(
  natureza?: Natureza,
  opts: { incluirInativos?: boolean } = {},
) {
  const incluirInativos = opts.incluirInativos ?? false;
  return useQuery({
    queryKey: ATIVOS_KEY(natureza, incluirInativos),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (natureza) params.set("natureza", natureza);
      // The server lists only `status='ativo'` unless asked — a paused or
      // archived intent would otherwise be invisible AND uneditable.
      if (incluirInativos) params.set("incluir_inativos", "true");
      const qs = params.toString() ? `?${params.toString()}` : "";
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

// ─── Registry mutations ─────────────────────────────────────────────────────
//
// Every write invalidates ALL permutas queries, not just the registry list:
// a delete cascades to the ativo's matches (FK CASCADE), and an edit clears
// its vectors server-side (`atualizar_ativo`), which changes the "sem
// vetores" count on the embeddings button.

export function useCriarAtivo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AtivoPayload & { natureza: Natureza }) =>
      api.post<PermutaAtivo>(BASE, body),
    onSuccess: () => invalidarTudo(qc),
  });
}

export function useAtualizarAtivo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ativoId, body }: { ativoId: string; body: AtivoPayload }) =>
      api.patch<PermutaAtivo>(`${BASE}/${ativoId}`, body),
    onSuccess: () => invalidarTudo(qc),
  });
}

export function useRemoverAtivo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ativoId: string) => api.delete<void>(`${BASE}/${ativoId}`),
    onSuccess: () => invalidarTudo(qc),
  });
}
