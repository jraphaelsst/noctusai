/**
 * `createCardHubHooks(descriptor, api)` — the data layer for one card hub.
 *
 * MOVED from the generic slice of
 * `products/social-wiring/frontend/src/hooks/useCardHub.ts` (resumo, timeline,
 * notas, tags, membros, checklists, documentos, checklist-extras) per
 * `project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` §2,
 * Slice C. Mirrors `components/pipeline/createPipelineHooks.ts`: a descriptor
 * literal in, a bag of hooks out — two card hubs differ by the descriptor and
 * nothing else.
 *
 * 🔴 QUERY KEYS DERIVE FROM `rootKey`, BYTE-FOR-BYTE SW's SHAPE
 * -------------------------------------------------------------
 * `rootKey: ["sw", "cardHub"]` reproduces SW's keys exactly
 * (`[...root, id, "card"]`, `[...root, id, "timeline", kinds ?? "all"]`,
 * `[...root, "tags"]`, …), so SW's product-only hooks that stay behind
 * (roteiros, agendamentos, compradores, documento-checklist) keep sharing ONE
 * cache family with these and every existing invalidation still lands. The
 * key builders are returned as `keys` for exactly that reuse.
 *
 * 🔴 NARROW INVALIDATION, NOT THE WHOLE FAMILY
 * --------------------------------------------
 * Each mutation invalidates only what that write can change (a checklist tick
 * never refetches documentos). Wholesale family invalidation is what made the
 * SW card flash on every edit. A product that has EXTRA derived views an
 * attachment write moves (SW: its documento-checklist) names their family
 * sub-keys in `documentoInvalidates` — the seed does not guess them.
 *
 * 🔴 NO `placeholderData` ON THE PER-CARD READS — deliberately. Every read here
 * is keyed by the card id; carrying the PREVIOUS card's data over while the
 * next one loads would render one person's tags, notes and documents under
 * another person's name (authorisation-scoped personal data — the documented
 * exception in `KB § PATTERNS/frontend/lying-loading-state.md`). Consumers
 * derive `showSkeleton = isPending && !data` via `cardHubLoadingState`.
 *
 * Optimistic updates (checklist add/toggle/remove, the tag full-set PUT) roll
 * back to the pre-mutation snapshot on failure — never a silently swallowed
 * mutation.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";

import type { ApiClient } from "../../api";
import type {
  Acesso,
  CardResumoBase,
  Checklist,
  ChecklistExtra,
  ChecklistExtraTipo,
  ChecklistExtrasResponse,
  Documento,
  DocumentoUrlResponse,
  ItemsEnvelope,
  Membro,
  Nota,
  NotaTipo,
  Tag,
  TimelineEntry,
  TimelineKind,
  TimelinePage,
  TipoDocumento,
} from "./types";

/** The slice of the seed `ApiClient` the card hub needs (bare-payload JSON
 *  methods + multipart `upload`). A product passes its seed `api`. */
export type CardHubApi = Pick<ApiClient, "get" | "post" | "patch" | "put" | "delete" | "upload">;

export interface CardHubDescriptor {
  /** Query-key root. SW: `["sw", "cardHub"]`. */
  rootKey: readonly unknown[];
  /** The entity collection path — `${basePath}/{id}/card` etc. SW: `/api/clientes`. */
  basePath: string;
  /** Human noun for the entity ("cliente", "lead") — for consumer copy. */
  entityLabel: string;
  /** Extra family sub-keys an attachment write invalidates (SW:
   *  `["documento-checklist"]`). */
  documentoInvalidates?: readonly string[];
  /** Page size for the timeline's cursor pagination (1–200 server-side). */
  timelinePageSize?: number;
}

/** The two loading signals (`KB § PATTERNS/frontend/lying-loading-state.md`):
 *  a skeleton only while there is nothing yet, a refresh indicator only over
 *  data that exists. Never `isLoading`, never a bare `isFetching`. */
export function cardHubLoadingState(query: {
  isPending: boolean;
  isFetching: boolean;
  data: unknown;
}): { showSkeleton: boolean; isRefreshing: boolean } {
  const hasData = query.data !== undefined && query.data !== null;
  return {
    showSkeleton: query.isPending && !hasData,
    isRefreshing: query.isFetching && hasData,
  };
}

