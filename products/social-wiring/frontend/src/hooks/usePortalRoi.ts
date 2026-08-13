/**
 * Portal ROI hooks — TanStack Query wrappers over `/api/portal-roi`
 * (`products/social-wiring/projects/portal-roi-PROJECT.md` §3, the FE↔BE
 * contract both slices build to).
 *
 * 🔴 The whole point of this page is that `investimento: null` (never
 * recorded) and `investimento: 0` (recorded as zero) are DIFFERENT facts —
 * §3.1/§3.5 of the contract. The same applies to `cpl` / `roi` /
 * `taxa_conversao`. Every formatter here renders `null` as "—", NEVER as a
 * currency/percent zero — reusing `@noctusai/lib`'s `formatCurrency` would
 * silently reintroduce exactly the lying-zero bug §2 of the PROJECT fixes
 * one layer down (`formatCurrency(null)` returns `"R$ 0,00"`, see
 * `seed/lib/frontend/src/utils.ts`) — flagged as `scoped-improvement` in the
 * delivery note rather than used here.
 *
 * Response envelopes: bare, no `{data: ...}` wrapper — matches the closest
 * sibling (`useImoveis.ts`), not the `SuccessEnvelope<T>` shape
 * `useLeadsSources.ts` uses. `/origens`'s exact envelope isn't spelled in
 * the contract (only `/resumo` and `/campanhas` show worked examples);
 * `{ origens: OrigemLead[] }` is INFERRED from the sibling endpoints'
 * named-key convention (mirrors the `N8nExecutionListResponse` precedent in
 * `useN8nWorkflows.ts`) — flag if the live shape differs.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { ApiError, formatDate } from "@noctusai/lib";

// ─── Types (mirror the FE↔BE contract verbatim — PROJECT.md §3) ────────────

export type PortalRoiCategoria = "portal" | "social" | "direto" | "outro";

export interface PortalRoiTotais {
  investimento: number | null;
  total_leads: number;
  total_vendas: number;
  valor_vendas: number;
  cpl: number | null;
  roi: number | null;
  taxa_conversao: number | null;
}

export interface PortalRoiPortal extends PortalRoiTotais {
  origem_id: string;
  slug: string;
  label: string;
  categoria: PortalRoiCategoria;
}

export interface PortalRoiPeriodo {
  inicio: string;
  fim: string;
}

export interface PortalRoiResumo {
  periodo: PortalRoiPeriodo | null;
  totais: PortalRoiTotais;
  portais: PortalRoiPortal[];
}

export interface PortalRoiFiltros {
  periodo_inicio?: string;
  periodo_fim?: string;
}

export interface CampanhaRow {
  id: string;
  origem_id: string;
  origem_label: string;
  periodo_inicio: string;
  periodo_fim: string;
  investimento: number;
  impressoes: number | null;
  cliques: number | null;
  leads: number | null;
  visitas_perfil: number | null;
  engajamento: number | null;
  /** GENERATED — read-only, never sent on a write. */
  cpc: number | null;
  /** GENERATED — read-only, never sent on a write. */
  cpl: number | null;
  /** GENERATED — read-only, never sent on a write. */
  custo_visita: number | null;
  observacoes: string | null;
  created_at: string;
  updated_at: string | null;
}

/** Writable fields per §3.3 — `cpc`/`cpl`/`custo_visita` are deliberately absent. */
export interface CampanhaWritableFields {
  origem_id: string;
  periodo_inicio: string;
  periodo_fim: string;
  investimento: number;
  impressoes?: number | null;
  cliques?: number | null;
  leads?: number | null;
  visitas_perfil?: number | null;
  engajamento?: number | null;
  observacoes?: string | null;
}

export interface CampanhaFiltros extends PortalRoiFiltros {
  origem_id?: string;
}

export interface OrigemLead {
  id: string;
  slug: string;
  label: string;
  categoria: PortalRoiCategoria;
}

const EMPTY_TOTAIS: PortalRoiTotais = {
  investimento: null,
  total_leads: 0,
  total_vendas: 0,
  valor_vendas: 0,
  cpl: null,
  roi: null,
  taxa_conversao: null,
};

// ─── Query keys ─────────────────────────────────────────────────────────────

const FAMILY_KEY = ["sw", "portal-roi"] as const;
const RESUMO_KEY = (f: PortalRoiFiltros) => [...FAMILY_KEY, "resumo", f] as const;
const CAMPANHAS_KEY = (f: CampanhaFiltros) => [...FAMILY_KEY, "campanhas", f] as const;
const ORIGENS_KEY = [...FAMILY_KEY, "origens"] as const;

const BASE = "/api/portal-roi";

function buildQuery(params: Record<string, string | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) qs.set(key, value);
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

// ─── Queries ────────────────────────────────────────────────────────────────

export function usePortalRoiResumo(filtros: PortalRoiFiltros = {}) {
  return useQuery({
    queryKey: RESUMO_KEY(filtros),
    queryFn: async () => {
      const res = await api.get<PortalRoiResumo>(
        `${BASE}/resumo${buildQuery({
          periodo_inicio: filtros.periodo_inicio,
          periodo_fim: filtros.periodo_fim,
        })}`,
      );
      return res ?? { periodo: null, totais: EMPTY_TOTAIS, portais: [] };
    },
  });
}

export function usePortalRoiCampanhas(
  filtros: CampanhaFiltros = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: CAMPANHAS_KEY(filtros),
    queryFn: async () => {
      const res = await api.get<{ campanhas: CampanhaRow[] }>(
        `${BASE}/campanhas${buildQuery({
          origem_id: filtros.origem_id,
          periodo_inicio: filtros.periodo_inicio,
          periodo_fim: filtros.periodo_fim,
        })}`,
      );
      return res?.campanhas ?? [];
    },
    enabled: options.enabled,
  });
}

