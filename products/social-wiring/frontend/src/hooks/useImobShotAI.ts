/**
 * ImobShotAI hooks -- TanStack Query over `/api/imobshotai/*` (`products/social-wiring/IMOBSHOTAI-CONTRACT.md`
 * v1, photo side). The photo work itself (upload, Vista pull, submit, review) stays on the existing Edição de
 * Fotos hooks (`@/hooks/useEdicaoFotos`); this file adds the CARD layer on top.
 *
 * Contract facts these hooks rely on:
 *  - lists are `page_out` (`{items, page, page_size, total}`); a single object comes back bare.
 *  - the card `etapa` is a SERVER PROJECTION (contract §6): it is never set by hand, so a decision or a submit
 *    cannot place it optimistically -- those writes hand off to polling (`handOffToPolling`) instead.
 *  - `POST /lotes` answers `{card, lote}`: the card is committed into every board list it belongs on.
 *
 * Loading-state contract: every read returns `showSkeleton = isPending && !data` / `isRefreshing = isFetching &&
 * !!data` (never `isLoading`), with `placeholderData: (prev) => prev` on the filtered board.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { handOffToPolling, jobPolling } from "@noctusai/lib";
import {
  useSubmeterLote,
  type EstadoFoto,
  type LoteDetalhe,
  type LoteResumo,
  type LoteVelocidade,
} from "@/hooks/useEdicaoFotos";

// ─── Contract types (§3, §4, §6) ───────────────────────────────────────────

export type Etapa =
  | "fotos_enviadas"
  | "fotos_em_edicao"
  | "fotos_em_revisao"
  | "fotos_aprovadas"
  | "video_em_montagem"
  | "video_renderizando"
  | "video_em_revisao"
  | "concluido"
  | "arquivado";

/** The only etapas a card can reach in v1 (contract §6) -- the board's columns, in order. */
export const ETAPAS_FOTO: readonly Etapa[] = [
  "fotos_enviadas",
  "fotos_em_edicao",
  "fotos_em_revisao",
  "fotos_aprovadas",
] as const;

export const ETAPA_LABEL: Record<Etapa, string> = {
  fotos_enviadas: "Fotos enviadas",
  fotos_em_edicao: "Em edição",
  fotos_em_revisao: "Em revisão",
  fotos_aprovadas: "Fotos aprovadas",
  video_em_montagem: "Vídeo em montagem",
  video_renderizando: "Renderizando vídeo",
  video_em_revisao: "Vídeo em revisão",
  concluido: "Concluído",
  arquivado: "Arquivado",
};

export type EventoTipo = "card_criado" | "lote_vinculado" | "etapa_mudou" | "card_arquivado";

export interface CardResumo {
  id: string;
  imovel: { org_id: string; codigo: string; titulo: string | null; bairro: string | null };
  etapa: Etapa;
  /** ISO -- when the card entered `etapa`. */
  etapa_desde: string;
  /** Signed URL of the cover (best approved photo); null until one exists. */
  capa_url: string | null;
  total_fotos: number;
  fotos_aprovadas: number;
  /** 0 in v1. */
  total_videos: number;
  criado_em: string;
  atualizado_em: string;
}

export interface CardFoto {
  id: string;
  lote_id: string;
  /** Room label when known (S5 fills it); null in v1. */
  comodo: string | null;
  /** `fotos_fotos.status` verbatim. */
  status: string;
  original_url: string;
  editada_url: string | null;
}

export interface CardEvento {
  tipo: EventoTipo;
  etapa_de: Etapa | null;
  etapa_para: Etapa | null;
  ator_id: string | null;
  em: string;
  detalhe: Record<string, unknown>;
}

export interface CardDetalhe extends CardResumo {
  /** Newest first. */
  lotes: LoteResumo[];
  fotos: CardFoto[];
  /** v1: always empty. */
  videos: [];
  /** Newest first, at most 50. */
  eventos: CardEvento[];
}

export interface CardsPage {
  items: CardResumo[];
  page: number;
  page_size: number;
  total: number;
}

export interface IniciarLoteBody {
  imovel_codigo: string;
  nome?: string;
  velocidade?: LoteVelocidade;
}

export interface IniciarLoteResposta {
  card: CardResumo;
  lote: LoteResumo;
}

export interface CardsFiltro {
  etapa?: Etapa;
  /** Prefix of `imovel_codigo` (case-insensitive). */
  q?: string;
  page?: number;
  pageSize?: number;
}

// ─── Keys ──────────────────────────────────────────────────────────────────

const ROOT = ["imobshotai"] as const;

export const imobKeys = {
  all: ROOT,
  cards: () => [...ROOT, "cards"] as const,
  lists: () => [...ROOT, "cards", "list"] as const,
  list: (f: CardsFiltro) => [...ROOT, "cards", "list", normalizaFiltro(f)] as const,
  detail: (cardId: string | null | undefined) => [...ROOT, "cards", "detail", cardId] as const,
};

function normalizaFiltro(f: CardsFiltro) {
  return {
    etapa: f.etapa ?? null,
    q: (f.q ?? "").trim().toUpperCase(),
    page: f.page ?? 1,
    pageSize: f.pageSize ?? 50,
  };
}

const LOTES_KEY = ["edicao-fotos", "lotes"] as const;
const LOTE_KEY = (loteId: string | null | undefined) => ["edicao-fotos", "lote", loteId] as const;

