/**
 * useCardHub — the ONE file every card query/mutation lives in
 * (`lead-card-hub-p2-PROJECT.md` §0 ruling S3: `components/card/**` is
 * presentational-only, zero data fetching; this file is where that data
 * access is confined). Mirrors `useClientes.ts`'s conventions exactly
 * (bare-payload `api.get<T>`, `@noctusai/seed/infra`, manual query-string
 * building, `{items, total}` house envelope) — the sibling P1 file for this
 * same feature area.
 *
 * The backend for this contract is being built in a PARALLEL worktree and
 * does not exist on this branch — every shape traces to PROJECT.md §3,
 * never to observed behaviour.
 *
 * Optimistic updates: checklist-item toggles and the tag full-set PUT
 * (`useSetClienteTagsMutation`) update the cache immediately and roll back
 * visibly (via `onError` restoring the pre-mutation snapshot + surfacing
 * the error to the caller) on failure — never a silently-swallowed
 * mutation, per the brief's mandatory rule.
 */
import { useEffect, useRef } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";
import { createCardHubHooks, flattenTimeline } from "@noctusai/lib/components";
import type { CardHubApi } from "@noctusai/lib/components";

import { apiUrl } from "@/lib/apiBase";
import type {
  Agendamento,
  AgendamentoCreateBody,
  AgendamentoPatchBody,
  ChecklistOrigem,
  Documento,
  ItemsEnvelope,
  CardResumo,
  DocumentoChecklist,
  DocumentoChecklistItem,
  Comprador,
  CompradoresResponse,
  LadoParte,
  ImovelBusca,
  Roteiro,
  RoteiroCreateBody,
  RoteiroPatchBody,
  Visita,
  VisitaPatchBody,
  VisitaPropostaBody,
} from "@/types/cardHub";
import type { QualificacaoCompletude } from "@/types/qualificacaoCompletude";
import {
  apenasDadosPessoais,
  type DadosPessoais,
} from "@/components/card/DadosPessoaisForm";

// ─── The seed card hub — the generic slice ─────────────────────────────────
//
// Resumo, timeline, notas, tags, membros, checklists, documentos and
// checklist-extras are the seed's (`createCardHubHooks`, `@noctusai/lib/
// components` — MOVED there from this file, wave-a Slice C/F,
// `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`). This
// file keeps the SW-only hooks (agendamentos, roteiros, imóveis, documento
// checklist, qualificação, compradores, dados pessoais, conflitos) and
// re-exports the generated ones under their historical names below, so no
// consumer changes.

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Multipart POST — SW's own, kept verbatim through the seed's `upload` seam.
 *
 * Raw `fetch` with the supabase session header and NO content-type (the
 * browser sets the multipart boundary). Kept rather than the seed client's
 * `upload` because SW surfaces the server's `error.message` VERBATIM in its
 * toasts (e.g. the upload-size refusal — a platform constant this UI does not
 * own), where the seed client prefixes `[<status>] `; the swap onto the seed
 * hooks is a zero-behaviour-change move.
 */
