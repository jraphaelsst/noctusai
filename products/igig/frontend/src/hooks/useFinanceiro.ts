/**
 * Financeiro hooks — Módulo 6.
 *
 * Backend mirror: `app/routers/financeiro_router.py`.
 *
 * Adding an invoice line returns the INVOICE, not the line, because the total
 * is derived server-side — a caller holding a stale total would show the
 * client a number that does not match the lines.
 */
import { useQuery } from "@tanstack/react-query";
import { addTo, listOps, patchById, rowOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api, cleanParams, unwrapData } from "@/lib/api";

export type StatusFatura = "aberta" | "enviada" | "paga" | "vencida" | "cancelada";
export type TipoItem = "mensalidade" | "excedente" | "desconto" | "avulso";

export interface Fatura {
  id: string;
  cliente_id: string;
  contrato_id: string | null;
  competencia: string;
  valor_total: number;
  vencimento: string | null;
  status: StatusFatura;
  pago_em: string | null;
  enviada_em: string | null;
}

export interface FaturaItem {
  id: string;
  fatura_id: string;
  descricao: string;
  tipo: string;
  quantidade: number;
  valor_unit: number;
}

export interface Excedente {
  cliente_id: string;
  cliente_nome: string;
  contrato_id: string;
  competencia: string;
  contratados: number;
  entregues: number;
  excedentes: number;
  valor_unitario: number;
  valor_total: number;
  /** The invoice this lands on — the month AFTER the work. */
  competencia_cobranca: string;
}

export interface DRE {
  cliente_id: string;
  cliente_nome: string;
  receita: number;
  custo: number;
  margem: number;
  margem_percentual: number;
  /** Non-empty ⇒ the margin is OVERSTATED. Must be shown, never hidden. */
  alertas: string[];
}

export interface Inadimplente {
  fatura_id: string;
  cliente_id: string;
  competencia: string;
  valor_total: number;
  vencimento: string;
  dias_atraso: number;
}

export const FINANCEIRO_QUERY_KEY = ["igig", "financeiro"] as const;

/**
 * Invoices, optionally scoped to one competência OR one cliente (the Clientes
 * card's Financeiro tab). The backend applies ONE filter: `cliente_id` wins
 * over `competencia` (`financeiro_router.listar_faturas`).
 */
export function useFaturas(competencia?: string, opts: { clienteId?: string | null } = {}) {
  const params = cleanParams({ cliente_id: opts.clienteId ?? undefined, competencia });
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "faturas", competencia ?? "", opts.clienteId ?? ""],
    queryFn: () => api.get<Fatura[]>("/api/financeiro/faturas", params),
    // `competencia` rides in the key — switching it is a new key. Keep the
    // previous list on screen instead of blanking to a skeleton.
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    faturas: query.data ?? [],
    loading: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * The lines that make up one invoice.
 *
 * `GET /faturas/{id}/itens` shipped with no consumer, so an invoice showed a
 * total with no way to see what was in it — the first question anyone asks
 * about a charge. Enabled only when a fatura is actually selected.
 */
export function useFaturaItens(faturaId: string | undefined) {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "itens", faturaId ?? ""],
    queryFn: () => api.get<FaturaItem[]>(`/api/financeiro/faturas/${faturaId}/itens`),
    enabled: !!faturaId,
  });
  return {
    ...query,
    itens: query.data ?? [],
    loading: query.isPending && !query.data,
  };
}

const FATURAS_KEY = [...FINANCEIRO_QUERY_KEY, "faturas"] as const;
const ITENS_KEY = [...FINANCEIRO_QUERY_KEY, "itens"] as const;

/**
 * Totals, resumo, DRE, excedentes and inadimplentes are all derived from the
 * faturas server-side — never recomputed here: they refresh in the background
 * once the fatura/linha itself has been written.
 */
const DERIVADOS = [FINANCEIRO_QUERY_KEY];

/** Where a freshly-created fatura for (cliente, competência) certainly belongs. */
function listasDaFatura<TVars>(competencia: string, clienteId: string) {
  return [
    addTo<Fatura, TVars>([...FATURAS_KEY, competencia, ""]),
    addTo<Fatura, TVars>([...FATURAS_KEY, "", clienteId]),
    addTo<Fatura, TVars>([...FATURAS_KEY, "", ""]),
  ];
}

export function useCriarFatura() {
  type Vars = { cliente_id: string; competencia: string; contrato_id?: string; vencimento?: string };
  return useCacheWriteMutation<Fatura, Vars>({
    mutationFn: (payload) => api.post<Fatura>("/api/financeiro/faturas", payload),
    targets: (v) => listasDaFatura<Vars>(v.competencia, v.cliente_id),
    invalidate: DERIVADOS,
  });
}

