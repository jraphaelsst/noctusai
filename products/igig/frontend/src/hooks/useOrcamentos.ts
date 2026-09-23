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

import { api, cleanParams, unwrapData } from "@/lib/api";
import { COMERCIAL_BOARD_KEY } from "@/lib/pipelines";
import type {
  AceiteResultado,
  CalculoOrcamento,
  ContratoGerado,
  ModalidadeAssinatura,
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
  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ORCAMENTOS_QUERY_KEY }),
      qc.invalidateQueries({ queryKey: [COMERCIAL_BOARD_KEY] }),
    ]);

  const criar = useMutation({
    mutationFn: (payload: OrcamentoInput) => api.post("/api/orcamentos", payload).then(unwrapData<Orcamento>),
    onSuccess: invalidate,
  });
  const atualizar = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OrcamentoPatch }) =>
      api.patch(`/api/orcamentos/${encodeURIComponent(id)}`, payload).then(unwrapData<Orcamento>),
    onSuccess: invalidate,
  });
  const novaVersao = useMutation({
    mutationFn: (id: string) => api.post(`/api/orcamentos/${encodeURIComponent(id)}/nova-versao`, {}).then(unwrapData<Orcamento>),
    onSuccess: invalidate,
  });
  const aceitar = useMutation({
    mutationFn: (id: string) => api.post(`/api/orcamentos/${encodeURIComponent(id)}/aceitar`, {}).then(unwrapData<AceiteResultado>),
    onSuccess: () =>
      Promise.all([invalidate(), qc.invalidateQueries({ queryKey: ["igig", "clientes"] })]),
  });
  const recusar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      api.post(`/api/orcamentos/${encodeURIComponent(id)}/recusar`, { motivo }).then(unwrapData<Orcamento>),
    onSuccess: invalidate,
  });
  const gerarPdf = useMutation({
    mutationFn: (id: string) => api.post(`/api/orcamentos/${encodeURIComponent(id)}/pdf`, {}).then(unwrapData<{ pdf_key: string; url: string }>),
    onSuccess: invalidate,
  });
  /** A signed, short-TTL URL — fetched on click, never cached. */
  const urlPdf = useMutation({
    mutationFn: (id: string) => api.get(`/api/orcamentos/${encodeURIComponent(id)}/pdf`).then(unwrapData<{ url: string }>),
  });
  const enviar = useMutation({
    mutationFn: ({
      id,
      ...body
    }: { id: string; para?: string; cc?: string; assunto?: string; mensagem?: string }) =>
      api.post(`/api/orcamentos/${encodeURIComponent(id)}/enviar`, cleanParams(body)).then(unwrapData<{ orcamento: Orcamento; message_id: string }>),
    onSuccess: invalidate,
  });
  const gerarContrato = useMutation({
    mutationFn: ({
      id,
      modalidade_assinatura,
      dia_vencimento,
    }: { id: string; modalidade_assinatura: ModalidadeAssinatura; dia_vencimento?: number }) =>
      api.post(
        `/api/orcamentos/${encodeURIComponent(id)}/contrato`,
        cleanParams({ modalidade_assinatura, dia_vencimento }),
      ).then(unwrapData<ContratoGerado>),
    onSuccess: () =>
      Promise.all([invalidate(), qc.invalidateQueries({ queryKey: ["igig", "contratos"] })]),
  });

  return { criar, atualizar, novaVersao, aceitar, recusar, gerarPdf, urlPdf, enviar, gerarContrato };
}
