/**
 * Orçamentos — list, detail, calculator preview, lifecycle (wave-2 contract,
 * Slices A + B).
 *
 *   GET   /api/orcamentos?aba=&status=&negocio_id=&lead_id=&cliente_id=&q=
 *   GET   /api/orcamentos/{id}
 *   POST  /api/orcamentos                      → 201
 *   PATCH /api/orcamentos/{id}                 (rascunho|enviado; else 409 orcamento_bloqueado)
 *   POST  /api/orcamentos/{id}/nova-versao     → 201 (previous → substituido)
 *   POST  /api/orcamentos/calcular             pure preview, no write
 *   POST  /api/orcamentos/{id}/aceitar         fechado transition + pautas
 *   POST  /api/orcamentos/{id}/recusar {motivo}
 *   DELETE /api/orcamentos/{id}                (rascunho only → 204)
 *   POST  /api/orcamentos/{id}/pdf             → {pdf_key, url}
 *   GET   /api/orcamentos/{id}/pdf             → {url}
 *   POST  /api/orcamentos/{id}/enviar          (Slice B; 409 pdf_nao_gerado)
 *   GET   /api/orcamentos/{id}/emails          (Slice B)
 *   POST  /api/orcamentos/{id}/contrato {modalidade_assinatura, dia_vencimento?}
 *
 * Every write invalidates the orçamento family AND the comercial board: an
 * accept moves the negócio to Fechado and creates a Cliente, so the funnel
 * and the clientes list go stale too.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { api, cleanParams, unwrapData } from "@/lib/api";
import { addTo, patchById, removeById, rowOps } from "@/lib/cacheOps";
import { COMERCIAL_BOARD_KEY } from "@/lib/pipelines";
import type {
  AceiteResultado,
  CalculoOrcamento,
  ContratoGerado,
  ModalidadeAssinatura,
  NovaVersaoInput,
  Orcamento,
  OrcamentoEmail,
  OrcamentoFiltros,
  OrcamentoInput,
  OrcamentoItemInput,
  OrcamentoPatch,
} from "@/types/crm";

export const ORCAMENTOS_QUERY_KEY = ["igig", "orcamentos"] as const;

export function useOrcamentos(filtros: OrcamentoFiltros = {}, opts: { enabled?: boolean } = {}) {
  const params = cleanParams({ ...filtros });
  const query = useQuery({
    queryKey: [...ORCAMENTOS_QUERY_KEY, "lista", params],
    queryFn: () => api.get("/api/orcamentos", params).then(unwrapData<Orcamento[]>),
    enabled: opts.enabled ?? true,
    // Filters/tabs ride in the key — never blank the list on a switch.
    placeholderData: (prev) => prev,
  });
  const data = query.data;
  return {
    ...query,
    orcamentos: data ?? [],
    showSkeleton: query.isPending && !data && (opts.enabled ?? true),
    isRefreshing: query.isFetching && !!data,
  };
}

export function useOrcamento(id: string | null) {
  const query = useQuery({
    queryKey: [...ORCAMENTOS_QUERY_KEY, "detalhe", id ?? "__none__"],
    queryFn: () => api.get(`/api/orcamentos/${encodeURIComponent(id as string)}`).then(unwrapData<Orcamento>),
    enabled: !!id,
  });
  const data = query.data;
  return {
    ...query,
    orcamento: data ?? null,
    showSkeleton: !!id && query.isPending && !data,
    isRefreshing: query.isFetching && !!data,
  };
}

/**
 * Live totals. A QUERY keyed on the (already debounced) payload, not a
 * mutation: identical payloads hit the cache, and `placeholderData` keeps the
 * last totals on screen while the next answer is in flight — the panel never
 * flashes back to zero on each keystroke.
 */