/** Flattens the timeline's infinite-query pages into one newest-first array. */
export function flattenTimeline(pages: TimelinePage[] | undefined): TimelineEntry[] {
  if (!pages) return [];
  return pages.flatMap((p) => p.items);
}

export function createCardHubHooks<TResumo extends CardResumoBase = CardResumoBase>(
  descriptor: CardHubDescriptor,
  api: CardHubApi,
) {
  const { rootKey, basePath, documentoInvalidates = [], timelinePageSize = 50 } = descriptor;

  // ─── Query keys ──────────────────────────────────────────────────────────
  const ROOT_KEY = [...rootKey] as const;
  const keys = {
    root: ROOT_KEY,
    family: (id: string) => [...ROOT_KEY, id] as const,
    card: (id: string) => [...ROOT_KEY, id, "card"] as const,
    timeline: (id: string, kinds?: TimelineKind[]) =>
      [...ROOT_KEY, id, "timeline", kinds ?? "all"] as const,
    /** Prefix of every timeline query of one card (all `kinds` filters). */
    timelineAll: (id: string) => [...ROOT_KEY, id, "timeline"] as const,
    membros: (id: string) => [...ROOT_KEY, id, "membros"] as const,
    checklists: (id: string) => [...ROOT_KEY, id, "checklists"] as const,
    checklistExtras: (id: string) => [...ROOT_KEY, id, "checklist-extras"] as const,
    documentos: (id: string) => [...ROOT_KEY, id, "documentos"] as const,
    acessos: (id: string, documentoId: string) =>
      [...ROOT_KEY, id, "documentos", documentoId, "acessos"] as const,
    tags: [...ROOT_KEY, "tags"] as const,
    tiposDocumento: [...ROOT_KEY, "tiposDocumento"] as const,
  };

  const entityBase = (id: string) => `${basePath}/${encodeURIComponent(id)}`;

  function invalidateEverything(qc: QueryClient) {
    return qc.invalidateQueries({ queryKey: ROOT_KEY });
  }

  /** A checklist edit changes the checklists, the card's badges (item counts)
   *  and the timeline (the activity entry) — nothing else. */
  function invalidateChecklistFamily(qc: QueryClient, id: string) {
    return Promise.all([
      qc.invalidateQueries({ queryKey: keys.checklists(id) }),
      qc.invalidateQueries({ queryKey: keys.card(id) }),
      qc.invalidateQueries({ queryKey: keys.timelineAll(id) }),
    ]);
  }

  // ─── Card summary ────────────────────────────────────────────────────────

  function useCardResumo(id: string | null) {
    return useQuery({
      queryKey: keys.card(id ?? "__none__"),
      queryFn: () => api.get<TResumo>(`${entityBase(id as string)}/card`),
      enabled: !!id,
    });
  }

  // ─── Timeline (one thread, cursor-paginated) ─────────────────────────────

  function useTimeline(id: string | null, kinds?: TimelineKind[]) {
    return useInfiniteQuery({
      queryKey: keys.timeline(id ?? "__none__", kinds),
      queryFn: async ({ pageParam }: { pageParam: string | null }) => {
        const params = new URLSearchParams({ limit: String(timelinePageSize) });
        if (pageParam) params.set("cursor", pageParam);
        if (kinds?.length) params.set("kinds", kinds.join(","));
        const res = await api.get<TimelinePage>(
          `${entityBase(id as string)}/timeline?${params.toString()}`,
        );
        return res ?? { items: [], total: 0, next_cursor: null };
      },
      initialPageParam: null as string | null,
      getNextPageParam: (lastPage) => lastPage.next_cursor,
      enabled: !!id,
    });
  }

  // ─── Notas ───────────────────────────────────────────────────────────────

  /**
   * A nota is a `comentario` (timeline + the `notas` badge) or the card's
   * single `descricao` (card state). Either way only `card` and `timeline`
   * change. The backend refuses a second live `descricao` with a typed 409 —
   * callers MUST surface `err.message`, never read it as a network failure.
   */
  function useNotaMutations(id: string) {
    const qc = useQueryClient();
    const invalidate = () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.card(id) }),
        qc.invalidateQueries({ queryKey: keys.timelineAll(id) }),
      ]);

    const create = useMutation({
      mutationFn: ({ corpo, tipo = "comentario" }: { corpo: string; tipo?: NotaTipo }) =>
        api.post<Nota>(`${entityBase(id)}/notas`, { corpo, tipo }),
      onSuccess: invalidate,
    });

    const update = useMutation({
      mutationFn: ({ notaId, corpo }: { notaId: string; corpo: string }) =>
        api.patch<Nota>(`${entityBase(id)}/notas/${encodeURIComponent(notaId)}`, { corpo }),
      onSuccess: invalidate,
    });

    const remove = useMutation({
      mutationFn: (notaId: string) =>
        api.delete(`${entityBase(id)}/notas/${encodeURIComponent(notaId)}`),
      onSuccess: invalidate,
    });

    return { create, update, remove };
  }

  // ─── Tags (one catalogue per org) ────────────────────────────────────────

  function useTags() {
    return useQuery({
      queryKey: keys.tags,
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<Tag>>(`${basePath}/tags`);
        return res?.items ?? [];
      },
    });
  }

  function useTagCatalogMutations() {
    const qc = useQueryClient();
    // Renaming/recolouring/deleting a tag changes what ANY open card shows
    // (its `tags` are a snapshot at fetch time) — invalidate the whole root.
    const invalidate = () => invalidateEverything(qc);

    const create = useMutation({
      mutationFn: (body: { nome: string; cor: string }) => api.post<Tag>(`${basePath}/tags`, body),
      onSuccess: invalidate,
    });

    const update = useMutation({
      mutationFn: ({ tagId, body }: { tagId: string; body: { nome?: string; cor?: string } }) =>
        api.patch<Tag>(`${basePath}/tags/${encodeURIComponent(tagId)}`, body),
      onSuccess: invalidate,
    });

    const remove = useMutation({
      mutationFn: (tagId: string) => api.delete(`${basePath}/tags/${encodeURIComponent(tagId)}`),
      onSuccess: invalidate,
    });

    return { create, update, remove };
  }

  /**
   * PUT the full tag set for one card — optimistic: the chip flips instantly
   * and a failure rolls `tags` back to the pre-toggle snapshot rather than
   * leaving a checked box the server never accepted. Re-confirms `card` only.
   */
  function useSetTagsMutation(id: string) {
    const qc = useQueryClient();

    return useMutation({
      mutationFn: (tagIds: string[]) =>
        api.put<ItemsEnvelope<Tag>>(`${entityBase(id)}/tags`, { tag_ids: tagIds }),
      onMutate: async (tagIds: string[]) => {
        await qc.cancelQueries({ queryKey: keys.card(id) });
        const previous = qc.getQueryData<TResumo>(keys.card(id));
        if (previous) {
          const allTags = qc.getQueryData<Tag[]>(keys.tags) ?? previous.tags;
          const optimisticTags = allTags.filter((t) => tagIds.includes(t.id));
          qc.setQueryData<TResumo>(keys.card(id), { ...previous, tags: optimisticTags });
        }
        return { previous };
      },
      onError: (_err, _vars, context) => {
        if (context?.previous) qc.setQueryData(keys.card(id), context.previous);
      },
      onSettled: () => qc.invalidateQueries({ queryKey: keys.card(id) }),
    });
  }

  // ─── Membros ─────────────────────────────────────────────────────────────

  function useCardMembros(id: string | null) {
    return useQuery({
      queryKey: keys.membros(id ?? "__none__"),
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<Membro>>(`${entityBase(id as string)}/membros`);
        return res?.items ?? [];
      },
      enabled: !!id,
    });
  }

  /**
   * PUT the card's member set. The body key is the member source's FK column
   * (SW: `lead_corretor_ids`) — `memberIdsField`, default `membro_ids`.
   */
  function useSetMembrosMutation(id: string, memberIdsField = "membro_ids") {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (memberIds: string[]) =>
        api.put<ItemsEnvelope<Membro>>(`${entityBase(id)}/membros`, {
          [memberIdsField]: memberIds,
        }),
      onSuccess: () =>
        Promise.all([
          qc.invalidateQueries({ queryKey: keys.card(id) }),
          qc.invalidateQueries({ queryKey: keys.membros(id) }),
        ]),
    });
  }

  // ─── Checklists ──────────────────────────────────────────────────────────

  function useChecklists(id: string | null) {
    return useQuery({
      queryKey: keys.checklists(id ?? "__none__"),
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<Checklist>>(`${entityBase(id as string)}/checklists`);
        return res?.items ?? [];
      },
      enabled: !!id,
    });
  }

  function useChecklistMutations(id: string) {
    const qc = useQueryClient();
    const invalidate = () => invalidateChecklistFamily(qc, id);
    const base = entityBase(id);
    const itemPath = (checklistId: string, itemId: string) =>
      `${base}/checklists/${encodeURIComponent(checklistId)}/itens/${encodeURIComponent(itemId)}`;

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

    /** Optimistic — a namespaced temporary id, whole list rolled back on failure. */
    const addItem = useMutation({
      mutationFn: ({ checklistId, texto }: { checklistId: string; texto: string }) =>
        api.post(`${base}/checklists/${encodeURIComponent(checklistId)}/itens`, { texto }),
      onMutate: async ({ checklistId, texto }) => {
        await qc.cancelQueries({ queryKey: keys.checklists(id) });
        const previous = qc.getQueryData<Checklist[]>(keys.checklists(id));
        if (previous) {
          qc.setQueryData<Checklist[]>(
            keys.checklists(id),
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
        if (context?.previous) qc.setQueryData(keys.checklists(id), context.previous);
      },
      onSettled: invalidate,
    });

    /** Optimistic — the checkbox flips the instant it is clicked. */
    const toggleItem = useMutation({
      mutationFn: ({
        checklistId,
        itemId,
        concluido,
      }: {
        checklistId: string;
        itemId: string;
        concluido: boolean;
      }) => api.patch(itemPath(checklistId, itemId), { concluido }),
      onMutate: async ({ checklistId, itemId, concluido }) => {
        await qc.cancelQueries({ queryKey: keys.checklists(id) });
        const previous = qc.getQueryData<Checklist[]>(keys.checklists(id));
        if (previous) {
          qc.setQueryData<Checklist[]>(
            keys.checklists(id),
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
        if (context?.previous) qc.setQueryData(keys.checklists(id), context.previous);
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
      }) => api.patch(itemPath(checklistId, itemId), { texto }),
      onSuccess: invalidate,
    });

    const removeItem = useMutation({
      mutationFn: ({ checklistId, itemId }: { checklistId: string; itemId: string }) =>
        api.delete(itemPath(checklistId, itemId)),
      onMutate: async ({ checklistId, itemId }) => {
        await qc.cancelQueries({ queryKey: keys.checklists(id) });
        const previous = qc.getQueryData<Checklist[]>(keys.checklists(id));
        if (previous) {
          qc.setQueryData<Checklist[]>(
            keys.checklists(id),
            previous.map((c) =>
              c.id === checklistId ? { ...c, itens: c.itens.filter((i) => i.id !== itemId) } : c,
            ),
          );
        }
        return { previous };
      },
      onError: (_err, _vars, context) => {
        if (context?.previous) qc.setQueryData(keys.checklists(id), context.previous);
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

  // ─── Documentos (LGPD) ───────────────────────────────────────────────────

  function useDocumentos(id: string | null) {
    return useQuery({
      queryKey: keys.documentos(id ?? "__none__"),
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<Documento>>(`${entityBase(id as string)}/documentos`);
        return res?.items ?? [];
      },
      enabled: !!id,
    });
  }

  function useTiposDocumento() {
    return useQuery({
      queryKey: keys.tiposDocumento,
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<TipoDocumento>>(`${basePath}/documentos/tipos`);
        return res?.items ?? [];
      },
    });
  }

  function useDocumentoAcessos(id: string | null, documentoId: string | null) {
    return useQuery({
      queryKey: keys.acessos(id ?? "__none__", documentoId ?? "__none__"),
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<Acesso>>(
          `${entityBase(id as string)}/documentos/${encodeURIComponent(documentoId as string)}/acessos`,
        );
        return res?.items ?? [];
      },
      enabled: !!id && !!documentoId,
    });
  }

  /**
   * An attachment write touches `documentos`, `card` (`badges.documentos`),
   * the `timeline` (a `documento` entry) and whatever the product named in
   * `documentoInvalidates` — never the whole family.
   */
  function useDocumentoMutations(id: string) {
    const qc = useQueryClient();
    const invalidate = () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: keys.documentos(id) }),
        qc.invalidateQueries({ queryKey: keys.card(id) }),
        ...documentoInvalidates.map((sub) =>
          qc.invalidateQueries({ queryKey: [...keys.family(id), sub] }),
        ),
        qc.invalidateQueries({ queryKey: keys.timelineAll(id) }),
      ]);
    const base = entityBase(id);

    // Multipart through the seed client's `upload` — never `post`, which
    // would JSON-stringify the FormData into `{}`.
    const upload = useMutation({
      mutationFn: ({ file, tipoDocumento }: { file: File; tipoDocumento: string }) => {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("tipo_documento", tipoDocumento);
        return api.upload<Documento>(`${base}/documentos`, formData);
      },
      onSuccess: invalidate,
    });

    // `motivo` travels as a REQUIRED query param (LGPD access log), not a body.
    const remove = useMutation({
      mutationFn: ({ documentoId, motivo }: { documentoId: string; motivo: string }) =>
        api.delete(
          `${base}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
        ),
      onSuccess: invalidate,
    });

    // 🔴 Each call is a RECORDED access — never call it speculatively.
    const getUrl = useMutation({
      mutationFn: ({
        documentoId,
        intent = "view",
      }: {
        documentoId: string;
        intent?: "view" | "download";
      }) =>
        api.get<DocumentoUrlResponse>(
          `${base}/documentos/${encodeURIComponent(documentoId)}/url?intent=${intent}`,
        ),
    });

    // Re-queues a stuck/never-run extraction — never delete + re-upload,
    // which would destroy the LGPD access log.
    const reextrair = useMutation({
      mutationFn: (documentoId: string) =>
        api.post<Documento>(`${base}/documentos/${encodeURIComponent(documentoId)}/extrair`),
      onSuccess: invalidate,
    });

    return { upload, remove, getUrl, reextrair };
  }

  // ─── Checklist extras (operator-created rows) ───────────────────────────

  function useChecklistExtras(id: string | null) {
    return useQuery({
      queryKey: keys.checklistExtras(id ?? "__none__"),
      queryFn: async () => {
        const res = await api.get<ChecklistExtrasResponse>(
          `${entityBase(id as string)}/checklist-extras`,
        );
        return res?.items ?? [];
      },
      enabled: !!id,
    });
  }

  /**
   * NOT optimistic: these create/destroy rows whose ids the server assigns.
   * Discarding a row's FILE (`DELETE .../{extraId}/documento`) keeps the row;
   * `DELETE .../{extraId}` removes the row. Invalidates ONLY the extras list.
   */
  function useChecklistExtraMutations(id: string) {
    const qc = useQueryClient();
    const base = `${entityBase(id)}/checklist-extras`;
    const invalidate = () => qc.invalidateQueries({ queryKey: keys.checklistExtras(id) });

    const criar = useMutation({
      mutationFn: (body: { label: string; tipo: ChecklistExtraTipo }) =>
        api.post<ChecklistExtra>(base, body),
      onSuccess: invalidate,
    });

    const atualizar = useMutation({
      mutationFn: ({
        extraId,
        body,
      }: {
        extraId: string;
        body: { label?: string; valor_texto?: string | null; ordem?: number };
      }) => api.patch<ChecklistExtra>(`${base}/${encodeURIComponent(extraId)}`, body),
      onSuccess: invalidate,
    });

    const remover = useMutation({
      mutationFn: (extraId: string) => api.delete(`${base}/${encodeURIComponent(extraId)}`),
      onSuccess: invalidate,
    });

    const uploadDocumento = useMutation({
      mutationFn: ({ extraId, file }: { extraId: string; file: File }) => {
        const formData = new FormData();
        formData.append("file", file);
        return api.upload<ChecklistExtra>(`${base}/${encodeURIComponent(extraId)}/documento`, formData);
      },
      onSuccess: invalidate,
    });

    const removerDocumento = useMutation({
      mutationFn: (extraId: string) => api.delete(`${base}/${encodeURIComponent(extraId)}/documento`),
      onSuccess: invalidate,
    });

    return { criar, atualizar, remover, uploadDocumento, removerDocumento };
  }

  return {
    descriptor,
    keys,
    useCardResumo,
    useTimeline,
    useNotaMutations,
    useTags,
    useTagCatalogMutations,
    useSetTagsMutation,
    useCardMembros,
    useSetMembrosMutation,
    useChecklists,
    useChecklistMutations,
    useDocumentos,
    useTiposDocumento,
    useDocumentoAcessos,
    useDocumentoMutations,
    useChecklistExtras,
    useChecklistExtraMutations,
  };
}

export type CardHubHooks<TResumo extends CardResumoBase = CardResumoBase> = ReturnType<
  typeof createCardHubHooks<TResumo>
>;
