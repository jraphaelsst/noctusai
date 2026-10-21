/**
 * Comercial — leads + the negócio funnel card's own writes.
 *
 * Backend mirror: `app/routers/comercial_router.py` (leads) and
 * `app/routers/comercial_funil_router.py` (negócios). The board itself (query,
 * optimistic move, stage editor) is the seed pipeline organ declared in
 * `@/lib/pipelines`; orçamentos live in `@/hooks/useOrcamentos`.
 *
 * The legacy calculator / orçamento / contrato endpoints of this module
 * (`/api/comercial/estimar`, `/api/comercial/orcamentos*`,
 * `/api/comercial/contratos/gerar`) are GONE (wave-2 contract, Slice A) — the
 * orçamento lifecycle is `/api/orcamentos/*` now.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { boardOps, patchById, rowOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api, unwrapData } from "@/lib/api";
import { COMERCIAL_BOARD_KEY } from "@/lib/pipelines";
import type { AssistenteAcao, LeadManualInput, Negocio } from "@/types/crm";

export interface Lead {
  id: string;
  nome: string;
  email: string | null;
  telefone: string | null;
  empresa: string | null;
  nicho: string | null;
  canais_atuais?: string | null;
  dores: string | null;
  orcamento_disponivel: number | null;
  origem?: string | null;
  como_conheceu?: string | null;
  instagram?: string | null;
  especificacoes?: Record<string, unknown>;
  observacoes?: string | null;
  status: "novo" | "qualificado" | "descartado" | "convertido";
  cliente_id: string | null;
  created_at?: string | null;
}

export type LeadPatch = Partial<
  Pick<Lead, "nome" | "email" | "telefone" | "empresa" | "instagram" | "nicho" | "observacoes">
>;

export const COMERCIAL_QUERY_KEY = ["igig", "comercial"] as const;

export function useLeads(status?: string) {
  const query = useQuery({
    queryKey: [...COMERCIAL_QUERY_KEY, "leads", status ?? ""],
    queryFn: () =>
      api.get("/api/comercial/leads", status ? { status_filtro: status } : {}).then(unwrapData<Lead[]>),
    // `status` rides in the key — switching the filter is a new key. Keep
    // the previous list on screen instead of blanking to a skeleton.
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    leads: query.data ?? [],
    loading: query.isPending && !query.data,
    refreshing: query.isFetching && !!query.data,
  };
}

/**
 * One lead by id — the negócio card's "Lead" subpage used to call
 * `useLeads()` (the org's ENTIRE list) just to `.find()` a single row
 * (achado #11: an N-scaling read for one card open). `enabled: !!id` — pass
 * `null` while the negócio itself hasn't loaded yet.
 */
export function useLead(id: string | null) {
  const query = useQuery({
    queryKey: [...COMERCIAL_QUERY_KEY, "lead", id ?? ""],
    queryFn: () => api.get(`/api/comercial/leads/${encodeURIComponent(id as string)}`).then(unwrapData<Lead>),
    enabled: !!id,
  });
  return {
    ...query,
    lead: query.data ?? null,
    showSkeleton: !!id && query.isPending && !query.data,
  };
}

/**
 * One negócio, ANY status — the board query only ever holds `aberto`/`ganho`
 * cards (`GET /board`), so a `perdido` deal opened from its archive, or from
 * an orçamento deep link, falls back here (`GET /negocios/{id}`, gap G-2).
 * `enabled: !!id` — pass `null` when the board already has the card.
 */
export function useNegocioPorId(id: string | null) {
  return useQuery({
    queryKey: [...COMERCIAL_QUERY_KEY, "negocio", id ?? ""],
    queryFn: () =>
      api.get(`/api/comercial/negocios/${encodeURIComponent(id as string)}`).then(unwrapData<Negocio>),
    enabled: !!id,
  });
}

/** The board's card edits (a negócio's column total = sum of `valor_estimado`). */
const board = boardOps<Negocio>((n) => Number(n.valor_estimado || 0));
const BOARD = [COMERCIAL_BOARD_KEY] as const;
const PERDIDOS = [...COMERCIAL_QUERY_KEY, "perdidos"] as const;
const NEGOCIO = [...COMERCIAL_QUERY_KEY, "negocio"] as const;

/**
 * Every write here can regroup the funnel server-side and touches the lead /
 * perdidos / negócio queries: the board and the comercial family settle in
 * the background once the cache has been written.
 */
const SETTLE = [[COMERCIAL_BOARD_KEY], COMERCIAL_QUERY_KEY];

/**
 * The Perdidos archive — negócios the board itself never shows (`GET /board`
 * is aberto+ganho only). `GET /negocios?status=perdido` already existed with
 * no FE consumer at all (achado #10/#14 — no way to see, let alone reopen,
 * an archived deal).
 */
export function usePerdidos() {
  const query = useQuery({
    queryKey: [...COMERCIAL_QUERY_KEY, "perdidos"],
    queryFn: () => api.get("/api/comercial/negocios", { status: "perdido" }).then(unwrapData<Negocio[]>),
  });
  return {
    ...query,
    perdidos: query.data ?? [],
    showSkeleton: query.isPending && !query.data,
  };
}

/** "Reabrir" — returns a perdido negócio to the stage it was lost from. */
export function useReabrirNegocio() {
  return useCacheWriteMutation<Negocio, string>({
    mutationFn: (id) =>
      api.post(`/api/comercial/negocios/${encodeURIComponent(id)}/reabrir`, {}).then(unwrapData<Negocio>),
    targets: [
      // Leaves the archive on the click.
      { queryKey: PERDIDOS, optimistic: (old, id) => rowOps.remove(old, id) },
      // Back on the board in the stage the server put it in.
      { queryKey: BOARD, match: "prefix", commit: (old, saved) => board.addCard(old, saved.etapa_id, saved) },
      patchById<Negocio, string>(NEGOCIO, (id) => id),
    ],
    invalidate: SETTLE,
  });
}

