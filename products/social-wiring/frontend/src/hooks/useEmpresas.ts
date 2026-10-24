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
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { jobPolling } from "@noctusai/lib";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { uploadMultipart } from "@/hooks/useCardHub";
import type { DocumentoUrlResponse } from "@/types/cardHub";
import type {
  AdicionarEmpresaBody,
  AtualizarEmpresaBody,
  AtualizarEmpresaResponse,
  DecidirParticipacaoBody,
  EditarParticipacaoBody,
  EmpresaCardItem,
  EmpresaChecklistResponse,
  EmpresaDocumento,
  EmpresaDocumentoExtracaoStatus,
  EmpresaDocumentosResponse,
  EmpresasDoCardResponse,
  RemoverEmpresaResponse,
} from "@/types/empresas";

// ─── Query keys ─────────────────────────────────────────────────────────────

const EMPRESAS_DO_CARD_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "empresas"] as const;
const EMPRESA_DOCUMENTOS_KEY = (empresaId: string) =>
  ["sw", "empresas", empresaId, "documentos"] as const;
const EMPRESA_CHECKLIST_KEY = (empresaId: string) =>
  ["sw", "empresas", empresaId, "checklist"] as const;

const empresaBase = (empresaId: string) => `/api/empresas/${encodeURIComponent(empresaId)}`;
const clienteEmpresaBase = (clienteId: string, empresaId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/empresas/${encodeURIComponent(empresaId)}`;

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
    ...jobPolling(
      (d: EmpresaDocumentosResponse | undefined) =>
        (d?.items ?? []).some((doc) => extracaoEmAndamento(doc.extracao_status)),
      2500,
    ),
  });
}

/** `GET /api/empresas/{empresa_id}/checklist` (slice D) — today, ONE item
 *  (`cartao_cnpj`). See `EmpresaChecklistItem`'s own docstring for the
 *  PJ-vendedor-conditional items this deliberately does NOT build yet. */
export function useEmpresaChecklist(empresaId: string | null) {
  return useQuery({
    queryKey: EMPRESA_CHECKLIST_KEY(empresaId ?? "__none__"),
    queryFn: () =>
      api.get<EmpresaChecklistResponse>(`${empresaBase(empresaId as string)}/checklist`),
    enabled: !!empresaId,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────────────

/** The same family as `invalidateEmpresaFamily`, as keys for a cache-write mutation's settle. */
function empresaFamilyKeys(clienteId: string | null, empresaId?: string, comDocumentos = true) {
  return [
    ...(clienteId ? [EMPRESAS_DO_CARD_KEY(clienteId)] : []),
    ...(empresaId
      ? [...(comDocumentos ? [EMPRESA_DOCUMENTOS_KEY(empresaId)] : []), EMPRESA_CHECKLIST_KEY(empresaId)]
      : []),
  ];
}

/** `items` rows are keyed by `empresa.id`, not `id`. */
const empresaIdOf = (i: EmpresaCardItem) => i.empresa.id;

/** Edit ONE empresa row of the card's list. */
const naEmpresa = (
  old: EmpresasDoCardResponse | undefined,
  empresaId: string,
  edit: (item: EmpresaCardItem) => EmpresaCardItem,
) => listOps.within(old, "items", (l) => listOps.update(l, empresaId, edit, empresaIdOf));

function invalidateEmpresaFamily(
  qc: ReturnType<typeof useQueryClient>,
  clienteId: string | null,
  empresaId?: string,
) {
  if (clienteId) void qc.invalidateQueries({ queryKey: EMPRESAS_DO_CARD_KEY(clienteId) });
  if (empresaId) {
    void qc.invalidateQueries({ queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId) });
    void qc.invalidateQueries({ queryKey: EMPRESA_CHECKLIST_KEY(empresaId) });
  }
}

/** `POST /api/clientes/{cliente_id}/empresas` (§D.2) — manual link: upserts
 *  the empresa by CNPJ and a participação with `origem='manual'`. */
export function useAdicionarEmpresa(clienteId: string) {
  return useCacheWriteMutation<EmpresaCardItem, AdicionarEmpresaBody>({
    mutationFn: (body) =>
      api.post<EmpresaCardItem>(
        `/api/clientes/${encodeURIComponent(clienteId)}/empresas`,
        body,
      ),
    targets: [
      {
        queryKey: EMPRESAS_DO_CARD_KEY(clienteId),
        commit: (old: EmpresasDoCardResponse | undefined, saved) =>
          listOps.within(old, "items", (l) =>
            l.some((i) => i.empresa.id === saved.empresa.id) ? l : listOps.append(l, saved),
          ),
      },
    ],
  });
}

/** `cliente_empresa_participacoes`' decision columns as the PATCH below
 *  returns them (the updated row). */
interface ParticipacaoDecidida {
  confirmado_em: string | null;
  descartado_em: string | null;
}

interface DecidirParticipacaoVars {
  empresaId: string;
  body: DecidirParticipacaoBody;
}

/** One owner's decision written into the card's cached empresas list. */
function comDecisao(
  old: EmpresasDoCardResponse | undefined,
  { empresaId, body }: DecidirParticipacaoVars,
  decisao: ParticipacaoDecidida,
): EmpresasDoCardResponse | undefined {
  return naEmpresa(old, empresaId, (item) => ({
    ...item,
    owners: item.owners.map((o) => (o.cliente_id !== body.participante_cliente_id ? o : { ...o, ...decisao })),
  }));
}

/** `PATCH /api/clientes/{cliente_id}/empresas/{empresa_id}/participacao`
 *  (migration 299) — confirm / dismiss ("Não é do vendedor") / reopen a
 *  Serasa-Crednet participação of a person on this card. A confirmed one
 *  enters the generated contract with its company's certidões. The decision
 *  is drawn on the owner's row at once and committed from the server's
 *  answer; the list then re-reads in the background (the E1 verdict /
 *  `certificando` are server-computed). */
export function useDecidirParticipacao(clienteId: string) {
  return useCacheWriteMutation<ParticipacaoDecidida, DecidirParticipacaoVars>({
    mutationFn: ({ empresaId, body }) =>
      api.patch<ParticipacaoDecidida>(
        `${clienteEmpresaBase(clienteId, empresaId)}/participacao`,
        body,
      ),
    targets: [
      {
        queryKey: EMPRESAS_DO_CARD_KEY(clienteId),
        optimistic: (old: EmpresasDoCardResponse | undefined, vars) => {
          const agora = new Date().toISOString();
          const { decisao } = vars.body;
          return comDecisao(old, vars, {
            confirmado_em: decisao === "confirmar" ? agora : null,
            descartado_em: decisao === "descartar" ? agora : null,
          });
        },
        commit: (old: EmpresasDoCardResponse | undefined, result, vars) =>
          comDecisao(old, vars, {
            confirmado_em: result?.confirmado_em ?? null,
            descartado_em: result?.descartado_em ?? null,
          }),
      },
    ],
  });
}

interface EditarParticipacaoVars {
  empresaId: string;
  body: EditarParticipacaoBody;
}

/** `PATCH .../participacao/dados` — a human types the participação % /
 *  "desde" (a field is never upload-only). Drawn on the owner's row at once,
 *  committed from the server's answer. */
export function useEditarParticipacao(clienteId: string) {
  const aplicar = (
    old: EmpresasDoCardResponse | undefined,
    { empresaId, body }: EditarParticipacaoVars,
    valores: { participacao_pct?: number | null; desde?: string | null },
  ) =>
    naEmpresa(old, empresaId, (item) => ({
      ...item,
      owners: item.owners.map((o) =>
        o.cliente_id !== body.participante_cliente_id ? o : { ...o, ...valores },
      ),
    }));
  const pick = (b: { participacao_pct?: unknown; desde?: unknown }) => ({
    ...("participacao_pct" in b ? { participacao_pct: b.participacao_pct as number | null } : {}),
    ...("desde" in b ? { desde: b.desde as string | null } : {}),
  });
  return useCacheWriteMutation<
    { participacao_pct: number | string | null; desde: string | null },
    EditarParticipacaoVars
  >({
    mutationFn: ({ empresaId, body }) =>
      api.patch(`${clienteEmpresaBase(clienteId, empresaId)}/participacao/dados`, body),
    targets: [
      {
        queryKey: EMPRESAS_DO_CARD_KEY(clienteId),
        optimistic: (old: EmpresasDoCardResponse | undefined, vars) => aplicar(old, vars, pick(vars.body)),
        commit: (old: EmpresasDoCardResponse | undefined, result, vars) =>
          aplicar(old, vars, {
            participacao_pct:
              result?.participacao_pct == null ? null : Number(result.participacao_pct),
            desde: result?.desde ?? null,
          }),
      },
    ],
  });
}

/** `PATCH /api/empresas/{empresa_id}` (slice D) — razão social, nome
 *  fantasia, CNPJ, situação cadastral, data da situação. The response's
 *  `pendente_confirmacao` tells the caller whether the edit landed or was
 *  deferred to admin adjudication (`empresa_campo_conflitos`) — the row
 *  itself is unchanged when every touched field was deferred. */
export function useAtualizarEmpresa(empresaId: string, clienteId: string | null = null) {
  return useCacheWriteMutation<AtualizarEmpresaResponse, AtualizarEmpresaBody>({
    mutationFn: (body) => api.patch<AtualizarEmpresaResponse>(empresaBase(empresaId), body),
    // The saved empresa replaces the card row's `empresa`; the verdict (exige_certidoes, cartao, certidoes) is the server's.
    targets: clienteId
      ? [
          {
            queryKey: EMPRESAS_DO_CARD_KEY(clienteId),
            commit: (old: EmpresasDoCardResponse | undefined, saved) => {
              const { pendente_confirmacao: _p, ...empresa } = saved;
              return naEmpresa(old, empresaId, (i) => ({ ...i, empresa: { ...i.empresa, ...empresa } }));
            },
          },
        ]
      : [],
    invalidate: empresaFamilyKeys(null, empresaId),
  });
}

/** `DELETE /api/clientes/{cliente_id}/empresas/{empresa_id}` (slice D) —
 *  admin/owner only (403 for anyone else, enforced server-side). Unlinks
 *  this cliente from the empresa; the empresa row (and its Cartão CNPJ)
 *  is hard-deleted only when this was the last participação. */
export function useRemoverEmpresa(clienteId: string) {
  return useCacheWriteMutation<RemoverEmpresaResponse, string>({
    mutationFn: (empresaId) =>
      api.delete<RemoverEmpresaResponse>(clienteEmpresaBase(clienteId, empresaId)),
    // The participação is always unlinked from this card, so the row leaves the list.
    targets: (empresaId) => [
      {
        queryKey: EMPRESAS_DO_CARD_KEY(clienteId),
        optimistic: (old: EmpresasDoCardResponse | undefined) =>
          listOps.within(old, "items", (l) => listOps.remove(l, empresaId, empresaIdOf)),
      },
    ],
  });
}

/** `POST /api/empresas/{empresa_id}/documentos` (§D.4, multipart, always
 *  `tipo_documento='cartao_cnpj'` — the only type this store accepts).
 *  Schedules extraction server-side; `useEmpresaDocumentos`'s own polling
 *  picks up the terminal status once it lands. */
export function useUploadEmpresaDocumento(empresaId: string, clienteId: string | null = null) {
  return useCacheWriteMutation<EmpresaDocumento, File>({
    mutationFn: (file) => {
      const form = new FormData();
      form.append("file", file);
      form.append("tipo_documento", "cartao_cnpj");
      return uploadMultipart<EmpresaDocumento>(`${empresaBase(empresaId)}/documentos`, form);
    },
    targets: [
      {
        queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId),
        commit: (old: EmpresaDocumentosResponse | undefined, saved) =>
          listOps.within(old, "items", (l) => listOps.replace(l, saved.id, saved)),
      },
    ],
    // documentos is a target of this write: its settle already refreshes it
    invalidate: empresaFamilyKeys(clienteId, empresaId, false),
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
  return useMutation({ // noc-allow: invalidate-only — a read-on-click (signed URL), writes nothing and caches nothing
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
  return useCacheWriteMutation<void, { documentoId: string; motivo: string }>({
    mutationFn: ({ documentoId, motivo }) =>
      api.delete<void>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    targets: ({ documentoId }) => [
      {
        queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId),
        optimistic: (old: EmpresaDocumentosResponse | undefined) =>
          listOps.within(old, "items", (l) => listOps.remove(l, documentoId)),
      },
    ],
    // documentos is a target of this write: its settle already refreshes it
    invalidate: empresaFamilyKeys(clienteId, empresaId, false),
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
  const reextrair = useCacheWriteMutation<EmpresaDocumento, string>({
    mutationFn: (documentoId) =>
      api.post<EmpresaDocumento>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/extrair`,
        {},
      ),
    targets: (documentoId) => [
      {
        queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId),
        commit: (old: EmpresaDocumentosResponse | undefined, saved) =>
          listOps.within(old, "items", (l) => listOps.patch(l, documentoId, saved)),
      },
    ],
    // documentos is a target of this write: its settle already refreshes it
    invalidate: empresaFamilyKeys(clienteId, empresaId, false),
  });

  const confirmar = useCacheWriteMutation<EmpresaDocumento, string>({
    mutationFn: (documentoId) =>
      api.post<EmpresaDocumento>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/extracao/confirmar`,
        {},
      ),
    targets: (documentoId) => [
      {
        queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId),
        commit: (old: EmpresaDocumentosResponse | undefined, saved) =>
          listOps.within(old, "items", (l) => listOps.patch(l, documentoId, saved)),
      },
    ],
    // documentos is a target of this write: its settle already refreshes it
    invalidate: empresaFamilyKeys(clienteId, empresaId, false),
  });

  const descartar = useCacheWriteMutation<EmpresaDocumento, string>({
    mutationFn: (documentoId) =>
      api.post<EmpresaDocumento>(
        `${empresaBase(empresaId)}/documentos/${encodeURIComponent(documentoId)}/extracao/descartar`,
        {},
      ),
    targets: (documentoId) => [
      {
        queryKey: EMPRESA_DOCUMENTOS_KEY(empresaId),
        commit: (old: EmpresaDocumentosResponse | undefined, saved) =>
          listOps.within(old, "items", (l) => listOps.patch(l, documentoId, saved)),
      },
    ],
    // documentos is a target of this write: its settle already refreshes it
    invalidate: empresaFamilyKeys(clienteId, empresaId, false),
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

/**
 * P1/883 (2026-09-25) — the empresas-list sibling of `useImovelDados.
 * useImovelExtracaoPollingInvalidation`. `useEmpresaDocumentos` above
 * already polls THIS document's own `extracao_status` (so
 * `EmpresaCartaoSlot`'s "Lendo…" state updates), but nothing invalidated
 * `EMPRESAS_DO_CARD_KEY` — the SEPARATE query carrying the E1 verdict
 * (`situacao_cadastral`/`motivo`/`exige_certidoes`) `dados_service.
 * aplicar_cartao`'s group-level D1 apply fills on landing. Left unwired,
 * `EmpresasSection`'s badge kept showing the pre-extraction verdict until
 * a hard reload — the same shape the imóvel G2 bug had. Closes
 * NOC-REMEDIATE[empresas-extracao-dependent-invalidation] (2026-09-24):
 * the badge IS the real consumer that marker deferred to.
 *
 * Mount alongside `useEmpresaDocumentos(empresaId)` — same query key, so
 * this shares that hook's cache/fetch rather than doubling the request.
 * Returns nothing: callers keep using `useEmpresaDocumentos`'s own result
 * for render data; this hook is mounted purely for the polling +
 * invalidation side effect.
 */
export function useEmpresaExtracaoPollingInvalidation(
  empresaId: string | null,
  clienteId: string | null,
): void {
  const qc = useQueryClient();
  const prevStatusRef = useRef<Map<string, EmpresaDocumentoExtracaoStatus | null>>(new Map());
  const query = useEmpresaDocumentos(empresaId);

  useEffect(() => {
    if (!empresaId || !query.data) return;
    const prev = prevStatusRef.current;
    const items = query.data.items;
    const proximo = new Map(items.map((d) => [d.id, d.extracao_status] as const));
    const transicionou = items.some((d) => {
      const antes = prev.get(d.id);
      // `undefined` = this document's first appearance in the map (the
      // panel just mounted, or it was just uploaded) — never itself a
      // transition; only a PREVIOUSLY-seen pending status turning terminal
      // counts, same rule `useImovelDados`'s sibling hook applies.
      return antes !== undefined && extracaoEmAndamento(antes) && !extracaoEmAndamento(d.extracao_status);
    });
    prevStatusRef.current = proximo;
    if (transicionou) {
      invalidateEmpresaFamily(qc, clienteId, empresaId);
    }
  }, [empresaId, clienteId, query.data, qc]);
}
