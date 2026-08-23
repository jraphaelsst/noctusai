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
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";

import { apiUrl } from "@/lib/apiBase";
import type {
  Agendamento,
  AgendamentoCreateBody,
  AgendamentoPatchBody,
  Acesso,
  Checklist,
  ChecklistOrigem,
  Documento,
  DocumentoUrlResponse,
  ItemsEnvelope,
  CardDatas,
  CardResumo,
  Membro,
  Nota,
  NotaTipo,
  Tag,
  TimelineEntry,
  TimelineKind,
  TimelinePage,
  TipoDocumento,
  DocumentoChecklist,
  DocumentoChecklistItem,
} from "@/types/cardHub";

// ─── Query keys ─────────────────────────────────────────────────────────────

const ROOT_KEY = ["sw", "cardHub"] as const;
const FAMILY_KEY = (clienteId: string) => [...ROOT_KEY, clienteId] as const;
const CARD_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "card"] as const;
const TIMELINE_KEY = (clienteId: string, kinds?: TimelineKind[]) =>
  [...FAMILY_KEY(clienteId), "timeline", kinds ?? "all"] as const;
const MEMBROS_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "membros"] as const;
const CHECKLISTS_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "checklists"] as const;
const DOC_CHECKLIST_KEY = (clienteId: string) =>
  [...FAMILY_KEY(clienteId), "documento-checklist"] as const;
const AGENDAMENTOS_KEY = (clienteId: string) =>
  [...FAMILY_KEY(clienteId), "agendamentos"] as const;
const DOCUMENTOS_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "documentos"] as const;
const ACESSOS_KEY = (clienteId: string, documentoId: string) =>
  [...FAMILY_KEY(clienteId), "documentos", documentoId, "acessos"] as const;
const TAGS_KEY = [...ROOT_KEY, "tags"] as const;
const TIPOS_DOC_KEY = [...ROOT_KEY, "tiposDocumento"] as const;

function invalidateCliente(qc: QueryClient, clienteId: string) {
  return qc.invalidateQueries({ queryKey: FAMILY_KEY(clienteId) });
}

function invalidateEverything(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: ROOT_KEY });
}

/**
 * The checklist family ONLY — plus the two things a checklist edit genuinely
 * changes elsewhere: the card's badges (item counts) and the timeline (the
 * activity entry the edit produces).
 *
 * `invalidateCliente` refetches the WHOLE family, so ticking one checkbox also
 * re-fetched documentos and membros, neither of which a checklist edit can
 * affect. Combined with the section skeletons that used to key off
 * `isFetching`, that is what made the card feel like it reloaded on every move.
 */
function invalidateChecklistFamily(qc: QueryClient, clienteId: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: CHECKLISTS_KEY(clienteId) }),
    qc.invalidateQueries({ queryKey: CARD_KEY(clienteId) }),
    qc.invalidateQueries({ queryKey: [...FAMILY_KEY(clienteId), "timeline"] }),
  ]);
}

const clienteBase = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;

// ─── Card summary (the badge row source — §3 "Card summary") ──────────────

export function useCardResumo(clienteId: string | null) {
  return useQuery({
    queryKey: CARD_KEY(clienteId ?? "__none__"),
    queryFn: () => api.get<CardResumo>(`${clienteBase(clienteId as string)}/card`),
    enabled: !!clienteId,
  });
}

// ─── Timeline (D9 — one thread, cursor-paginated) ──────────────────────────