async function uploadMultipart<T>(path: string, form: FormData): Promise<T> {
  const headers = await getAuthHeader();
  const response = await fetch(apiUrl(path), { method: "POST", headers, body: form });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.error?.message ?? `Erro HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

/**
 * The seed hooks' api seam. JSON verbs delegate to the seed client LAZILY
 * (looked up per call, never captured), so the client stays the one
 * `@noctusai/seed/infra` provides — including under a test's module mock.
 */
const cardHubApi: CardHubApi = {
  get: (...args: Parameters<CardHubApi["get"]>) => api.get(...args),
  post: (...args: Parameters<CardHubApi["post"]>) => api.post(...args),
  patch: (...args: Parameters<CardHubApi["patch"]>) => api.patch(...args),
  put: (...args: Parameters<CardHubApi["put"]>) => api.put(...args),
  delete: (...args: Parameters<CardHubApi["delete"]>) => api.delete(...args),
  upload: uploadMultipart,
};

const cardHub = createCardHubHooks<CardResumo>(
  {
    // Byte-identical to SW's historical keys — every SW-only hook below shares
    // this one cache family, so every existing invalidation still lands.
    rootKey: ["sw", "cardHub"],
    basePath: "/api/clientes",
    entityLabel: "cliente",
    // An `rg`/`cpf` upload satisfies that mandatory item — the documento
    // checklist's ticks DERIVE from documento existence too.
    documentoInvalidates: ["documento-checklist"],
  },
  cardHubApi,
);

// ─── Query keys ─────────────────────────────────────────────────────────────

const { keys } = cardHub;
const ROOT_KEY = keys.root;
const FAMILY_KEY = keys.family;
const CARD_KEY = keys.card;
const DOCUMENTOS_KEY = keys.documentos;
const DOC_CHECKLIST_KEY = (clienteId: string) =>
  [...FAMILY_KEY(clienteId), "documento-checklist"] as const;

/**
 * 🔴 NOT nested under `FAMILY_KEY`. `FAMILY_KEY(clienteId)` is scoped to the
 * CARD's own titular; qualificação-completude is fetched per PARTY
 * (`parte.cliente_id`), which is routinely a different person's id than the
 * card that is open. Rooting it here instead of under the titular's family
 * means invalidating it from `useCompradorMutations` (which knows only the
 * titular's id) still reaches every party's cached entry.
 */
const QUALIFICACAO_ROOT_KEY = [...ROOT_KEY, "qualificacao"] as const;
const QUALIFICACAO_KEY = (clienteId: string) =>
  [...QUALIFICACAO_ROOT_KEY, clienteId] as const;
const AGENDAMENTOS_KEY = (clienteId: string) =>
  [...FAMILY_KEY(clienteId), "agendamentos"] as const;
const ROTEIROS_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "roteiros"] as const;
const IMOVEIS_BUSCA_KEY = (termo: string) => [...ROOT_KEY, "imoveisBusca", termo] as const;
/** 🔴 The SIDE is part of the key. Both tabs hit the same endpoint, so a
 *  shared cache entry would render the vendedores under Compradores. */
const COMPRADORES_KEY = (clienteId: string, lado: LadoParte = "comprador") =>
  [...FAMILY_KEY(clienteId), "compradores", lado] as const;
/**
 * 🔴 NOT nested under `FAMILY_KEY`, same reasoning `QUALIFICACAO_ROOT_KEY`
 * gives: the org-wide admin queue (`useConflitosPendentes()`, no
 * `clienteId`) and a per-person read (`useConflitosPendentes(clienteId)`)
 * are two different queries under ONE root, so deciding a conflict can
 * invalidate BOTH with a single root-prefix `invalidateQueries` call
 * regardless of which one the caller currently has mounted.
 */
const CONFLITOS_ROOT_KEY = [...ROOT_KEY, "conflitos"] as const;
const CONFLITOS_KEY = (clienteId?: string) =>
  [...CONFLITOS_ROOT_KEY, clienteId ?? "__org__"] as const;

const clienteBase = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;

// ─── Generated (seed) hooks, under SW's historical names ───────────────────

export { flattenTimeline };
export const useCardResumo = cardHub.useCardResumo;
export const useTimeline = cardHub.useTimeline;
export const useNotaMutations = cardHub.useNotaMutations;
export const useTags = cardHub.useTags;
export const useTagCatalogMutations = cardHub.useTagCatalogMutations;
/** PUT the full tag set for one cliente — optimistic, rolled back on failure. */
export const useSetClienteTagsMutation = cardHub.useSetTagsMutation;
export const useCardMembros = cardHub.useCardMembros;
/** PUT the card's membros. SW's member source is `lead_corretores`, so the
 *  body key is `lead_corretor_ids` (D10 — points at lead_corretores). */
export function useSetCardMembrosMutation(clienteId: string) {
  return cardHub.useSetMembrosMutation(clienteId, "lead_corretor_ids");
}
export const useChecklists = cardHub.useChecklists;
export const useChecklistMutations = cardHub.useChecklistMutations;
export const useDocumentos = cardHub.useDocumentos;
export const useTiposDocumento = cardHub.useTiposDocumento;
export const useDocumentoAcessos = cardHub.useDocumentoAcessos;
/** Upload / remove (`motivo` query param) / signed URL / re-extract. An
 *  attachment write also invalidates SW's `documento-checklist`. */
export const useDocumentoMutations = cardHub.useDocumentoMutations;
export const useChecklistExtras = cardHub.useChecklistExtras;
export const useChecklistExtraMutations = cardHub.useChecklistExtraMutations;

export type { ChecklistOrigem };



// ─── Agendamentos (migration 061 — many per atendimento) ──────────────────

export function useAgendamentos(clienteId: string | null) {
  return useQuery({
    queryKey: AGENDAMENTOS_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api
        .get<ItemsEnvelope<Agendamento>>(`${clienteBase(clienteId as string)}/agendamentos`)
        .then((r) => r.items),
    enabled: !!clienteId,
  });
}

/**
 * Create / edit / delete. Every one invalidates the agendamentos list AND the
 * card (its badges) — and nothing else, for the same reason the checklist
 * mutations were narrowed: an appointment cannot change a document.
 */
export function useAgendamentoMutations(clienteId: string) {
  const qc = useQueryClient();
  const base = clienteBase(clienteId);
  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: AGENDAMENTOS_KEY(clienteId) }),
      qc.invalidateQueries({ queryKey: CARD_KEY(clienteId) }),
    ]);

  const create = useMutation({
    mutationFn: (body: AgendamentoCreateBody) =>
      api.post<Agendamento>(`${base}/agendamentos`, body),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AgendamentoPatchBody }) =>
      api.patch<Agendamento>(`${base}/agendamentos/${encodeURIComponent(id)}`, body),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`${base}/agendamentos/${encodeURIComponent(id)}`),
    // Optimistic: a cancelled appointment lingering while the round-trip
    // completes reads as "the delete failed", and invites a second click.
    onMutate: async (id: string) => {
      await qc.cancelQueries({ queryKey: AGENDAMENTOS_KEY(clienteId) });
      const previous = qc.getQueryData<Agendamento[]>(AGENDAMENTOS_KEY(clienteId));
      if (previous) {
        qc.setQueryData<Agendamento[]>(
          AGENDAMENTOS_KEY(clienteId),
          previous.filter((a) => a.id !== id),
        );
      }
      return { previous };
    },
    onError: (_err, _id, context) => {
      if (context?.previous) qc.setQueryData(AGENDAMENTOS_KEY(clienteId), context.previous);
    },
    onSettled: invalidate,
  });

  return { create, update, remove };
}

// ─── Roteiros e visitas (migration 082) ─────────────────────────────────────

export function useRoteiros(clienteId: string | null) {
  return useQuery({
    queryKey: ROTEIROS_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api
        .get<ItemsEnvelope<Roteiro>>(`${clienteBase(clienteId as string)}/roteiros`)
        .then((r) => r.items),
    enabled: !!clienteId,
  });
}

/**
 * The live property search behind every imóvel picker — "Criar Roteiro", and
 * the Negociação panel's deal property.
 *
 * 🔴 IT USED TO CALL `GET /api/imoveis?search=`, AND THAT WAS THE BUG.
 * That endpoint reads `social_wiring.imoveis`, the Vista MIRROR, which holds
 * only what the catalog lists TODAY. On prod (2026-08-25) the registry held
 * 3017 imóveis against the mirror's 2008 — so 35% of everything the schema
 * would accept could not be typed into any picker. And it was the wrong 35%:
 * an imóvel leaves the Vista catalog when it is SOLD, i.e. exactly when its
 * matrícula, its negociação and its contract are being handled.
 *
 * `GET /api/imoveis/busca` searches the REGISTRY ∪ the mirror and labels each
 * hit with its `fonte` and `ativo_no_vista`. The catalog browser keeps the old
 * endpoint — a person browsing what is FOR SALE does not want sold properties
 * in the grid, so the two are separate on purpose.
 *
 * `enabled` gates on two characters: a one-character term matches most of the
 * catalog, and paying a round trip to render a list nobody can use is worse
 * than showing the hint. The server refuses a shorter term (422) rather than
 * answering an empty list, so the gate and the backstop agree.
 *
 * `placeholderData: keepPreviousData` — the queryKey is the DEBOUNCED term,
 * so every keystroke's settle is a brand-new key with no cache of its own.
 * Without this, the popover's list emptied and re-showed "Buscando..." on
 * every keystroke's settle, even while the PREVIOUS term's results were
 * still perfectly good to look at; this keeps them on screen (as
 * `isPlaceholderData`) until the new term's answer arrives, so `busca.data`
 * never goes `undefined` mid-typing.
 */
export function useImoveisBusca(termo: string) {
  const limpo = termo.trim();
  return useQuery({
    queryKey: IMOVEIS_BUSCA_KEY(limpo),
    queryFn: () =>
      api.get<{ items: ImovelBusca[] }>(
        `/api/imoveis/busca?q=${encodeURIComponent(limpo)}&limit=10`,
      ),
    enabled: limpo.length >= 2,
    placeholderData: keepPreviousData,
    // The result for a given term cannot change while someone is typing, and
    // backspacing to a previous term is the common move.
    staleTime: 30_000,
  });
}

// 🔴 `POST /api/imoveis/{codigo}/registrar`'s mutation hook (migration 149)
// moved to `hooks/useImovelRegistro.ts` (migration 159): the endpoint now
// REQUIRES a full address body, and the picker also needs the paired
// "did you mean one of these?" near-duplicate check
// (`GET /api/imoveis/busca/duplicatas`) — both live together there, in
// their own file, so this shared card-hub file's query-invalidation
// surface stays untouched by the imóvel-registration flow. `IMOVEIS_BUSCA_
// KEY`/`useImoveisBusca` above are unaffected and stay exactly where they
// were; the new file's mutation invalidates the SAME `[...ROOT_KEY,
// "imoveisBusca"]` prefix by its literal value.

/**
 * Create / rename / delete a roteiro, reorder it, and record each visita's
 * outcome.
 *
 * Every one invalidates the roteiros list AND the timeline: a visita outcome
 * IS a timeline entry (derived from `feedback_em`), so leaving the timeline
 * stale would show the card contradicting itself in two panes.
 */
export function useRoteiroMutations(clienteId: string) {
  const qc = useQueryClient();
  const base = clienteBase(clienteId);
  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ROTEIROS_KEY(clienteId) }),
      qc.invalidateQueries({ queryKey: [...FAMILY_KEY(clienteId), "timeline"] }),
    ]);

  const create = useMutation({
    mutationFn: (body: RoteiroCreateBody) => api.post<Roteiro>(`${base}/roteiros`, body),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: RoteiroPatchBody }) =>
      api.patch<Roteiro>(`${base}/roteiros/${encodeURIComponent(id)}`, body),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`${base}/roteiros/${encodeURIComponent(id)}`),
    // Optimistic, same reasoning as the agendamento delete: a removed route
    // lingering through the round trip reads as a failed delete and invites a
    // second click.
    onMutate: async (id: string) => {
      await qc.cancelQueries({ queryKey: ROTEIROS_KEY(clienteId) });
      const previous = qc.getQueryData<Roteiro[]>(ROTEIROS_KEY(clienteId));
      if (previous) {
        qc.setQueryData<Roteiro[]>(
          ROTEIROS_KEY(clienteId),
          previous.filter((r) => r.id !== id),
        );
      }
      return { previous };
    },
    onError: (_err, _id, context) => {
      if (context?.previous) qc.setQueryData(ROTEIROS_KEY(clienteId), context.previous);
    },
    onSettled: invalidate,
  });

  const reorder = useMutation({
    mutationFn: ({ id, visitaIds }: { id: string; visitaIds: string[] }) =>
      api.put<Roteiro>(`${base}/roteiros/${encodeURIComponent(id)}/ordem`, {
        visita_ids: visitaIds,
      }),
    onSuccess: invalidate,
  });

  const patchVisita = useMutation({
    mutationFn: ({
      roteiroId,
      visitaId,
      body,
    }: {
      roteiroId: string;
      visitaId: string;
      body: VisitaPatchBody;
    }) =>
      api.patch<Visita>(
        `${base}/roteiros/${encodeURIComponent(roteiroId)}/visitas/${encodeURIComponent(visitaId)}`,
        body,
      ),
    onSuccess: invalidate,
  });

  // A roteiro's property list was fixed at creation: `POST /roteiros` seeds the
  // visitas from `imoveis[]` and nothing could add or drop one afterwards,
  // even though both routes have always existed.
  const addVisita = useMutation({
    mutationFn: ({ roteiroId, codigo }: { roteiroId: string; codigo: string }) =>
      api.post<Visita>(
        `${base}/roteiros/${encodeURIComponent(roteiroId)}/visitas`,
        { codigo },
      ),
    onSuccess: invalidate,
  });

  const removeVisita = useMutation({
    mutationFn: ({ roteiroId, visitaId }: { roteiroId: string; visitaId: string }) =>
      api.delete(
        `${base}/roteiros/${encodeURIComponent(roteiroId)}/visitas/${encodeURIComponent(visitaId)}`,
      ),
    onSuccess: invalidate,
  });

  // 🔴 ITS OWN ROUTE, not a field on `patchVisita` — migration 104 keeps
  // "did the visit happen" and "did it produce an accepted offer" as separate
  // axes, and one body carrying both invites a client that cannot say which
  // of the two it meant to change.
  //
  // Invalidates the NEGOCIAÇÃO too: accepting writes
  // `atendimento_negociacao.imovel_codigo`, so leaving that query stale would
  // show the Negociação panel contradicting the roteiro in the next tab.
  const patchProposta = useMutation({
    mutationFn: ({
      roteiroId,
      visitaId,
      body,
    }: {
      roteiroId: string;
      visitaId: string;
      body: VisitaPropostaBody;
    }) =>
      api.patch<Visita>(
        `${base}/roteiros/${encodeURIComponent(roteiroId)}/visitas/${encodeURIComponent(visitaId)}/proposta`,
        body,
      ),
    onSuccess: () =>
      Promise.all([
        invalidate(),
        qc.invalidateQueries({
          queryKey: ["sw", "clientes", clienteId, "negociacao"],
        }),
      ]),
  });

  return {
    create,
    update,
    remove,
    reorder,
    patchVisita,
    patchProposta,
    addVisita,
    removeVisita,
  };
}

