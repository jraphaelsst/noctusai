/**
 * Review-queue hooks — TanStack Query wrappers over `/api/clientes/revisao`
 * + `/api/clientes/merges/{id}/desfazer`
 * (`products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §5).
 *
 * The backend for this contract is being built in a PARALLEL worktree and
 * does not exist on this branch — every shape below is built to §5, never
 * to observed behaviour.
 *
 * 🔴 Two assumptions, both called out because §5 leaves them genuinely open:
 *
 * 1. **Pagination shape.** §5's board row explicitly lists `pagination` as
 *    a query param; the revisao row does not — it just says "the ~311 C4–C6
 *    groups, each with its candidate rows and the reason code". A queue of
 *    ~311 items is unwalkable unpaginated (the roadmap's own checkpoint
 *    language — "the review queue is walkable"), so this hook REQUESTS
 *    `?page=&page_size=` regardless, and `normalizeRevisaoPage` accepts
 *    EITHER shape the backend might return: a paginated envelope
 *    (`{items,total,page,pages}`, matching `ClientesPage`/`ImovelPage`) OR
 *    a bare array (paginated client-side as a fallback so the UI still
 *    works if the backend ships the simpler shape first).
 * 2. **Merge survivor selection.** §5 lists exactly two operator actions —
 *    "merge" and "manter separados" — with no candidate-selection step.
 *    `merge()` therefore posts no body by default; the backend picks the
 *    survivor (presumably mirroring C3's "adopt the longest name" rule).
 *    `sobreviventeId` is accepted as an optional override in case the real
 *    endpoint wants it, but nothing in this slice requires the operator to
 *    choose — flag if the live contract needs an explicit survivor.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types ──────────────────────────────────────────────────────────────────

/** §3 — the auto-merge predicate's review-queue verdicts. */
export type RevisaoMotivo = "C4" | "C5" | "C6";

export const REVISAO_MOTIVO_LABEL: Record<RevisaoMotivo, string> = {
  C4: "Mesmo primeiro nome, sobrenomes diferentes",
  C5: "Dois nomes genuinamente diferentes",
  C6: "Três ou mais nomes distintos",
};

/**
 * C5 is the dangerous case (PROJECT.md §3: the 08-07 census found one real
 * phone shared by two genuinely distinct people) — it gets its own,
 * stronger copy so the operator reads it as "look carefully", not just
 * another badge.
 */
export const REVISAO_MOTIVO_HINT: Record<RevisaoMotivo, string> = {
  C4: "Pode ser a mesma pessoa com sobrenome incompleto — confira os toques antes de mesclar.",
  C5: "Um telefone/e-mail pode ser compartilhado por duas pessoas reais (casal, escritório). Não mescle sem confirmar que é a mesma pessoa.",
  C6: "Três ou mais nomes na mesma chave — revise cada candidato com atenção.",
};

export interface RevisaoCandidato {
  id: string;
  nome: string;
  chave_canonica: string;
  touch_count?: number | null;
  primeiro_contato_em?: string | null;
  ultimo_contato_em?: string | null;
}

export interface RevisaoGrupo {
  grupo_id: string;
  motivo: RevisaoMotivo;
  chave_canonica: string;
  candidatos: RevisaoCandidato[];
}

export interface RevisaoFiltros {
  page?: number;
  page_size?: number;
}

export interface RevisaoPage {
  items: RevisaoGrupo[];
  total: number;
  page: number;
  pages: number;
}

/** §5's `POST .../merge` response shape is unpinned — `merge_id` is the one
 * field this slice depends on (to wire the undo toast to `/merges/{id}/desfazer`).
 * Everything else passes through untyped rather than being invented. */
export interface RevisaoMergeResult {
  merge_id: string;
  [key: string]: unknown;
}

export const DEFAULT_REVISAO_PAGE_SIZE = 12;

// ─── Query keys ─────────────────────────────────────────────────────────────

const QUEUE_FAMILY_KEY = ["sw", "clientes", "revisao"] as const;
const QUEUE_KEY = (f: RevisaoFiltros) => [...QUEUE_FAMILY_KEY, f] as const;
const BOARD_FAMILY_KEY = ["sw", "clientes", "board"] as const;

const REVISAO_BASE = "/api/clientes/revisao";
const MERGES_BASE = "/api/clientes/merges";

function buildQuery(f: RevisaoFiltros): string {
  const params = new URLSearchParams();
  if (f.page) params.set("page", String(f.page));
  if (f.page_size) params.set("page_size", String(f.page_size));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** See file header, assumption 1. */
export function normalizeRevisaoPage(res: unknown, filtros: RevisaoFiltros): RevisaoPage {
  if (res && typeof res === "object" && Array.isArray((res as { items?: unknown }).items)) {
    const page = res as Partial<RevisaoPage> & { items: RevisaoGrupo[] };
    return {
      items: page.items,
      total: page.total ?? page.items.length,
      page: page.page ?? filtros.page ?? 1,
      pages: page.pages ?? 1,
    };
  }

  const items = Array.isArray(res) ? (res as RevisaoGrupo[]) : [];
  const pageSize = filtros.page_size ?? DEFAULT_REVISAO_PAGE_SIZE;
  const page = filtros.page ?? 1;
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    total: items.length,
    page,
    pages: Math.max(1, Math.ceil(items.length / pageSize)),
  };
}

// ─── Queries ────────────────────────────────────────────────────────────────

export function useRevisaoFila(filtros: RevisaoFiltros = {}) {
  return useQuery({
    queryKey: QUEUE_KEY(filtros),
    queryFn: async () => {
      const res = await api.get<unknown>(`${REVISAO_BASE}${buildQuery(filtros)}`);
      return normalizeRevisaoPage(res, filtros);
    },
    // A resolved group must not flash back in while the next page loads.
    placeholderData: (prev) => prev,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export function useRevisaoMutations() {
  const qc = useQueryClient();
  const invalidateQueue = () => qc.invalidateQueries({ queryKey: QUEUE_FAMILY_KEY });
  const invalidateBoard = () => qc.invalidateQueries({ queryKey: BOARD_FAMILY_KEY });

  const merge = useMutation<
    RevisaoMergeResult,
    unknown,
    { grupoId: string; sobreviventeId?: string }
  >({
    mutationFn: ({ grupoId, sobreviventeId }) =>
      api.post<RevisaoMergeResult>(
        `${REVISAO_BASE}/${encodeURIComponent(grupoId)}/merge`,
        sobreviventeId ? { sobrevivente_id: sobreviventeId } : undefined,
      ),
    onSuccess: () => {
      invalidateQueue();
      invalidateBoard();
    },
  });

  const manterSeparados = useMutation<unknown, unknown, string>({
    mutationFn: (grupoId) =>
      api.post(`${REVISAO_BASE}/${encodeURIComponent(grupoId)}/manter-separados`),
    onSuccess: invalidateQueue,
  });

  /** D3 — undo a merge. `mergeId` is `RevisaoMergeResult.merge_id`. */
  const desfazer = useMutation<unknown, unknown, string>({
    mutationFn: (mergeId) =>
      api.post(`${MERGES_BASE}/${encodeURIComponent(mergeId)}/desfazer`),
    onSuccess: () => {
      invalidateQueue();
      invalidateBoard();
    },
  });

  return { merge, manterSeparados, desfazer };
}