export function useTimeline(clienteId: string | null, kinds?: TimelineKind[]) {
  return useInfiniteQuery({
    queryKey: TIMELINE_KEY(clienteId ?? "__none__", kinds),
    queryFn: async ({ pageParam }: { pageParam: string | null }) => {
      const params = new URLSearchParams({ limit: "50" });
      if (pageParam) params.set("cursor", pageParam);
      if (kinds?.length) params.set("kinds", kinds.join(","));
      const res = await api.get<TimelinePage>(
        `${clienteBase(clienteId as string)}/timeline?${params.toString()}`,
      );
      return res ?? { items: [], total: 0, next_cursor: null };
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: !!clienteId,
  });
}

/** Flattens the infinite-query pages into one newest-first array. */
export function flattenTimeline(pages: TimelinePage[] | undefined): TimelineEntry[] {
  if (!pages) return [];
  return pages.flatMap((p) => p.items);
}

// ─── Notas ───────────────────────────────────────────────────────────────

export function useNotaMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => invalidateCliente(qc, clienteId);

  // `tipo` mirrors `card_hub/schemas.py::NotaCreateBody` — defaults to
  // "comentario" (the composer's case); the description editor passes
  // `tipo: "descricao"` explicitly. The backend enforces at most one
  // non-deleted "descricao" per cliente and returns a typed 409
  // (`ConflictError`) on a second — callers MUST surface `err.message`
  // rather than let a rejected create read as a network failure.
  const create = useMutation({
    mutationFn: ({ corpo, tipo = "comentario" }: { corpo: string; tipo?: NotaTipo }) =>
      api.post<Nota>(`${clienteBase(clienteId)}/notas`, { corpo, tipo }),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ notaId, corpo }: { notaId: string; corpo: string }) =>
      api.patch<Nota>(`${clienteBase(clienteId)}/notas/${encodeURIComponent(notaId)}`, { corpo }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (notaId: string) =>
      api.delete(`${clienteBase(clienteId)}/notas/${encodeURIComponent(notaId)}`),
    onSuccess: invalidate,
  });

  return { create, update, remove };
}

// ─── Tags (D6 — one system) ─────────────────────────────────────────────────

export function useTags() {
  return useQuery({
    queryKey: TAGS_KEY,
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<Tag>>("/api/clientes/tags");
      return res?.items ?? [];
    },
  });
}

export function useTagCatalogMutations() {
  const qc = useQueryClient();
  // Renaming/recolouring/deleting a tag can change what any open card shows
  // (its `tags` are a materialised snapshot at fetch time) — invalidate the
  // whole cardHub root, not just the catalogue, rather than tracking which
  // clientes reference this tag.
  const invalidate = () => invalidateEverything(qc);

  const create = useMutation({
    mutationFn: (body: { nome: string; cor: string }) =>
      api.post<Tag>("/api/clientes/tags", body),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ tagId, body }: { tagId: string; body: { nome?: string; cor?: string } }) =>
      api.patch<Tag>(`/api/clientes/tags/${encodeURIComponent(tagId)}`, body),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (tagId: string) => api.delete(`/api/clientes/tags/${encodeURIComponent(tagId)}`),
    onSuccess: invalidate,
  });

  return { create, update, remove };
}

/**
 * PUT the full tag set for one cliente (Etiquetas chip toggle) — optimistic:
 * the checkbox flips instantly in `EtiquetasPopover`, and a failure rolls
 * `CardResumo.tags` back to the pre-toggle snapshot rather than leaving a
 * lying checked box the server never accepted.
 */
export function useSetClienteTagsMutation(clienteId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (tagIds: string[]) =>
      api.put<ItemsEnvelope<Tag>>(`${clienteBase(clienteId)}/tags`, { tag_ids: tagIds }),
    onMutate: async (tagIds: string[]) => {
      await qc.cancelQueries({ queryKey: CARD_KEY(clienteId) });
      const previous = qc.getQueryData<CardResumo>(CARD_KEY(clienteId));
      if (previous) {
        const allTags = qc.getQueryData<Tag[]>(TAGS_KEY) ?? previous.tags;
        const optimisticTags = allTags.filter((t) => tagIds.includes(t.id));
        qc.setQueryData<CardResumo>(CARD_KEY(clienteId), {
          ...previous,
          tags: optimisticTags,
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        qc.setQueryData(CARD_KEY(clienteId), context.previous);
      }
    },
    onSettled: () => invalidateCliente(qc, clienteId),
  });
}

// ─── Membros (D10 — points at lead_corretores) ─────────────────────────────

export function useCardMembros(clienteId: string | null) {
  return useQuery({
    queryKey: MEMBROS_KEY(clienteId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<Membro>>(`${clienteBase(clienteId as string)}/membros`);
      return res?.items ?? [];
    },
    enabled: !!clienteId,
  });
}

export function useSetCardMembrosMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leadCorretorIds: string[]) =>
      api.put<ItemsEnvelope<Membro>>(`${clienteBase(clienteId)}/membros`, {
        lead_corretor_ids: leadCorretorIds,
      }),
    onSuccess: () => invalidateCliente(qc, clienteId),
  });
}

// ─── Datas + lembretes (screenshot 06) ─────────────────────────────────────