/**
 * The "Gerar Roteiro" download.
 *
 * NOT `api.get` — the seed client parses JSON, and this endpoint answers with
 * `application/pdf`. Fetched with the session token and handed to the browser
 * as a blob, so a failure surfaces as a thrown error the caller can toast
 * rather than a downloaded file containing an error page.
 */
export async function baixarRoteiroPdf(clienteId: string, roteiroId: string): Promise<void> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const resp = await fetch(
    apiUrl(`${clienteBase(clienteId)}/roteiros/${encodeURIComponent(roteiroId)}/pdf`),
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!resp.ok) {
    throw new Error(`Falha ao gerar o roteiro (HTTP ${resp.status})`);
  }

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `roteiro-${roteiroId.slice(0, 8)}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ─── Documento checklist (migration 067) ──────────────────────────────────

/**
 * The permanent document checklist. Always six items, defined server-side —
 * there is no create/delete, only ticking.
 */
export function useDocumentoChecklist(clienteId: string | null) {
  return useQuery({
    queryKey: DOC_CHECKLIST_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<DocumentoChecklist>(
        `${clienteBase(clienteId as string)}/documento-checklist`,
      ),
    enabled: !!clienteId,
  });
}

/**
 * Set or CLEAR the human override on one item.
 *
 * `concluido: null` clears it and hands the item back to the server-side
 * derivation. Without that, the first person to touch an item would pin it
 * forever — including pinning a `false` onto a client who later supplies the
 * very data the item asks for.
 *
 * Optimistic by design: a checkbox that waits for a round-trip before moving
 * feels broken, and this one is ticked six times in a row while reading a
 * document off a screen. `onError` restores the snapshot, so a rejected write
 * un-ticks itself rather than leaving a lie on screen.
 *
 * Invalidates ONLY this list — a collected RG does not change a note, a tag or
 * an appointment, and a wider invalidation is what made the card flash.
 */
/**
 * Accept or turn down a low-confidence extracted value (migration 069).
 *
 * NOT optimistic, unlike the checklist tick beside it. The tick is a local
 * assertion that can be rolled back invisibly; this one writes a birthdate to
 * a person's record off a machine reading, and showing it as applied before
 * the server agreed would be the one moment a wrong value looks confirmed.
 *
 * Invalidates the checklist (the tick and the prompt both change) AND the
 * documents list (the discard flag lives on a document row). Migration 110 —
 * ALSO the qualificação-completude family: applying a suggested `estado_civil`
 * / `regime_bens` / `rg` / `cpf` moves this exact endpoint's answer, and this
 * mutation is the other write path into those columns besides
 * `useDadosPessoaisMutation` below.
 */
export function useExtracaoSugestaoMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentoId,
      acao,
      itemKey,
    }: {
      documentoId: string;
      acao: "confirmar" | "descartar";
      /**
       * Which extracted field this decision is about. Omitted means
       * `data_nascimento` — the only field these routes knew about when
       * they shipped, so an older caller keeps working.
       */
      itemKey?: string;
    }) =>
      api.post<{ documento_id: string }>(
        `${clienteBase(clienteId)}/documentos/${documentoId}/extracao/${acao}`,
        itemKey ? { item_key: itemKey } : {},
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: DOC_CHECKLIST_KEY(clienteId) });
      void qc.invalidateQueries({ queryKey: DOCUMENTOS_KEY(clienteId) });
      void qc.invalidateQueries({ queryKey: QUALIFICACAO_ROOT_KEY });
    },
  });
}

// 🔴 Bug 2 (prod card 755253934) — extraction runs SERVER-SIDE and
// ASYNCHRONOUSLY. `useDocumentoMutations().upload`'s own `onSuccess`
// invalidates `documentos`/`card`/`documento-checklist` the INSTANT the
// upload request completes — before the OCR job that fills `clientes`
// fields has even started. So the first refetch it triggers still reads the
// PRE-extraction record, and nothing after that ever asks again: "Qualificação
// para contrato", a party's "Dados obrigatórios" progress and negociação kept
// showing the upload-time snapshot until a hard reload. A previous pass
// (9ce161f82) invalidated `QUALIFICACAO_ROOT_KEY` from `useDadosPessoaisMutation`
// / `useDecidirConflitoMutation` — both CLIENT-initiated writes — which never
// fires for a write the SERVER makes on its own schedule.
const EXTRACAO_POLL_INTERVAL_MS = 2500;
// A stuck extraction job (or a document type that never resolves) stops
// polling after this — "briefly (bounded)", never forever. The operator
// still has the manual "Reenviar para leitura" retry
// (`AnexosSection.onReextrairDocumento` → `useDocumentoMutations().reextrair`)
// for a genuinely stuck read.
const EXTRACAO_POLL_MAX_MS = 30_000;

function extracaoEmAndamento(status: string | null): boolean {
  // Deliberately NOT `status == null` — `null` is the PERMANENT, terminal
  // value for a type `identidade_extracao_service.deve_extrair` never reads
  // (a `contrato`, a `foto_imovel`; see `Documento.extracao_status`'s own
  // docstring). Polling on `null` would poll forever for a card whose only
  // attachments are that kind.
  return status === "pendente" || status === "processando";
}

/**
 * The dependent-surface invalidation set a `clientes` field write needs —
 * shared by `useExtracaoPollingInvalidation` below (a SERVER write it only
 * learns about by polling) AND `useNegociacaoMutation` (`useNegociacao.ts`,
 * a CLIENT write whose own `onSuccess` only `setQueryData`s its own key,
 * per that file's docblock — "Salvar" moves `imovel_codigo`/valor fields
 * "Qualificação para contrato"/geração-readiness surfaces also read).
 * Exported so neither caller hand-rolls its own subset and drifts from the
 * other.
 */
export function invalidateExtracaoDependentes(
  qc: ReturnType<typeof useQueryClient>,
  clienteId: string,
): Promise<unknown> {
  return Promise.all([
    qc.invalidateQueries({ queryKey: DOC_CHECKLIST_KEY(clienteId) }),
    qc.invalidateQueries({ queryKey: QUALIFICACAO_ROOT_KEY }),
    qc.invalidateQueries({ queryKey: CARD_KEY(clienteId) }),
    qc.invalidateQueries({ queryKey: COMPRADORES_KEY(clienteId) }),
    qc.invalidateQueries({ queryKey: COMPRADORES_KEY(clienteId, "vendedor") }),
    // Broad prefix, same pattern `useDadosPessoaisMutation` /
    // `useDecidirConflitoMutation` already use for this exact class of
    // problem — covers `useNegociacao`'s `["sw","clientes",id,"negociacao"]`
    // key (not exported for direct reuse here) and the clientes list.
    qc.invalidateQueries({ queryKey: ["sw", "clientes"] }),
  ]);
}

/**
 * Mount once per person's documentos panel (the titular's Geral tab, and
 * each party's `PessoaDocumentosPanel`) alongside `useDocumentos(clienteId)`
 * — same query key, so this shares that hook's cache/fetch rather than
 * doubling the request. While any of that person's documents reads
 * `extracao_status` "pendente"/"processando" it refetches on an interval;
 * the FIRST refetch that flips one from pending to terminal invalidates
 * every surface a `clientes` field the extraction can write lands on:
 * this person's checklist ("Dados obrigatórios"), the whole qualificação
 * family (every party's, not just this one — `QUALIFICACAO_ROOT_KEY` is a
 * shared root), this person's card badges, the compradores/vendedores
 * lists (a linked cônjuge can gain a name), and — via the same broad
 * `["sw","clientes"]` prefix `useDadosPessoaisMutation` already uses for
 * this exact reason — the negociação snapshot and the clientes list.
 * Returns nothing: callers that already hold `useDocumentos`'s own result
 * keep using that for render data; this hook is mounted purely for the
 * polling + invalidation side effect.
 */
export function useExtracaoPollingInvalidation(clienteId: string | null): void {
  const qc = useQueryClient();
  const prevStatusRef = useRef<Map<string, string | null>>(new Map());
  const pollStartedAtRef = useRef<number | null>(null);

  const query = useQuery({
    queryKey: DOCUMENTOS_KEY(clienteId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<Documento>>(
        `${clienteBase(clienteId as string)}/documentos`,
      );
      return res?.items ?? [];
    },
    enabled: !!clienteId,
    refetchInterval: (q) => {
      const docs = (q.state.data as Documento[] | undefined) ?? [];
      if (!docs.some((d) => extracaoEmAndamento(d.extracao_status))) {
        pollStartedAtRef.current = null;
        return false;
      }
      pollStartedAtRef.current ??= Date.now();
      if (Date.now() - pollStartedAtRef.current > EXTRACAO_POLL_MAX_MS) return false;
      return EXTRACAO_POLL_INTERVAL_MS;
    },
  });

  useEffect(() => {
    if (!clienteId || !query.data) return;
    const prev = prevStatusRef.current;
    const proximo = new Map(query.data.map((d) => [d.id, d.extracao_status] as const));
    const transicionou = query.data.some((d) => {
      const antes = prev.get(d.id);
      // `undefined` = this document's first appearance in the map (either the
      // panel just mounted, or it was just uploaded) — never itself a
      // transition; only a PREVIOUSLY-seen pending status turning terminal
      // counts.
      return antes !== undefined && extracaoEmAndamento(antes) && !extracaoEmAndamento(d.extracao_status);
    });
    prevStatusRef.current = proximo;
    if (transicionou) {
      void invalidateExtracaoDependentes(qc, clienteId);
    }
  }, [clienteId, query.data, qc]);
}

export function useDocumentoChecklistMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, concluido }: { key: string; concluido: boolean | null }) =>
      api.patch<DocumentoChecklistItem>(
        `${clienteBase(clienteId)}/documento-checklist/${encodeURIComponent(key)}`,
        { concluido },
      ),
    onMutate: async ({ key, concluido }) => {
      await qc.cancelQueries({ queryKey: DOC_CHECKLIST_KEY(clienteId) });
      const previous = qc.getQueryData<DocumentoChecklist>(DOC_CHECKLIST_KEY(clienteId));
      if (previous) {
        // Clearing the override optimistically shows `derivado` — the value
        // the server is about to fall back to — rather than blanking the row.
        const items = previous.items.map((i) =>
          i.key === key
            ? {
                ...i,
                concluido: concluido === null ? i.derivado : concluido,
                origem: concluido === null ? ("derivado" as const) : ("manual" as const),
              }
            : i,
        );
        qc.setQueryData<DocumentoChecklist>(DOC_CHECKLIST_KEY(clienteId), {
          ...previous,
          items,
          concluidos: items.filter((i) => i.concluido).length,
        });
      }
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(DOC_CHECKLIST_KEY(clienteId), ctx.previous);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: DOC_CHECKLIST_KEY(clienteId) });
    },
  });
}


// ─── Qualificação civil completude (migration 110) ────────────────────────

/**
 * One party's contract-readiness (`documento_checklist_service.
 * completude_contratual`) — a stricter, SEPARATE question from
 * `useDocumentoChecklist`'s "has something plausible been collected".
 *
 * Keyed by `clienteId`, never by a parte id: this is a fact about the
 * PERSON, so the titular's own card and every comprador/vendedor panel read
 * it off the same route by handing it their own `cliente_id`.
 */
export function useQualificacaoCompletude(clienteId: string | null) {
  return useQuery({
    queryKey: QUALIFICACAO_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<QualificacaoCompletude>(
        `${clienteBase(clienteId as string)}/qualificacao-completude`,
      ),
    enabled: !!clienteId,
  });
}

// ─── Compradores / partes do atendimento (migration 073) ──────────────────

/**
 * The other people party to this card's atendimento.
 *
 * Returns an empty list rather than erroring when the person has no single
 * open atendimento — the Geral tab hides the section entirely in that case,
 * and an error state for "nothing to show" would be noise on every card that
 * has one buyer, which is most of them.
 */
export function useCompradores(
  clienteId: string | null,
  lado: LadoParte = "comprador",
) {
  return useQuery({
    queryKey: COMPRADORES_KEY(clienteId ?? "__none__", lado),
    queryFn: () =>
      api.get<CompradoresResponse>(
        `${clienteBase(clienteId as string)}/compradores?lado=${lado}`,
      ),
    enabled: !!clienteId,
  });
}

/**
 * Add or detach a party.
 *
 * NOT optimistic, unlike the checklist tick. Adding a comprador CREATES a
 * person record (or links an existing one) and the server assigns their id —
 * there is no correct row to render before it answers, and inventing one would
 * mean the Documentos tab briefly renders a checklist for a `cliente_id` that
 * does not exist yet, whose own queries would 404.
 *
 * Invalidates the party list AND the card summary: the Geral tab's Compradores
 * section appears the moment the first one is added, so the card's own shape
 * changed. Migration 110 — ALSO every party's qualificação-completude: adding
 * or removing a party changes who is ON the deal, and `atualizarPapel` can set
 * `papel: "conjuge"` (writing `conjuge_cliente_id` on TWO people, neither of
 * which is necessarily this card's own titular) — over-invalidating the whole
 * `qualificacao` root is cheap next to rendering a stale "cônjuge pendente".
 */
export function useCompradorMutations(clienteId: string) {
  const qc = useQueryClient();
  // Invalidates BOTH sides, not just the one written. `remover` is not told
  // which side the party was on, and a person moved between sides would
  // otherwise linger in the stale list — cheap to over-invalidate, expensive
  // to render a vendedor under Compradores.
  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({
        queryKey: [...FAMILY_KEY(clienteId), "compradores"],
      }),
      qc.invalidateQueries({ queryKey: CARD_KEY(clienteId) }),
      qc.invalidateQueries({ queryKey: QUALIFICACAO_ROOT_KEY }),
    ]);

  const adicionar = useMutation({
    mutationFn: (body: {
      nome?: string;
      celular?: string;
      cliente_id?: string;
      papel?: string;
      observacao?: string;
      atendimento_id?: string;
      lado?: LadoParte;
    }) => api.post<Comprador>(`${clienteBase(clienteId)}/compradores`, body),
    onSuccess: invalidate,
  });

  const remover = useMutation({
    mutationFn: (parteId: string) =>
      api.delete(
        `${clienteBase(clienteId)}/compradores/${encodeURIComponent(parteId)}`,
      ),
    onSuccess: invalidate,
  });

  /**
   * Correct what a party IS to their side.
   *
   * 🔴 `lado` is deliberately absent from the body — the server reads it off
   * the stored row, because `lado` decides which vocabulary validates `papel`
   * and a client able to name it could call a vendedor a `fiador`.
   *
   * Shares `invalidate` with the other two, which re-reads BOTH sides. That is
   * over-invalidation on purpose here as well: setting `conjuge` can also
   * write `clientes.conjuge_cliente_id` on two people, so the card summary is
   * no longer only about this list.
   */
  const atualizarPapel = useMutation({
    mutationFn: ({ parteId, papel }: { parteId: string; papel: string }) =>
      api.patch<Comprador>(
        `${clienteBase(clienteId)}/compradores/${encodeURIComponent(parteId)}`,
        { papel },
      ),
    onSuccess: invalidate,
  });

  return { adicionar, remover, atualizarPapel };
}


/**
 * Save the typed identity fields — the ones the checklist derives its ticks
 * from.
 *
 * Hits the ordinary `PATCH /api/clientes/{id}`; there is deliberately no
 * "checklist write" endpoint, because a tick is derived and the way to satisfy
 * an item IS to supply the data.
 *
 * 🔴 SCOPED invalidation, not the whole card-hub family.
 *
 * Used to be `invalidateQueries({ queryKey: FAMILY_KEY(clienteId) })` — every
 * query this cliente has, including compradores, roteiros, agendamentos,
 * documentos and membros, none of which a name/email/profissão edit can
 * possibly change. That is exactly the mechanism a screen recording caught:
 * clearing one field flipped `isFetching` on `documento-checklist` (which
 * DOES derive from these fields — see `DocumentoChecklistSection`'s
 * docblock) at the same time as everything else, and the section's
 * early-return-on-loading shape turned that into all 8 rows vanishing.
 *
 * Narrowed to exactly what this write can change:
 *   - `documento-checklist` — the ticks and `valores` derive from these exact
 *     columns (the whole reason this mutation exists per the docblock above).
 *   - `card` — its `badges.checklist_concluidos`/`checklist_total` move with
 *     the same ticks, and `cliente.nome` in the header can change too.
 *   - `timeline` — a satisfied item is a `checklist`-kind entry, the same
 *     activity a checklist tick produces (mirrors the seed checklist
 *     mutations' invalidation, applied here because satisfying an item via data IS a checklist
 *     edit, just routed through the clientes API).
 *   - `["sw", "clientes"]` — a SEPARATE root (the clientes list/board), kept
 *     as-is: that surface shows `nome`/`email` outside this card entirely.
 *   - the `qualificacao` root (migration 110) — `estado_civil`, `regime_bens`,
 *     `cpf`, `rg`, `rg_orgao_expedidor`, `nacionalidade` and every endereço
 *     column this form writes are exactly what `completude_contratual` reads;
 *     the ROOT, not `QUALIFICACAO_KEY(clienteId)` alone, because this same
 *     mutation is instantiated per PARTY (`PessoaDocumentosPanel`), and a
 *     married party's PATCH can also change what a LINKED cônjuge's own
 *     completude reports (the pair fact `completude_contratual` composes).
 *
 * Not optimistic: this writes to a person's record, and a checklist item
 * flipping green before the server agreed is the one moment a rejected save
 * looks like a successful one.
 */
/**
 * The PATCH response `clientes_service.update_cliente` (owner directive,
 * 2026-09-19) always returns: the updated cliente row PLUS
 * `pendente_confirmacao` — item_keys THIS save deferred to admin
 * confirmation (empty when nothing was). `DadosPessoaisForm`'s
 * `pendenteConfirmacao` prop reads off `mutation.data?.pendente_confirmacao`.
 */
export type DadosPessoaisSaveResult = DadosPessoais & {
  pendente_confirmacao?: string[];
};

export function useDadosPessoaisMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    // Typed as the form's own shape: these are the exact columns
    // `clientes_router.ClientePatchBody` accepts. The type alone does NOT
    // keep a stray key out — a wider object (the full `clientes` row) is
    // assignable to it — so the body is narrowed at runtime too; see
    // `apenasDadosPessoais`.
    mutationFn: (body: DadosPessoais) =>
      api.patch<DadosPessoaisSaveResult>(
        `${clienteBase(clienteId)}`,
        apenasDadosPessoais(body),
      ),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: DOC_CHECKLIST_KEY(clienteId) }),
        qc.invalidateQueries({ queryKey: CARD_KEY(clienteId) }),
        qc.invalidateQueries({ queryKey: [...FAMILY_KEY(clienteId), "timeline"] }),
        qc.invalidateQueries({ queryKey: ["sw", "clientes"] }),
        qc.invalidateQueries({ queryKey: QUALIFICACAO_ROOT_KEY }),
        // The DURABLE pending-state read (owner directive, 2026-09-19) —
        // a save that just opened (or found) a pending conflict must show
        // up on the very next read, not only in THIS mutation's own
        // transient `data.pendente_confirmacao`.
        qc.invalidateQueries({ queryKey: CONFLITOS_KEY(clienteId) }),
      ]),
  });
}

// ─── Admin-adjudicated field conflicts (migration 138 + its reverse
//     direction, owner directive 2026-09-19) ───────────────────────────
//
// `identidade_extracao_service.CampoExtraido`/`clientes_service
// .update_cliente`'s `_CAMPOS_COM_ORIGEM` on the backend — this is the
// read/decide surface for the SAME `cliente_campo_conflitos` rows,
// whichever direction opened them (an extraction disagreeing with a
// human value, OR a human editing a document-sourced value without being
// an admin).

