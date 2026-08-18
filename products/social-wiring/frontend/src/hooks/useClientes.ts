/**
 * Clientes board hooks — TanStack Query wrappers over `/api/clientes`
 * (`products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §5, the
 * FE↔BE contract both slices build to). Mirrors `usePortalRoi.ts` /
 * `useImoveis.ts` conventions (bare-payload `api.get<T>`, manual
 * `buildQuery`, `placeholderData` to avoid a flash on pagination).
 *
 * The backend for this contract is being built in a PARALLEL worktree and
 * does not exist on this branch — every shape below is built to §5, never
 * to observed behaviour. §5 pins the board row's *filters* explicitly
 * (`?ativo=`, `?q=`, `?corretor_id=`, pagination) but does NOT pin the row's
 * exact JSON shape beyond §4's schema columns — every field below traces to
 * a §4 column; `touch_count` / `atendimentos_abertos` are ASSUMED present
 * (so a card can show "14 toques" without a second request) and rendered as
 * "—" rather than a lying zero if the live response omits them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

// ─── Types (§4 schema — `clientes` table) ──────────────────────────────────

export type ClienteChaveTipo = "telefone" | "email" | null;

export interface Cliente {
  id: string;
  nome: string;
  /** E.164 phone or lowercased email. `null` ⇒ one of the 399 keyless leads (PROJECT.md §2). */
  chave_canonica: string | null;
  chave_tipo: ClienteChaveTipo;
  /** §2 — true for a keyless cliente created from a `contato_norm IS NULL` lead. Never auto-merged. */
  identidade_incerta: boolean;
  ativo: boolean;
  inativo_em: string | null;
  arquivado_em: string | null;
  primeiro_contato_em: string | null;
  ultimo_contato_em: string | null;
  /** ASSUMPTION — see file header. `undefined`/`null` renders "—", never "0". */
  touch_count?: number | null;
  atendimentos_abertos?: number | null;
  /**
   * lead-card-hub-p2-PROJECT.md §3: "the board list endpoint must return
   * these counts inline for every card [so it can render card faces
   * without N+1 calls]". That requirement is stated against the BOARD
   * list, but this file's route (`GET /api/clientes`) is P1's contract —
   * whether P2's backend slice enriches THIS SAME response, or only the
   * single-record `GET /clientes/{id}/card`, is left unresolved by both
   * contracts (surfaced, not silently assumed either way). Optional here:
   * `ClienteCardFace` already renders nothing when badges/tags are absent,
   * so the board face degrades gracefully — no badges, no colour strip —
   * until/unless the list route is confirmed to carry them.
   */
  tags?: { id: string; nome: string; cor: string }[];
  badges?: {
    notas: number;
    documentos: number;
    touches: number;
    checklist_total: number;
    checklist_concluidos: number;
    tem_descricao: boolean;
    temperatura: { valor: number; rotulo: string; provisoria: true } | null;
  };
  data_entrega?: string | null;
  entrega_concluida?: boolean;
}

export interface ClientesFiltros {
  page?: number;
  page_size?: number;
  /**
   * Omitted ⇒ server default is **active only** (D4, §5: "Default active
   * only"). Explicit `false` is how the board asks for the inactive tab —
   * there is deliberately no explicit `true` sent for the default tab, to
   * stay symmetric with the server's own default rather than duplicating it
   * client-side.
   */
  ativo?: boolean;
  q?: string;
  corretor_id?: string;
}

export interface ClientesPage {
  items: Cliente[];
  total: number;
  page: number;
  pages: number;
}

/**
 * PATCH body — §5: "PATCH /api/clientes/{id} — nome, ativo/arquivado
 * (manual restore, D4)". §4 models TWO distinct columns (`ativo boolean`
 * and a separate `arquivado_em timestamptz`), but §5's prose names them as
 * one write surface ("ativo/arquivado"). ASSUMPTION: only `ativo` is
 * writable here — flipping it `true` IS the manual restore D4 requires.
 * `arquivado_em` (a stronger, presumably-terminal state than 180-day
 * inactivity) has no documented write path in §5, so it is deliberately NOT
 * exposed — inventing one would be building past the contract.
 */
export interface ClientePatchBody {
  nome?: string;
  ativo?: boolean;
}

// ─── Query keys ─────────────────────────────────────────────────────────────

const FAMILY_KEY = ["sw", "clientes"] as const;
const BOARD_KEY = (f: ClientesFiltros) => [...FAMILY_KEY, "board", f] as const;

const BASE = "/api/clientes";

function buildQuery(f: ClientesFiltros): string {
  const params = new URLSearchParams();
  if (f.page) params.set("page", String(f.page));
  if (f.page_size) params.set("page_size", String(f.page_size));
  if (f.ativo !== undefined) params.set("ativo", String(f.ativo));
  if (f.q) params.set("q", f.q);
  if (f.corretor_id) params.set("corretor_id", f.corretor_id);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

// ─── Queries ────────────────────────────────────────────────────────────────

export function useClientesBoard(filtros: ClientesFiltros = {}) {
  return useQuery({
    queryKey: BOARD_KEY(filtros),
    queryFn: async () => {
      const res = await api.get<ClientesPage>(`${BASE}${buildQuery(filtros)}`);
      return res ?? { items: [], total: 0, page: 1, pages: 1 };
    },
    // Keeps the previous page on screen while the next one loads — same
    // rationale as useImoveis: paginating shouldn't flash an empty grid.
    placeholderData: (prev) => prev,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export function useClienteMutations() {
  const qc = useQueryClient();
  const invalidateAll = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const update = useMutation<Cliente, unknown, { id: string; body: ClientePatchBody }>({
    mutationFn: ({ id, body }) =>
      api.patch<Cliente>(`${BASE}/${encodeURIComponent(id)}`, body),
    onSuccess: invalidateAll,
  });

  return { update };
}

// ─── Display helpers ────────────────────────────────────────────────────────

/** `null`/`undefined` renders "—", never a lying "0" for a count we don't have. */
export function formatCountOrDash(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("pt-BR");
}
