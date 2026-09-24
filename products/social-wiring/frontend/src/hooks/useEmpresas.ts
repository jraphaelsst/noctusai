/**
 * Empresas — query/mutation hooks for the P0c contract's card-hub-family
 * routes (`project-history/roadmaps/sw-drive-extraction-P0c-contract.md`
 * §D.1-4). Mirrors `useCardHub.ts`'s own conventions (bare-payload
 * `api.get<T>`, `@noctusai/seed/infra`, manual query-string, `{items}`
 * envelope) — these ARE card routes ("Card routes use
 * `auth=Depends(get_current_user_org)` … and return a raw dict", §D), just
 * keyed by `empresa_id` instead of `cliente_id`.
 *
 * The backend (S2a) is being built in a PARALLEL worktree and does not exist
 * on this branch — every shape traces to the contract, never to observed
 * behaviour (same disclaimer `useCardHub.ts`'s own docblock carries).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import { uploadMultipart } from "@/hooks/useCardHub";
import type { DocumentoUrlResponse } from "@/types/cardHub";
import type {
  AdicionarEmpresaBody,
  EmpresaCardItem,
  EmpresaDocumento,
  EmpresaDocumentoExtracaoStatus,
  EmpresaDocumentosResponse,
  EmpresasDoCardResponse,
} from "@/types/empresas";

// ─── Query keys ─────────────────────────────────────────────────────────────

const EMPRESAS_DO_CARD_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "empresas"] as const;
const EMPRESA_DOCUMENTOS_KEY = (empresaId: string) =>
  ["sw", "empresas", empresaId, "documentos"] as const;

const empresaBase = (empresaId: string) => `/api/empresas/${encodeURIComponent(empresaId)}`;

// ─── Reads ──────────────────────────────────────────────────────────────────

/** `GET /api/clientes/{cliente_id}/empresas` (§D.1) — every empresa a card's
 *  titular, its partes (both lados) and any vendedor's linked cônjuge holds
 *  a participação in, deduped by empresa id, each with its owners, Cartão
 *  CNPJ slot summary, E1 verdict (`exige_certidoes`/`motivo`) and certidões
 *  rollup. Empty when there is no open atendimento or it is ambiguous. */
export function useEmpresasDoCard(clienteId: string | null) {
  return useQuery({
    queryKey: EMPRESAS_DO_CARD_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<EmpresasDoCardResponse>(
        `/api/clientes/${encodeURIComponent(clienteId as string)}/empresas`,
      ),
    enabled: !!clienteId,
  });
}

/** A terminal `extracao_status` is anything other than the two in-flight
 *  values — including `null` (a type extraction never reads, though today
 *  `cartao_cnpj` is the only `empresa_documentos` type and it always reads). */
function extracaoEmAndamento(status: EmpresaDocumentoExtracaoStatus | null): boolean {
  return status === "pendente" || status === "processando";
}

/**
 * `GET /api/empresas/{empresa_id}/documentos` (§D.3) — one empresa's Cartão
 * CNPJ documents (today: at most one, per `empresa_documentos.tipo_documento
 * CHECK IN ('cartao_cnpj')`, §A.3).
 *
 * Polls while ANY returned document is `pendente`/`processando` — mirrors
 * `useCardHub.ts::useExtracaoPollingInvalidation`'s own polling contract
 * (same interval, same reasoning): extraction runs server-side and
 * asynchronously, so the only way this panel learns a read landed is by
 * asking again. Stops the instant every document reaches a terminal state
 * (`ok` / `sem_dados` / `erro` / `null`) — never polls a card with nothing
 * in flight.
 */
export function useEmpresaDocumentos(empresaId: string | null) {
  return useQuery({
    queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId ?? "__none__"),
    queryFn: () =>
      api.get<EmpresaDocumentosResponse>(`${empresaBase(empresaId as string)}/documentos`),
    enabled: !!empresaId,
    refetchInterval: (q) => {
      const items = (q.state.data as EmpresaDocumentosResponse | undefined)?.items ?? [];
      return items.some((d) => extracaoEmAndamento(d.extracao_status)) ? 2500 : false;
    },
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

function invalidateEmpresaFamily(
  qc: ReturnType<typeof useQueryClient>,
  clienteId: string | null,
  empresaId?: string,
) {
  if (clienteId) void qc.invalidateQueries({ queryKey: EMPRESAS_DO_CARD_KEY(clienteId) });
  if (empresaId) void qc.invalidateQueries({ queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId) });
}

/** `POST /api/clientes/{cliente_id}/empresas` (§D.2) — manual link: upserts
 *  the empresa by CNPJ and a participação with `origem='manual'`. */
export function useAdicionarEmpresa(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AdicionarEmpresaBody) =>
      api.post<EmpresaCardItem>(
        `/api/clientes/${encodeURIComponent(clienteId)}/empresas`,
        body,
      ),
    onSuccess: () => invalidateEmpresaFamily(qc, clienteId),
  });
}

/** `POST /api/empresas/{empresa_id}/documentos` (§D.4, multipart, always
 *  `tipo_documento='cartao_cnpj'` — the only type this store accepts).
 *  Schedules extraction server-side; `useEmpresaDocumentos`'s own polling
 *  picks up the terminal status once it lands. */
