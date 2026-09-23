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

function useInvalidateFunil() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: [COMERCIAL_BOARD_KEY] }),
      qc.invalidateQueries({ queryKey: COMERCIAL_QUERY_KEY }),
    ]);
}

/** "Novo lead" — a manual lead lands on the funnel's entry stage, on top. */
export function useCriarNegocio() {
  const invalidate = useInvalidateFunil();
  return useMutation({
    mutationFn: (payload: {
      lead?: LeadManualInput;
      lead_id?: string;
      titulo?: string;
      valor_estimado?: number;
      responsavel_id?: string;
    }) => api.post("/api/comercial/negocios", payload).then(unwrapData<Negocio>),
    onSuccess: invalidate,
  });
}

export function useAtualizarNegocio() {
  const invalidate = useInvalidateFunil();
  return useMutation({
    mutationFn: ({
      id,
      ...payload
    }: { id: string; titulo?: string; valor_estimado?: number | null; responsavel_id?: string | null }) =>
      api.patch(`/api/comercial/negocios/${encodeURIComponent(id)}`, payload).then(unwrapData<Negocio>),
    onSuccess: invalidate,
  });
}

/** "Marcar como perdido" — archive with a REQUIRED reason (loss statistics). */
export function usePerderNegocio() {
  const invalidate = useInvalidateFunil();
  return useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      api.post(`/api/comercial/negocios/${encodeURIComponent(id)}/perder`, { motivo }).then(unwrapData<Negocio>),
    onSuccess: invalidate,
  });
}

/**
 * Edit the lead's contact data from the negócio card's "Lead" subpage —
 * `PATCH /api/comercial/leads/{id}` (roadmap gap G-1, same router as the
 * lead list).
 */
export function useAtualizarLead() {
  const invalidate = useInvalidateFunil();
  return useMutation({
    mutationFn: ({ id, ...payload }: LeadPatch & { id: string }) =>
      api.patch(`/api/comercial/leads/${encodeURIComponent(id)}`, payload).then(unwrapData<Lead>),
    onSuccess: invalidate,
  });
}

/** Assistente IA (Slice E2) — Claude via the seed LLM seam. */
export function useAssistenteNegocio() {
  return useMutation({
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