/**
 * "Novo lead" — a manual lead lands on the funnel's entry stage, on top.
 *
 * `cliente_id` (comercial achado 12 — upsell/renewal): an EXISTING cliente
 * this negócio is for. Closing it reuses that cliente instead of creating a
 * second one from the fresh `lead` row every negócio still requires.
 */
export function useCriarNegocio() {
  return useCacheWriteMutation<
    Negocio,
    {
      lead?: LeadManualInput;
      lead_id?: string;
      titulo?: string;
      valor_estimado?: number;
      responsavel_id?: string;
      cliente_id?: string;
    }
  >({
    mutationFn: (payload) => api.post("/api/comercial/negocios", payload).then(unwrapData<Negocio>),
    // The server picks the entry stage: commit the card where it says.
    targets: [{ queryKey: BOARD, match: "prefix", commit: (old, saved) => board.addCard(old, saved.etapa_id, saved) }],
    invalidate: SETTLE,
  });
}

export function useAtualizarNegocio() {
  type Vars = { id: string; titulo?: string; valor_estimado?: number | null; responsavel_id?: string | null };
  return useCacheWriteMutation<Negocio, Vars>({
    mutationFn: ({ id, ...payload }) =>
      api.patch(`/api/comercial/negocios/${encodeURIComponent(id)}`, payload).then(unwrapData<Negocio>),
    targets: [
      {
        queryKey: BOARD,
        match: "prefix",
        optimistic: (old, { id, ...changes }) => board.patchCard(old, id, changes),
        commit: (old, saved) => board.patchCard(old, saved.id, saved),
      },
      patchById<Negocio, Vars>(NEGOCIO, (v) => v.id, ({ id: _id, ...changes }) => changes),
    ],
    invalidate: SETTLE,
  });
}

/** "Marcar como perdido" — archive with a REQUIRED reason (loss statistics). */
export function usePerderNegocio() {
  return useCacheWriteMutation<Negocio, { id: string; motivo: string }>({
    mutationFn: ({ id, motivo }) =>
      api.post(`/api/comercial/negocios/${encodeURIComponent(id)}/perder`, { motivo }).then(unwrapData<Negocio>),
    targets: [
      // Off the board on the click…
      { queryKey: BOARD, match: "prefix", optimistic: (old, { id }) => board.removeCard(old, id) },
      // …and into the archive as soon as the server answers.
      { queryKey: PERDIDOS, commit: (old, saved) => rowOps.add(old, saved, "prepend") },
      patchById<Negocio, { id: string; motivo: string }>(NEGOCIO, (v) => v.id),
    ],
    invalidate: SETTLE,
  });
}

/**
 * Edit the lead's contact data from the negócio card's "Lead" subpage —
 * `PATCH /api/comercial/leads/{id}` (roadmap gap G-1, same router as the
 * lead list).
 */
export function useAtualizarLead() {
  return useCacheWriteMutation<Lead, LeadPatch & { id: string }>({
    mutationFn: ({ id, ...payload }) =>
      api.patch(`/api/comercial/leads/${encodeURIComponent(id)}`, payload).then(unwrapData<Lead>),
    // The lead list + the lead detail; the board's embedded lead summary settles.
    targets: [
      patchById<Lead, LeadPatch & { id: string }>(
        [...COMERCIAL_QUERY_KEY, "leads"],
        (v) => v.id,
        ({ id: _id, ...changes }) => changes,
      ),
      patchById<Lead, LeadPatch & { id: string }>(
        [...COMERCIAL_QUERY_KEY, "lead"],
        (v) => v.id,
        ({ id: _id, ...changes }) => changes,
      ),
    ],
    invalidate: SETTLE,
  });
}

/**
 * Reassign the funnel's one system role (`fechado`) to a stage, or clear it.
 * Sibling of the seed's generic stage PATCH (still used for
 * label/cor/posicao/ativo) and of `useEsteira`'s `useAtribuirPapelEtapa` —
 * this one atomically moves `fechado` off whatever stage held it, and
 * refuses to clear the sole holder (comercial achado #14, 409
 * `papel_fechado_obrigatorio`).
 */
export function useAtribuirPapelEtapaComercial() {
  const qc = useQueryClient();
  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: [COMERCIAL_BOARD_KEY] }),
      qc.invalidateQueries({ queryKey: COMERCIAL_QUERY_KEY }),
    ]);
  return useMutation({ // noc-allow: invalidate-only — atomically moves the `fechado` role off whatever stage held it (and 409s on the sole holder); the answer carries no row and the stage list / board are regrouped server-side
    mutationFn: ({ etapaId, papel }: { etapaId: string; papel: string | null }) =>
      api.patch(`/api/comercial/pipeline/stages/${encodeURIComponent(etapaId)}/papel`, { papel }),
    onSuccess: invalidate,
  });
}

/** Assistente IA (Slice E2) — Claude via the seed LLM seam. */
export function useAssistenteNegocio() {
  return useMutation({ // noc-allow: invalidate-only — generates text on demand; no cached read to update (the answer is returned to the caller)
    mutationFn: ({
      negocioId,
      acao,
      canal,
    }: { negocioId: string; acao: AssistenteAcao; canal?: "email" | "whatsapp" }) =>
      api.post(
        `/api/comercial/negocios/${encodeURIComponent(negocioId)}/assistente`,
        canal ? { acao, canal } : { acao },
      ).then(unwrapData<{ texto: string }>),
  });
}