/** The answer is the INVOICE (its total is derived server-side): the fatura row is committed, the new line is drawn on the click. */
export function useAdicionarItem() {
  type Vars = { faturaId: string; descricao: string; tipo?: TipoItem; quantidade?: number; valor_unit?: number };
  return useCacheWriteMutation<Fatura, Vars>({
    mutationFn: ({ faturaId, ...item }) => api.post<Fatura>(`/api/financeiro/faturas/${faturaId}/itens`, item),
    targets: (v) => [
      {
        queryKey: [...ITENS_KEY, v.faturaId],
        // The line has no server id yet: a stand-in until the settle brings the real one.
        optimistic: (old: FaturaItem[] | undefined, vars, { tempId }) =>
          listOps.append(old, {
            id: tempId,
            fatura_id: vars.faturaId,
            descricao: vars.descricao,
            tipo: vars.tipo ?? "avulso",
            quantidade: vars.quantidade ?? 1,
            valor_unit: vars.valor_unit ?? 0,
          }),
      },
      patchById<Fatura, Vars>(FATURAS_KEY, (x) => x.faturaId),
    ],
    invalidate: DERIVADOS,
  });
}

export function useEditarFatura() {
  type Vars = { faturaId: string; competencia?: string; vencimento?: string };
  return useCacheWriteMutation<Fatura, Vars>({
    mutationFn: ({ faturaId, ...campos }) => api.patch<Fatura>(`/api/financeiro/faturas/${faturaId}`, campos),
    targets: [patchById<Fatura, Vars>(FATURAS_KEY, (v) => v.faturaId, ({ faturaId: _f, ...campos }) => campos)],
    invalidate: DERIVADOS,
  });
}

export function useEditarItem() {
  type Vars = { faturaId: string; itemId: string; descricao?: string; quantidade?: number; valor_unit?: number };
  return useCacheWriteMutation<Fatura, Vars>({
    mutationFn: ({ faturaId, itemId, ...campos }) =>
      api.patch<Fatura>(`/api/financeiro/faturas/${faturaId}/itens/${itemId}`, campos),
    targets: (v) => [
      // The linha changes on the click; the fatura's new total comes from the answer.
      {
        queryKey: [...ITENS_KEY, v.faturaId],
        optimistic: (old, { faturaId: _f, itemId, ...campos }) => rowOps.patch(old, itemId, campos),
      },
      patchById<Fatura, Vars>(FATURAS_KEY, (x) => x.faturaId),
    ],
    invalidate: DERIVADOS,
  });
}

export function useRemoverItem() {
  type Vars = { faturaId: string; itemId: string };
  return useCacheWriteMutation<Fatura, Vars>({
    mutationFn: ({ faturaId, itemId }) =>
      api.delete<Fatura>(`/api/financeiro/faturas/${faturaId}/itens/${itemId}`),
    targets: (v) => [
      { queryKey: [...ITENS_KEY, v.faturaId], optimistic: (old, x) => rowOps.remove(old, x.itemId) },
      patchById<Fatura, Vars>(FATURAS_KEY, (x) => x.faturaId),
    ],
    invalidate: DERIVADOS,
  });
}

export function useMarcarPaga() {
  return useCacheWriteMutation<Fatura, string>({
    mutationFn: (faturaId) => api.post<Fatura>(`/api/financeiro/faturas/${faturaId}/pagar`, {}),
    targets: [patchById<Fatura, string>(FATURAS_KEY, (id) => id, () => ({ status: "paga" as const }))],
    invalidate: DERIVADOS,
  });
}

/** Void an invoice (admin-only server-side). */
export function useCancelarFatura() {
  return useCacheWriteMutation<Fatura, string>({
    mutationFn: (faturaId) => api.post<Fatura>(`/api/financeiro/faturas/${faturaId}/cancelar`, {}),
    targets: [patchById<Fatura, string>(FATURAS_KEY, (id) => id, () => ({ status: "cancelada" as const }))],
    invalidate: DERIVADOS,
  });
}

/** E-mail the fatura's PDF to the cliente (admin-only server-side). */
export function useEnviarFatura() {
  return useCacheWriteMutation<{ fatura: Fatura; message_id: string }, string>({
    mutationFn: (faturaId) =>
      api.post<{ fatura: Fatura; message_id: string }>(`/api/financeiro/faturas/${faturaId}/enviar`, {}),
    // No optimism: an e-mail is actually sent. The fatura shows "enviada" the moment the server says so.
    targets: [
      {
        queryKey: FATURAS_KEY,
        match: "prefix",
        commit: (old, saved) => rowOps.patch(old, saved.fatura.id, saved.fatura),
      },
    ],
    invalidate: DERIVADOS,
  });
}