export function useCalculoOrcamento(payload: { itens: OrcamentoItemInput[]; desconto: number } | null) {
  const query = useQuery({
    queryKey: [...ORCAMENTOS_QUERY_KEY, "calcular", payload],
    queryFn: () => api.post("/api/orcamentos/calcular", payload).then(unwrapData<CalculoOrcamento>),
    enabled: !!payload && payload.itens.length > 0,
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });
  const data = query.data;
  return {
    ...query,
    calculo: data ?? null,
    isRefreshing: query.isFetching && !!data,
  };
}

export function useOrcamentoEmails(id: string | null) {
  const query = useQuery({
    queryKey: [...ORCAMENTOS_QUERY_KEY, "emails", id ?? "__none__"],
    queryFn: () => api.get(`/api/orcamentos/${encodeURIComponent(id as string)}/emails`).then(unwrapData<OrcamentoEmail[]>),
    enabled: !!id,
  });
  const data = query.data;
  return {
    ...query,
    emails: data ?? [],
    showSkeleton: !!id && query.isPending && !data,
  };
}

export function useOrcamentoMutations() {
  const qc = useQueryClient();
  const familia = ORCAMENTOS_QUERY_KEY;
  /**
   * Lists, details and the board settle in the background after every write:
   * an accept moves the negócio to Fechado (board regroups server-side) and
   * creates a Cliente, so the funnel and the clientes list go stale too.
   */
  const settle = [ORCAMENTOS_QUERY_KEY, [COMERCIAL_BOARD_KEY]];
  /** The row edited wherever it is cached: every list and its detail (all under the family prefix). */
  const noFamilia = <V,>(idOf: (v: V) => string, changesOf?: (v: V) => object) =>
    patchById<Orcamento, V>(familia, idOf, changesOf);

  const criar = useCacheWriteMutation<Orcamento, OrcamentoInput>({
    mutationFn: (payload) => api.post("/api/orcamentos", payload).then(unwrapData<Orcamento>),
    // The new rascunho certainly belongs in the unfiltered list; filtered tabs settle.
    targets: [addTo<Orcamento, OrcamentoInput>([...familia, "lista", {}], "prepend")],
    invalidate: settle,
  });
  const atualizar = useCacheWriteMutation<Orcamento, { id: string; payload: OrcamentoPatch }>({
    mutationFn: ({ id, payload }) =>
      api.patch(`/api/orcamentos/${encodeURIComponent(id)}`, payload).then(unwrapData<Orcamento>),
    // Totals are server-computed: commit the answer into list + detail.
    targets: [noFamilia<{ id: string; payload: OrcamentoPatch }>((v) => v.id)],
    invalidate: settle,
  });
  const novaVersao = useCacheWriteMutation<Orcamento, { id: string } & NovaVersaoInput>({
    mutationFn: ({ id, validade }) =>
      api.post(`/api/orcamentos/${encodeURIComponent(id)}/nova-versao`, { validade }).then(unwrapData<Orcamento>),
    targets: [
      // The previous version is superseded on the click…
      noFamilia<{ id: string } & NovaVersaoInput>((v) => v.id, () => ({ status: "substituido" as const })),
      // …and the new one joins the list when the server answers.
      addTo<Orcamento, { id: string } & NovaVersaoInput>([...familia, "lista", {}], "prepend"),
    ],
    invalidate: settle,
  });
  const aceitar = useCacheWriteMutation<AceiteResultado, string>({
    mutationFn: (id) => api.post(`/api/orcamentos/${encodeURIComponent(id)}/aceitar`, {}).then(unwrapData<AceiteResultado>),
    targets: [
      {
        queryKey: familia,
        match: "prefix",
        commit: (old, saved) => rowOps.patch(old, saved.orcamento.id, saved.orcamento),
      },
    ],
    invalidate: [...settle, ["igig", "clientes"]],
  });
  /** Idempotent recovery action on an ACCEPTED orçamento — for a deal closed
   * before pauta generation moved into the shared close path (a legacy
   * drag-to-Fechado), this fills the calendar in without editing anything. */
  const gerarPautas = useMutation({ // noc-allow: invalidate-only — an idempotent recovery action whose answer is a count; the pautas it creates live in another feature's cache, nothing here to write
    mutationFn: (id: string) =>
      api.post(`/api/orcamentos/${encodeURIComponent(id)}/gerar-pautas`, {}).then(unwrapData<{ pautas_criadas: number }>),
    onSuccess: () => Promise.all(settle.map((queryKey) => qc.invalidateQueries({ queryKey }))),
  });
  const recusar = useCacheWriteMutation<Orcamento, { id: string; motivo: string }>({
    mutationFn: ({ id, motivo }) =>
      api.post(`/api/orcamentos/${encodeURIComponent(id)}/recusar`, { motivo }).then(unwrapData<Orcamento>),
    targets: [noFamilia<{ id: string; motivo: string }>((v) => v.id, (v) => ({ status: "recusado" as const, motivo_recusa: v.motivo }))],
    invalidate: settle,
  });
  /** Hard-delete a rascunho (409 once it is sent/accepted or has a contrato/e-mail). */
  const excluir = useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`/api/orcamentos/${encodeURIComponent(id)}`),
    targets: [removeById<unknown, string>(familia, (id) => id)],
    invalidate: settle,
  });
  const gerarPdf = useCacheWriteMutation<{ pdf_key: string; url: string }, string>({
    mutationFn: (id) => api.post(`/api/orcamentos/${encodeURIComponent(id)}/pdf`, {}).then(unwrapData<{ pdf_key: string; url: string }>),
    // The PDF key lands on the orçamento (list + detail) so "baixar PDF" is enabled at once.
    targets: (id) => [
      { queryKey: familia, match: "prefix", commit: (old, saved) => rowOps.patch(old, id, { pdf_key: saved.pdf_key }) },
    ],
    invalidate: settle,
  });
  /** A signed, short-TTL URL — fetched on click, never cached. */
  const urlPdf = useMutation({ // noc-allow: invalidate-only — a signed short-TTL URL fetched on click and deliberately never cached; no read to update
    mutationFn: (id: string) => api.get(`/api/orcamentos/${encodeURIComponent(id)}/pdf`).then(unwrapData<{ url: string }>),
  });
  const enviar = useCacheWriteMutation<
    { orcamento: Orcamento; message_id: string },
    { id: string; para?: string; cc?: string; assunto?: string; mensagem?: string }
  >({
    mutationFn: ({ id, ...body }) =>
      api.post(`/api/orcamentos/${encodeURIComponent(id)}/enviar`, cleanParams(body)).then(unwrapData<{ orcamento: Orcamento; message_id: string }>),
    // No optimism: an e-mail is actually sent. "Enviado" shows the moment the server says so.
    targets: [
      {
        queryKey: familia,
        match: "prefix",
        commit: (old, saved) => rowOps.patch(old, saved.orcamento.id, saved.orcamento),
      },
    ],
    invalidate: settle,
  });
  const gerarContrato = useMutation({ // noc-allow: invalidate-only — the new contrato belongs to a list keyed by cliente_id, which only the answer carries; every orçamento / contrato / board view settles instead
    mutationFn: ({
      id,
      modalidade_assinatura,
      dia_vencimento,
      vias,
      signatario_email,
    }: {
      id: string;
      modalidade_assinatura: ModalidadeAssinatura;
      dia_vencimento?: number;
      vias?: number;
      signatario_email?: string;
    }) =>
      api.post(
        `/api/orcamentos/${encodeURIComponent(id)}/contrato`,
        cleanParams({ modalidade_assinatura, dia_vencimento, vias, signatario_email }),
      ).then(unwrapData<ContratoGerado>),
    onSuccess: () =>
      Promise.all([...settle, ["igig", "contratos"]].map((queryKey) => qc.invalidateQueries({ queryKey }))),
  });

  return {
    criar, atualizar, novaVersao, aceitar, recusar, excluir, gerarPdf, urlPdf, enviar, gerarContrato,
    gerarPautas,
  };
}