export function useUploadEmpresaDocumento(empresaId: string, clienteId: string | null = null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      form.append("tipo_documento", "cartao_cnpj");
      return uploadMultipart<EmpresaDocumento>(`${empresaBase(empresaId)}/documentos`, form);
    },
    onSuccess: () => invalidateEmpresaFamily(qc, clienteId, empresaId),
  });
}

/**
 * `GET /api/empresas/{empresa_id}/documentos/{documento_id}/url` (§D.4) — a
 * 300s signed URL. Unlike the person-scoped `cliente_documentos`/
 * `imovel_documentos` siblings (`createCardHubHooks.useDocumentoMutations
 * .getUrl`, which takes an `intent: 'view'|'download'` so the LGPD access
 * log can tell the two apart), the contract names ONE route here — "view
 * opens it, download uses the same URL" — so this mints a single URL a
 * caller reuses for either action (`window.open` for view,
 * `baixarArquivo` for download); no `intent` param. Action-triggered, not
 * cached, hence a mutation.
 */
export function useEmpresaDocumentoUrl(empresaId: string) {
  return useMutation({
    mutationFn: (documentoId: string) =>
      api.get<DocumentoUrlResponse>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/url`,
      ),
  });
}

/**
 * `DELETE /api/empresas/{empresa_id}/documentos/{documento_id}` (§D.4).
 * `motivo` travels as a query param, not a JSON body — the SAME LGPD-access-
 * log transport `createCardHubHooks.useDocumentoMutations.remove` uses for
 * `cliente_documentos`/`imovel_documentos` (its own docblock: "`motivo`
 * travels as a REQUIRED query param … not a body"), which this empresa
 * store mirrors (§A.3 — "mirrors `imovel_documentos`"). The file is
 * soft-deleted (`deleted_at`), so this invalidates the same empresa-family
 * keys every other write here does.
 */
export function useRemoverEmpresaDocumento(empresaId: string, clienteId: string | null = null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ documentoId, motivo }: { documentoId: string; motivo: string }) =>
      api.delete<void>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: () => invalidateEmpresaFamily(qc, clienteId, empresaId),
  });
}

/**
 * The Cartão CNPJ slot's three extraction actions, bundled under one hook —
 * `reextrair` (re-run a stuck/never-run read, refused server-side while
 * pendente/processando), `confirmar` (D2 — stamps
 * `dados_confirmado_por/_em`) and `descartar` (marks
 * `extracao_descartada_*`; the file and its reading are both kept). Every
 * one invalidates this empresa's documentos AND the card's empresas list —
 * confirming/discarding a reading is what moves the row's own
 * `dados_confirmado_em` / E1 verdict.
 */
export function useEmpresaExtracao(empresaId: string, clienteId: string | null = null) {
  const qc = useQueryClient();
  const invalidate = () => invalidateEmpresaFamily(qc, clienteId, empresaId);

  const reextrair = useMutation({
    mutationFn: (documentoId: string) =>
      api.post<EmpresaDocumento>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/extrair`,
        {},
      ),
    onSuccess: invalidate,
  });

  const confirmar = useMutation({
    mutationFn: (documentoId: string) =>
      api.post<EmpresaDocumento>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/extracao/confirmar`,
        {},
      ),
    onSuccess: invalidate,
  });

  const descartar = useMutation({
    mutationFn: (documentoId: string) =>
      api.post<EmpresaDocumento>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/extracao/descartar`,
        {},
      ),
    onSuccess: invalidate,
  });

  return { reextrair, confirmar, descartar };
}

// Re-exported so a caller (e.g. `EmpresasSection`) can decide polling-related
// UI (a spinner, a "processando…" label) off the SAME predicate this file's
// own `useEmpresaDocumentos` polls against, rather than a second copy.
export { extracaoEmAndamento as empresaExtracaoEmAndamento };

/**
 * Mount alongside `useEmpresaDocumentos` purely to assert-in-tests / reason
 * about "polling stopped" — exposes whether THIS render still has a poll in
 * flight. Not required for the panel itself (the query's own
 * `refetchInterval` already governs refetching); kept as a small utility so
 * a consumer never has to recompute `extracaoEmAndamento` over the raw list
 * by hand.
 */
export function useEmpresaExtracaoEmAndamento(empresaId: string | null): boolean {
  const query = useEmpresaDocumentos(empresaId);
  const items = query.data?.items ?? [];
  return items.some((d) => extracaoEmAndamento(d.extracao_status));
}

// NOC-REMEDIATE[empresas-extracao-dependent-invalidation] — 2026-09-24
// `useCardHub.ts::useExtracaoPollingInvalidation` invalidates the whole
// qualificação/compradores/clientes family the INSTANT a cliente-scoped
// extraction transitions to terminal, because that read can silently fill
// fields several OTHER surfaces already have cached. A Cartão CNPJ read
// writes only `empresas`/`empresa_campo_conflitos` (group-level, §C.6) — no
// analogous cross-surface fan-out is wired here yet. Destination: this
// roadmap's P1, once a real consumer needs the E1 verdict to react to a
// landing mid-session rather than on the panel's own next open.