/** Manual "sent outside the system" flag — no e-mail (admin-only server-side). */
export function useMarcarFaturaEnviada() {
  return useCacheWriteMutation<Fatura, string>({
    mutationFn: (faturaId) => api.post<Fatura>(`/api/financeiro/faturas/${faturaId}/marcar-enviada`, {}),
    targets: [patchById<Fatura, string>(FATURAS_KEY, (id) => id)],
    invalidate: DERIVADOS,
  });
}

export function useExcedentes(competencia: string) {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "excedentes", competencia],
    queryFn: () => api.get<Excedente[]>(`/api/financeiro/excedentes/${competencia}`),
    enabled: /^\d{4}-\d{2}$/.test(competencia),
    // `competencia` rides in the key — changing the month picker is a new
    // key. Keep the previous list on screen instead of blanking to a
    // skeleton.
    placeholderData: (prev) => prev,
  });
  return { ...query, excedentes: query.data ?? [], loading: query.isPending && !query.data };
}

/**
 * `custoPorCompetencia`: when `true`, cost is ALSO scoped to `competencia`
 * (hours apontadas that month) instead of the backend's default full
 * history — the Dashboard's "Margem no mês" needs this so it compares the
 * SAME month on both sides; the M6 DRE screen (`Financeiro.tsx`) never
 * passes it, and keeps the documented "custo real é sempre o histórico
 * completo" behaviour. Requires `competencia` — the backend 422s otherwise.
 */
export function useDRE(competencia?: string, custoPorCompetencia = false) {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "dre", competencia ?? "", custoPorCompetencia],
    queryFn: () =>
      api.get<DRE[]>(
        "/api/financeiro/dre",
        cleanParams({
          competencia,
          custo_por_competencia: custoPorCompetencia ? true : undefined,
        }),
      ),
    // `competencia` rides in the key — keep the previous rows on screen
    // instead of blanking to a skeleton while the new competência loads.
    placeholderData: (prev) => prev,
  });
  return { ...query, linhas: query.data ?? [], loading: query.isPending && !query.data };
}

export function useInadimplentes() {
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "inadimplentes"],
    queryFn: () => api.get<Inadimplente[]>("/api/financeiro/inadimplentes"),
  });
  return { ...query, atrasadas: query.data ?? [], loading: query.isPending && !query.data };
}

// ─── Fechamento do mês + resumo (wave-2 contract, Slice E1) ──────────────

/** `POST /faturas/gerar-competencia` answer. Idempotent per contrato × mês. */
export interface GerarCompetenciaResultado {
  criadas: Fatura[];
  existentes: Fatura[];
}

export interface ResumoFinanceiro {
  competencia: string | null;
  /** Always the CURRENT active book — not scoped to `competencia`. */
  mrr: number;
  a_receber: number;
  recebido: number;
  inadimplente_valor: number;
  inadimplente_qtd: number;
}

/**
 * "Gerar competência": one invoice per active contract for the month
 * (retainer + that month's excedentes). Safe to re-run — a contract already
 * billed comes back under `existentes`, never twice.
 */
export function useGerarCompetencia() {
  return useCacheWriteMutation<GerarCompetenciaResultado, string>({
    // The router answers the bare model today (no `{data}` envelope);
    // `unwrapData` accepts both so a later envelope alignment is a no-op here.
    mutationFn: (competencia) =>
      api
        .post("/api/financeiro/faturas/gerar-competencia", { competencia })
        .then(unwrapData<GerarCompetenciaResultado>),
    // The month's faturas show up as soon as the server lists what it created.
    targets: (competencia) => [
      {
        queryKey: [...FATURAS_KEY, competencia, ""],
        commit: (old: Fatura[] | undefined, saved: GerarCompetenciaResultado) =>
          saved.criadas.reduce<Fatura[] | undefined>((lista, f) => rowOps.add(lista, f), old),
      },
    ],
    invalidate: DERIVADOS,
  });
}

export function useResumoFinanceiro(competencia?: string) {
  const params = cleanParams({ competencia });
  const query = useQuery({
    queryKey: [...FINANCEIRO_QUERY_KEY, "resumo", competencia ?? ""],
    queryFn: () => api.get("/api/financeiro/resumo", params).then(unwrapData<ResumoFinanceiro>),
    enabled: !competencia || /^\d{4}-\d{2}$/.test(competencia),
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  return {
    ...query,
    resumo: data ?? null,
    showSkeleton: query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}