// ─── Reads ─────────────────────────────────────────────────────────────────

const POLL_BOARD_MS = 15_000;
const POLL_LOTE_MS = 4_000;

/** `GET /cards` -- the board. Polls while any card is being edited (its stage moves without a click). */
export function useImobCards(filtro: CardsFiltro = {}) {
  const f = normalizaFiltro(filtro);
  const query = useQuery<CardsPage>({
    queryKey: imobKeys.list(filtro),
    queryFn: () =>
      api.get<CardsPage>("/api/imobshotai/cards", {
        ...(f.etapa ? { etapa: f.etapa } : {}),
        ...(f.q ? { q: f.q } : {}),
        page: f.page,
        page_size: f.pageSize,
      }),
    placeholderData: (prev) => prev,
    ...jobPolling<CardsPage>((data) => !!data?.items.some((c) => c.etapa === "fotos_em_edicao"), POLL_BOARD_MS),
  });
  return {
    cards: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    error: query.error,
    refetch: query.refetch,
  };
}

/** `GET /cards/{id}` -- the card detail. A `404 card_nao_encontrado` lands in `error` (code on the ApiError). */
export function useImobCard(cardId: string | null | undefined) {
  const query = useQuery<CardDetalhe>({
    queryKey: imobKeys.detail(cardId),
    queryFn: () => api.get<CardDetalhe>(`/api/imobshotai/cards/${cardId}`),
    enabled: !!cardId,
    placeholderData: (prev) => prev,
  });
  return {
    card: query.data,
    showSkeleton: query.isPending && !query.data && query.fetchStatus !== "idle",
    isRefreshing: query.isFetching && !!query.data,
    error: query.error,
    refetch: query.refetch,
  };
}

/** Photo states a lote is still working through (polling continues while any photo is in one). */
const ESTADOS_EM_ANDAMENTO: EstadoFoto[] = [
  "recebida",
  "normalizando",
  "pronta",
  "editando",
  "em_lote_openai",
  "editada",
  "avaliando",
];

/**
 * `GET /api/edicao-fotos/lotes/{id}` polled while the lote is being edited (funnel step 4). Same cache entry as
 * `useLote`, so the review step reads what this polled. SSE comes later (contract §8).
 */
export function useImobLoteProgresso(loteId: string | null | undefined, options: { enabled?: boolean } = {}) {
  const { enabled = true } = options;
  const query = useQuery<LoteDetalhe>({
    queryKey: LOTE_KEY(loteId),
    queryFn: () => api.get<LoteDetalhe>(`/api/edicao-fotos/lotes/${loteId}`),
    enabled: enabled && !!loteId,
    placeholderData: (prev) => prev,
    ...jobPolling<LoteDetalhe>((data) => !!data?.fotos.some((f) => ESTADOS_EM_ANDAMENTO.includes(f.estado)), POLL_LOTE_MS),
  });
  const fotos = query.data?.fotos ?? [];
  return {
    lote: query.data,
    totalFotos: fotos.length,
    emAndamento: fotos.filter((f) => ESTADOS_EM_ANDAMENTO.includes(f.estado)).length,
    showSkeleton: enabled && query.isPending && !query.data,
    error: query.error,
    refetch: query.refetch,
  };
}

// ─── Writes ────────────────────────────────────────────────────────────────

/**
 * `POST /lotes` (funnel step 1). The answer carries the card AND the lote: the card goes first on page 1 of every
 * unfiltered board list it belongs on, the lote first on page 1 of the batch lists. The detail is not seeded (it
 * needs the photos) -- it refetches on settle.
 */
export function useIniciarImobLote() {
  return useCacheWriteMutation<IniciarLoteResposta, IniciarLoteBody>({
    mutationFn: (body) => api.post<IniciarLoteResposta>("/api/imobshotai/lotes", body),
    targets: [
      {
        queryKey: imobKeys.lists(),
        match: "prefix",
        predicate: (key) => {
          const f = key[key.length - 1] as { etapa: Etapa | null; q: string; page: number };
          return !f.q && f.page === 1;
        },
        commit: (old, res, _vars, _ctx, queryKey) => {
          // A list filtered to another etapa does not hold this card.
          const f = queryKey?.[queryKey.length - 1] as { etapa: Etapa | null } | undefined;
          if (f?.etapa && f.etapa !== res.card.etapa) return old;
          return pageOps.prependNewest(old, res.card);
        },
      },
      { queryKey: LOTES_KEY, match: "prefix", commit: (old, res) => pageOps.prependNewest(old, res.lote) },
    ],
    invalidate: [imobKeys.cards()],
  });
}

/**
 * Submit a lote for editing (funnel step 4). The seed hook already writes the lote summary into the batch lists;
 * the card's stage is a server projection, so this hands the board and the card detail off to polling until it moves.
 */
export function useSubmeterLoteImob() {
  const qc = useQueryClient();
  const base = useSubmeterLote();
  const mutateAsync = async (loteId: string) => {
    const resumo = await base.mutateAsync(loteId);
    void handOffToPolling(qc, imobKeys.cards(), { until: "changed" });
    return resumo;
  };
  return { ...base, mutateAsync };
}

/** Re-reads the cards after a photo decision/retry (the etapa is derived server-side). */
export function useRefrescarCards() {
  const qc = useQueryClient();
  return () => void handOffToPolling(qc, imobKeys.cards(), { until: "changed" });
}