export function useChecklists(clienteId: string | null) {
  return useQuery({
    queryKey: CHECKLISTS_KEY(clienteId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<Checklist>>(`${clienteBase(clienteId as string)}/checklists`);
      return res?.items ?? [];
    },
    enabled: !!clienteId,
  });
}

export function useChecklistMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => invalidateChecklistFamily(qc, clienteId);
  const base = clienteBase(clienteId);

  const createChecklist = useMutation({
    mutationFn: (titulo: string) => api.post<Checklist>(`${base}/checklists`, { titulo }),
    onSuccess: invalidate,
  });

  const renameChecklist = useMutation({
    mutationFn: ({ checklistId, titulo }: { checklistId: string; titulo: string }) =>
      api.patch<Checklist>(`${base}/checklists/${encodeURIComponent(checklistId)}`, { titulo }),
    onSuccess: invalidate,
  });

  const removeChecklist = useMutation({
    mutationFn: (checklistId: string) =>
      api.delete(`${base}/checklists/${encodeURIComponent(checklistId)}`),
    onSuccess: invalidate,
  });

  /**
   * Optimistic, for the same reason `toggleItem` is: typing an item and waiting
   * for a round-trip before it appears reads as a stutter. The temporary id is
   * namespaced so a render between mutate and settle cannot collide with a real
   * one, and the whole list rolls back on failure.
   */
  const addItem = useMutation({
    mutationFn: ({ checklistId, texto }: { checklistId: string; texto: string }) =>
      api.post(`${base}/checklists/${encodeURIComponent(checklistId)}/itens`, { texto }),
    onMutate: async ({ checklistId, texto }) => {
      await qc.cancelQueries({ queryKey: CHECKLISTS_KEY(clienteId) });
      const previous = qc.getQueryData<Checklist[]>(CHECKLISTS_KEY(clienteId));
      if (previous) {
        qc.setQueryData<Checklist[]>(
          CHECKLISTS_KEY(clienteId),
          previous.map((c) =>
            c.id === checklistId
              ? {
                  ...c,
                  itens: [
                    ...c.itens,
                    {
                      id: `optimistic:${checklistId}:${c.itens.length}`,
                      texto,
                      concluido: false,
                      concluido_em: null,
                      concluido_por: null,
                      posicao: c.itens.length,
                    },
                  ],
                }
              : c,
          ),
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(CHECKLISTS_KEY(clienteId), context.previous);
    },
    onSettled: invalidate,
  });

  /**
   * Optimistic — the checkbox flips the instant a broker clicks it
   * (mandatory rule: "Optimistic updates for checkbox ticks"). Rolls the
   * whole checklist list back to its pre-toggle snapshot on failure.
   */
  const toggleItem = useMutation({
    mutationFn: ({
      checklistId,
      itemId,
      concluido,
    }: {
      checklistId: string;
      itemId: string;
      concluido: boolean;
    }) =>
      api.patch(
        `${base}/checklists/${encodeURIComponent(checklistId)}/itens/${encodeURIComponent(itemId)}`,
        { concluido },
      ),
    onMutate: async ({ checklistId, itemId, concluido }) => {
      await qc.cancelQueries({ queryKey: CHECKLISTS_KEY(clienteId) });
      const previous = qc.getQueryData<Checklist[]>(CHECKLISTS_KEY(clienteId));
      if (previous) {
        qc.setQueryData<Checklist[]>(
          CHECKLISTS_KEY(clienteId),
          previous.map((cl) =>
            cl.id !== checklistId
              ? cl
              : {
                  ...cl,
                  itens: cl.itens.map((it) => (it.id === itemId ? { ...it, concluido } : it)),
                  concluidos: cl.itens.filter((it) =>
                    it.id === itemId ? concluido : it.concluido,
                  ).length,
                },
          ),
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        qc.setQueryData(CHECKLISTS_KEY(clienteId), context.previous);
      }
    },
    onSettled: invalidate,
  });

  const updateItemText = useMutation({
    mutationFn: ({
      checklistId,
      itemId,
      texto,
    }: {
      checklistId: string;
      itemId: string;
      texto: string;
    }) =>
      api.patch(
        `${base}/checklists/${encodeURIComponent(checklistId)}/itens/${encodeURIComponent(itemId)}`,
        { texto },
      ),
    onSuccess: invalidate,
  });

  const removeItem = useMutation({
    mutationFn: ({ checklistId, itemId }: { checklistId: string; itemId: string }) =>
      api.delete(
        `${base}/checklists/${encodeURIComponent(checklistId)}/itens/${encodeURIComponent(itemId)}`,
      ),
    onMutate: async ({ checklistId, itemId }) => {
      await qc.cancelQueries({ queryKey: CHECKLISTS_KEY(clienteId) });
      const previous = qc.getQueryData<Checklist[]>(CHECKLISTS_KEY(clienteId));
      if (previous) {
        qc.setQueryData<Checklist[]>(
          CHECKLISTS_KEY(clienteId),
          previous.map((c) =>
            c.id === checklistId ? { ...c, itens: c.itens.filter((i) => i.id !== itemId) } : c,
          ),
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(CHECKLISTS_KEY(clienteId), context.previous);
    },
    onSettled: invalidate,
  });

  return {
    createChecklist,
    renameChecklist,
    removeChecklist,
    addItem,
    toggleItem,
    updateItemText,
    removeItem,
  };
}

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

// ─── Documentos (LGPD, D5) ──────────────────────────────────────────────────

export function useDocumentos(clienteId: string | null) {
  return useQuery({
    queryKey: DOCUMENTOS_KEY(clienteId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<Documento>>(`${clienteBase(clienteId as string)}/documentos`);
      return res?.items ?? [];
    },
    enabled: !!clienteId,
  });
}

export function useTiposDocumento() {
  return useQuery({
    queryKey: TIPOS_DOC_KEY,
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<TipoDocumento>>("/api/clientes/documentos/tipos");
      return res?.items ?? [];
    },
  });
}

export function useDocumentoAcessos(clienteId: string | null, documentoId: string | null) {
  return useQuery({
    queryKey: ACESSOS_KEY(clienteId ?? "__none__", documentoId ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<ItemsEnvelope<Acesso>>(
        `${clienteBase(clienteId as string)}/documentos/${encodeURIComponent(documentoId as string)}/acessos`,
      );
      return res?.items ?? [];
    },
    enabled: !!clienteId && !!documentoId,
  });
}

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function useDocumentoMutations(clienteId: string) {
  const qc = useQueryClient();
  const invalidate = () => invalidateCliente(qc, clienteId);
  const base = clienteBase(clienteId);

  // Multipart bypasses the JSON-only seed `api` client, same pattern as
  // `useUpload.ts` — raw fetch with the auth header pulled from supabase.
  const upload = useMutation({
    mutationFn: async ({ file, tipoDocumento }: { file: File; tipoDocumento: string }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("tipo_documento", tipoDocumento);
      const headers = await getAuthHeader();
      const response = await fetch(apiUrl(`${base}/documentos`), {
        method: "POST",
        headers, // no content-type — the browser sets the multipart boundary
        body: formData,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        const message = detail?.error?.message ?? `Erro HTTP ${response.status}`;
        throw new Error(message);
      }
      return (await response.json()) as Documento;
    },
    onSuccess: invalidate,
  });

  // Backend correction, landed on `origin/dev`
  // (`card_hub/router.py::delete_documento_route`): `motivo` travels as a
  // REQUIRED query param, not a JSON body — the seed `ApiClient.delete()`
  // gap this file originally routed around no longer applies to THIS
  // route (it may still bite elsewhere; the gap itself is real).
  const remove = useMutation({
    mutationFn: ({ documentoId, motivo }: { documentoId: string; motivo: string }) =>
      api.delete(
        `${base}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
      ),
    onSuccess: invalidate,
  });

  const getUrl = useMutation({
    mutationFn: (documentoId: string) =>
      api.get<DocumentoUrlResponse>(`${base}/documentos/${encodeURIComponent(documentoId)}/url`),
  });

  return { upload, remove, getUrl };
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
 * documents list (the discard flag lives on a document row).
 */
export function useExtracaoSugestaoMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentoId,
      acao,
    }: {
      documentoId: string;
      acao: "confirmar" | "descartar";
    }) =>
      api.post<{ documento_id: string }>(
        `${clienteBase(clienteId)}/documentos/${documentoId}/extracao/${acao}`,
        {},
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: DOC_CHECKLIST_KEY(clienteId) });
      void qc.invalidateQueries({ queryKey: DOCUMENTOS_KEY(clienteId) });
    },
  });
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