export interface ConflitoCampo {
  id: string;
  cliente_id: string;
  campo: string;
  valor_anterior: string | null;
  origem_anterior: string | null;
  valor_proposto: string;
  origem_proposto: string;
  confianca_proposta: string | null;
  status: "pendente" | "aceito" | "rejeitado";
  created_at: string;
}

/**
 * `clienteId` omitted: every pending conflict in the org — the admin
 * queue (`Settings.tsx`'s "Pendências de dados" tab). `clienteId` set:
 * just this person's — the DURABLE source `DadosPessoaisForm`'s
 * `pendenteConfirmacao` prop reads (survives a reload, unlike the last
 * mutation's own transient response).
 *
 * `enabled` defaults to `true` — a per-cliente caller whose id is not
 * READY YET (the card isn't open, `shouldFetch` is false) MUST pass
 * `enabled: false` explicitly, or an `undefined` `clienteId` reads as
 * "org-wide" and fires the wrong query.
 */
export function useConflitosPendentes(
  clienteId?: string,
  { enabled = true }: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: CONFLITOS_KEY(clienteId),
    queryFn: () => {
      const qs = clienteId
        ? `?${new URLSearchParams({ cliente_id: clienteId }).toString()}`
        : "";
      return api.get<ConflitoCampo[]>(`/api/clientes/conflitos${qs}`);
    },
    enabled,
  });
}

/** Owner/admin only on the server (`decidir_conflito_route`) — this
 *  mutation itself is unguarded; a non-admin's attempt simply 403s and
 *  surfaces through `onError`, same as any other write this file has. */
export function useDecidirConflitoMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ conflitoId, aceitar }: { conflitoId: string; aceitar: boolean }) =>
      api.put<ConflitoCampo>(`/api/clientes/conflitos/${conflitoId}/decidir`, {
        aceitar,
      }),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: CONFLITOS_ROOT_KEY });
      // Accepting writes the field for real — the same surfaces a normal
      // `DadosPessoaisForm` save touches.
      void qc.invalidateQueries({ queryKey: DOC_CHECKLIST_KEY(result.cliente_id) });
      void qc.invalidateQueries({ queryKey: CARD_KEY(result.cliente_id) });
      void qc.invalidateQueries({ queryKey: ["sw", "clientes"] });
      void qc.invalidateQueries({ queryKey: QUALIFICACAO_ROOT_KEY });
    },
  });
}