export function usePortalRoiOrigens() {
  return useQuery({
    queryKey: ORIGENS_KEY,
    queryFn: async () => {
      const res = await api.get<{ origens: OrigemLead[] }>(`${BASE}/origens`);
      return res?.origens ?? [];
    },
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

export function usePortalRoiCampanhaMutations() {
  const qc = useQueryClient();
  // Every derived surface (resumo totals + per-portal rows + the campanhas
  // list itself) is downstream of one write — invalidate the whole family
  // rather than enumerating each key.
  const invalidateAll = () => qc.invalidateQueries({ queryKey: FAMILY_KEY });

  const create = useMutation<CampanhaRow, unknown, CampanhaWritableFields>({
    mutationFn: (body) => api.post<CampanhaRow>(`${BASE}/campanhas`, body),
    onSuccess: invalidateAll,
  });

  const update = useMutation<
    CampanhaRow,
    unknown,
    { id: string; body: Partial<CampanhaWritableFields> }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<CampanhaRow>(`${BASE}/campanhas/${encodeURIComponent(id)}`, body),
    onSuccess: invalidateAll,
  });

  const remove = useMutation<unknown, unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/campanhas/${encodeURIComponent(id)}`),
    onSuccess: invalidateAll,
  });

  return { create, update, remove };
}

// ─── Conflict resolution (contract §3.3 — the 409 case) ────────────────────

/**
 * `POST /campanhas` 409s on a duplicate `(origem_id, periodo_inicio,
 * periodo_fim)` — the contract requires offering "update the existing
 * period" instead of a dead end, but does not pin the exact JSON shape of
 * the 409 body, and the seed api client's `extractErrorMessage` only
 * decodes a STRING or Pydantic-array `detail` into `err.message` (a
 * structured `{conflicting_id: ...}` object would be silently dropped —
 * see `seed/lib/frontend/src/api.ts:extractErrorMessage`). Rather than
 * depend on an unpinned error-body shape, this resolves the conflict from
 * data the FE already holds: the manager dialog loads every campanha row
 * for the target `origem_id` before the operator submits, so the exact
 * `(periodo_inicio, periodo_fim)` collision can be located client-side —
 * both as a pre-submit guard (never fire the request that would 409) and
 * as the true-409 fallback (a same-origem write raced in from elsewhere).
 */
export function findConflictingCampanha(
  campanhas: CampanhaRow[],
  input: { periodo_inicio: string; periodo_fim: string },
  excludeId?: string,
): CampanhaRow | null {
  return (
    campanhas.find(
      (c) =>
        c.periodo_inicio === input.periodo_inicio &&
        c.periodo_fim === input.periodo_fim &&
        c.id !== excludeId,
    ) ?? null
  );
}

/** True for a mutation error that is (or presents as) an HTTP 409. */
export function isConflictError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

// ─── Display helpers ────────────────────────────────────────────────────────

/**
 * `null` = never recorded → "não informado", rendered as a muted em dash
 * (contract §3.5: "a dash or muted '—' with a tooltip is fine; a zero is
 * not"). Deliberately NOT `@noctusai/lib`'s `formatCurrency` — that helper
 * coerces `null`/`undefined` to `"R$ 0,00"`, which is precisely the bug
 * PROJECT.md §2 fixes at the SQL layer; reusing it here would silently
 * reintroduce it in the UI.
 */
export function formatMoneyOrNaoInformado(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}

/**
 * 🔴 The API returns RATIOS, not percent units. `vw_portal_roi` computes
 * `taxa_conversao = total_vendas / total_leads` (`0.05`) and
 * `roi = valor_vendas / investimento` (`2.5`), and
 * `portal_roi_service._taxa_conversao` / `._roi` mirror the view exactly.
 * The contract (§3.1) showed the fields but never stated their scale — an
 * earlier draft of this file assumed percent units and rendered 5 % as
 * "0,1%" and a 2.5× return as "+2,5%". Every number on the page was off by
 * 100. Scale is now converted HERE, at the one boundary that knows it.
 *
 * `null` renders "—", never "0%" — same rule as money (§3.5).
 */
export function formatPercentOrNaoInformado(
  value: number | null | undefined,
  signed = false,
): string {
  if (value === null || value === undefined) return "—";
  const pct = value * 100;
  const sign = signed && pct > 0 ? "+" : "";
  return `${sign}${pct.toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`;
}

/**
 * `roi` is `valor_vendas / investimento` — revenue per R$1 of spend, i.e.
 * ROAS. That is a MULTIPLE, not a percentage: 2.5 means "R$ 2,50 back per
 * R$ 1,00 spent". Rendering it as "+250%" borrows percentage-CHANGE
 * semantics it does not have (a 2.5× return is a +150% change, not +250%),
 * so it gets its own formatter rather than being squeezed through the
 * percent one.
 */
export function formatMultipleOrNaoInformado(
  value: number | null | undefined,
): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}×`;
}

/** Plain pt-BR thousands-separated integer — `total_leads`/`total_vendas` are never null. */
export function formatCount(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString("pt-BR");
}

/** `YYYY-MM-DD` → `DD/MM/YYYY`. Thin re-export of the seed helper so every
 * date on this page (campanha periods, timestamps) renders identically. */
export function formatDateBR(value: string | null | undefined): string {
  return formatDate(value ?? null);
}
