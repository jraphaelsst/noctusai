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
import type { InfiniteData } from "@tanstack/react-query";

import type { ApiClient } from "../../api";
import { listOps, useCacheWriteMutation } from "../../cache-writes";
import { prepareImageForUpload } from "../../imageUpload";
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
  Lembrete,
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
    lembretes: (id: string) => [...ROOT_KEY, id, "lembretes"] as const,
    checklists: (id: string) => [...ROOT_KEY, id, "checklists"] as const,
    checklistExtras: (id: string) => [...ROOT_KEY, id, "checklist-extras"] as const,
    documentos: (id: string) => [...ROOT_KEY, id, "documentos"] as const,
    acessos: (id: string, documentoId: string) =>
      [...ROOT_KEY, id, "documentos", documentoId, "acessos"] as const,
    tags: [...ROOT_KEY, "tags"] as const,
    tiposDocumento: [...ROOT_KEY, "tiposDocumento"] as const,
  };

  const entityBase = (id: string) => `${basePath}/${encodeURIComponent(id)}`;

  /** Renaming/recolouring/deleting a tag changes what ANY open card shows (its `tags` are a snapshot at
   *  fetch time) — the whole root settles. */
  const everything = [ROOT_KEY] as const;

  /** A checklist edit changes the checklists, the card's badges (item counts) and the timeline (the
   *  activity entry) — nothing else. The derived reads are refreshed; the checklists read is written. */
  const checklistDerived = (id: string) => [keys.card(id), keys.timelineAll(id)];

  // ─── Cache edits shared by the writes below ──────────────────────────────

  type TimelineData = InfiniteData<TimelinePage>;
  const hasPages = (d: unknown): d is TimelineData => !!d && Array.isArray((d as TimelineData).pages);

  /** Put an entry at the top of the newest page of a (cached) timeline. */
  function timelinePrepend(old: TimelineData | undefined, entry: TimelineEntry): TimelineData | undefined {
    if (!hasPages(old) || old.pages.length === 0) return old;
    const [first, ...rest] = old.pages;
    const items = [entry, ...first.items.filter((e) => e.id !== entry.id)];
    return { ...old, pages: [{ ...first, items, total: first.total + (items.length - first.items.length) }, ...rest] };
  }

  /** Merge `changes` into the entry `entryId` wherever it sits in a (cached) timeline. */
  function timelinePatch(old: TimelineData | undefined, entryId: string, changes: Record<string, unknown>): TimelineData | undefined {
    if (!hasPages(old)) return old;
    return {
      ...old,
      pages: old.pages.map((pg) => ({
        ...pg,
        items: pg.items.map((e) => (e.id === entryId ? ({ ...e, ...changes } as TimelineEntry) : e)),
      })),
    };
  }

  /** A comentario as the timeline renders it. */
  const notaEntry = (n: Nota): TimelineEntry => ({
    id: n.id,
    kind: "nota",
    ocorrido_em: new Date().toISOString(),
    ator: n.autor,
    corpo: n.corpo,
    autor: n.autor,
    editado_em: n.editado_em,
    deleted_at: n.deleted_at,
  });

  /** Patch the cached card summary; an uncached card stays uncached. */
  const patchCard = (old: TResumo | undefined, fn: (card: TResumo) => Partial<TResumo>): TResumo | undefined =>
    old ? { ...old, ...fn(old) } : old;

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
    // The timeline cached WITHOUT a kinds filter gets the nota itself; filtered timelines converge on settle.
    const create = useCacheWriteMutation<Nota, { corpo: string; tipo?: NotaTipo }>({
      mutationFn: ({ corpo, tipo = "comentario" }) =>
        api.post<Nota>(`${entityBase(id)}/notas`, { corpo, tipo }),
      // The author comes from the server, so this commits (no stand-in): the note is on screen after ONE
      // round trip, not write + two refetches.
      targets: ({ tipo = "comentario" }) => [
        {
          queryKey: keys.card(id),
          commit: (old: TResumo | undefined, nota) =>
            patchCard(old, (c) =>
              tipo === "descricao"
                ? ({
                    descricao: { id: nota.id, corpo: nota.corpo, editado_em: nota.editado_em },
                    badges: { ...c.badges, tem_descricao: true },
                  } as Partial<TResumo>)
                : ({ badges: { ...c.badges, notas: c.badges.notas + 1 } } as Partial<TResumo>),
            ),
        },
        ...(tipo === "descricao"
          ? []
          : [
              {
                queryKey: keys.timeline(id),
                commit: (old: TimelineData | undefined, nota: Nota) => timelinePrepend(old, notaEntry(nota)),
              },
            ]),
      ],
      invalidate: [keys.timelineAll(id)],
    });

    const update = useCacheWriteMutation<Nota, { notaId: string; corpo: string }>({
      mutationFn: ({ notaId, corpo }) =>
        api.patch<Nota>(`${entityBase(id)}/notas/${encodeURIComponent(notaId)}`, { corpo }),
      targets: ({ notaId, corpo }) => [
        {
          queryKey: keys.card(id),
          optimistic: (old: TResumo | undefined) =>
            patchCard(old, (c) =>
              c.descricao?.id === notaId ? ({ descricao: { ...c.descricao, corpo } } as Partial<TResumo>) : {},
            ),
          commit: (old: TResumo | undefined, nota) =>
            patchCard(old, (c) =>
              c.descricao?.id === notaId
                ? ({ descricao: { ...c.descricao, corpo: nota.corpo, editado_em: nota.editado_em } } as Partial<TResumo>)
                : {},
            ),
        },
        {
          queryKey: keys.timeline(id),
          optimistic: (old: TimelineData | undefined) => timelinePatch(old, notaId, { corpo }),
          commit: (old: TimelineData | undefined, nota) =>
            timelinePatch(old, notaId, { corpo: nota.corpo, editado_em: nota.editado_em }),
        },
      ],
      invalidate: [keys.timelineAll(id)],
    });

    const remove = useCacheWriteMutation<unknown, string>({
      mutationFn: (notaId) => api.delete(`${entityBase(id)}/notas/${encodeURIComponent(notaId)}`),
      // A deleted comentario keeps its timeline slot as a tombstone (`deleted_at`); a deleted descricao
      // empties the card's description. Either way the badge follows.
      targets: (notaId) => [
        {
          queryKey: keys.card(id),
          optimistic: (old: TResumo | undefined) =>
            patchCard(old, (c) =>
              c.descricao?.id === notaId
                ? ({ descricao: null, badges: { ...c.badges, tem_descricao: false } } as Partial<TResumo>)
                : ({ badges: { ...c.badges, notas: Math.max(0, c.badges.notas - 1) } } as Partial<TResumo>),
            ),
        },
        {
          queryKey: keys.timeline(id),
          optimistic: (old: TimelineData | undefined) =>
            timelinePatch(old, notaId, { deleted_at: new Date().toISOString() }),
        },
      ],
      invalidate: [keys.timelineAll(id)],
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
    // Renaming/recolouring/deleting a tag changes what ANY open card shows (its `tags` are a snapshot at
    // fetch time) — the catalogue is written, the whole root settles.
    const create = useCacheWriteMutation<Tag, { nome: string; cor: string }>({
      mutationFn: (body) => api.post<Tag>(`${basePath}/tags`, body),
      targets: [{ queryKey: keys.tags, commit: (old: Tag[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
      invalidate: [...everything],
    });

    const update = useCacheWriteMutation<Tag, { tagId: string; body: { nome?: string; cor?: string } }>({
      mutationFn: ({ tagId, body }) => api.patch<Tag>(`${basePath}/tags/${encodeURIComponent(tagId)}`, body),
      targets: ({ tagId, body }) => [
        {
          queryKey: keys.tags,
          optimistic: (old: Tag[] | undefined) => listOps.patch(old, tagId, body),
          commit: (old: Tag[] | undefined, saved) => listOps.patch(old, tagId, saved),
        },
      ],
      invalidate: [...everything],
    });

    const remove = useCacheWriteMutation<unknown, string>({
      mutationFn: (tagId) => api.delete(`${basePath}/tags/${encodeURIComponent(tagId)}`),
      targets: (tagId) => [
        { queryKey: keys.tags, optimistic: (old: Tag[] | undefined) => listOps.remove(old, tagId) },
      ],
      invalidate: [...everything],
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
    return useCacheWriteMutation<ItemsEnvelope<Tag>, string[]>({
      mutationFn: (tagIds) => api.put<ItemsEnvelope<Tag>>(`${entityBase(id)}/tags`, { tag_ids: tagIds }),
      targets: (tagIds) => [
        {
          queryKey: keys.card(id),
          optimistic: (old: TResumo | undefined) => {
            if (!old) return old;
            const allTags = qc.getQueryData<Tag[]>(keys.tags) ?? old.tags;
            return { ...old, tags: allTags.filter((t) => tagIds.includes(t.id)) };
          },
          commit: (old: TResumo | undefined, res) => (old ? { ...old, tags: res?.items ?? old.tags } : old),
        },
      ],
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
    return useCacheWriteMutation<ItemsEnvelope<Membro>, string[]>({
      mutationFn: (memberIds) =>
        api.put<ItemsEnvelope<Membro>>(`${entityBase(id)}/membros`, {
          [memberIdsField]: memberIds,
        }),
      // The server resolves ids to members (name, colour): commit its answer into the card and the roster.
      targets: [
        {
          queryKey: keys.card(id),
          commit: (old: TResumo | undefined, res) => (old && res?.items ? { ...old, membros: res.items } : old),
        },
        { queryKey: keys.membros(id), commit: (old: Membro[] | undefined, res) => (old && res?.items ? res.items : old) },
      ],
    });
  }

  // ─── Lembretes (ad-hoc CRUD, `lembretes_crud` opt-in) ───────────────────

  function useLembretes(id: string | null) {
    return useQuery({
      queryKey: keys.lembretes(id ?? "__none__"),
      queryFn: async () => {
        const res = await api.get<ItemsEnvelope<Lembrete>>(`${entityBase(id as string)}/lembretes`);
        return res?.items ?? [];
      },
      enabled: !!id,
    });
  }

  /**
   * Create/edit/delete touch a row the badges/timeline never derive from, so only the lembretes list
   * is written: create commits the server's row (it assigns the id), edit draws the plain fields,
   * delete leaves on click. Each rolls back on failure.
   */
  function useLembreteMutations(id: string) {
    const base = `${entityBase(id)}/lembretes`;

    const criar = useCacheWriteMutation<Lembrete, { titulo: string; dispara_em: string; responsavel_id?: string | null }>({
      mutationFn: (body) => api.post<Lembrete>(base, body),
      // The server assigns the id and resolves the responsavel: commit its row (no stand-in).
      targets: [{ queryKey: keys.lembretes(id), commit: (old: Lembrete[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
    });

    const atualizar = useCacheWriteMutation<
      Lembrete,
      {
        lembreteId: string;
        body: { titulo?: string; dispara_em?: string; responsavel_id?: string | null; concluido?: boolean };
      }
    >({
      mutationFn: ({ lembreteId, body }) => api.patch<Lembrete>(`${base}/${encodeURIComponent(lembreteId)}`, body),
      targets: ({ lembreteId, body }) => [
        {
          queryKey: keys.lembretes(id),
          // Only the plain fields are drawn on click: `responsavel_id` needs the server's member lookup,
          // and `dispara_em` the server's UTC normalisation.
          optimistic: (old: Lembrete[] | undefined) =>
            listOps.patch(old, lembreteId, {
              ...(body.titulo !== undefined ? { titulo: body.titulo } : {}),
              ...(body.concluido !== undefined ? { concluido: body.concluido } : {}),
            }),
          commit: (old: Lembrete[] | undefined, saved) => listOps.patch(old, lembreteId, saved),
        },
      ],
    });

    const remover = useCacheWriteMutation<unknown, string>({
      mutationFn: (lembreteId) => api.delete(`${base}/${encodeURIComponent(lembreteId)}`),
      targets: (lembreteId) => [
        { queryKey: keys.lembretes(id), optimistic: (old: Lembrete[] | undefined) => listOps.remove(old, lembreteId) },
      ],
    });

    return { criar, atualizar, remover };
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
    const base = entityBase(id);
    const itemPath = (checklistId: string, itemId: string) =>
      `${base}/checklists/${encodeURIComponent(checklistId)}/itens/${encodeURIComponent(itemId)}`;
    /** Edit one checklist inside the cached list. */
    const onChecklist = (old: Checklist[] | undefined, checklistId: string, fn: (c: Checklist) => Checklist) =>
      Array.isArray(old) ? old.map((c) => (c.id === checklistId ? fn(c) : c)) : old;
    /** `concluidos` / `total_itens` are served, but follow from the items the click just changed. */
    const recount = (c: Checklist): Checklist => ({
      ...c,
      total_itens: c.itens.length,
      concluidos: c.itens.filter((i) => i.concluido).length,
    });

    const createChecklist = useCacheWriteMutation<Checklist, string>({
      mutationFn: (titulo) => api.post<Checklist>(`${base}/checklists`, { titulo }),
      targets: [{ queryKey: keys.checklists(id), commit: (old: Checklist[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
      invalidate: checklistDerived(id),
    });

    const renameChecklist = useCacheWriteMutation<Checklist, { checklistId: string; titulo: string }>({
      mutationFn: ({ checklistId, titulo }) =>
        api.patch<Checklist>(`${base}/checklists/${encodeURIComponent(checklistId)}`, { titulo }),
      targets: ({ checklistId, titulo }) => [
        {
          queryKey: keys.checklists(id),
          optimistic: (old: Checklist[] | undefined) => listOps.patch(old, checklistId, { titulo }),
          commit: (old: Checklist[] | undefined, saved) => listOps.patch(old, checklistId, { titulo: saved.titulo }),
        },
      ],
      invalidate: checklistDerived(id),
    });

    const removeChecklist = useCacheWriteMutation<unknown, string>({
      mutationFn: (checklistId) => api.delete(`${base}/checklists/${encodeURIComponent(checklistId)}`),
      targets: (checklistId) => [
        { queryKey: keys.checklists(id), optimistic: (old: Checklist[] | undefined) => listOps.remove(old, checklistId) },
      ],
      invalidate: checklistDerived(id),
    });

    /** Optimistic — a namespaced temporary id; the settle refetch brings the server's item (the POST
     *  answer is not typed, so there is no commit). Whole list rolled back on failure. */
    const addItem = useCacheWriteMutation<unknown, { checklistId: string; texto: string }>({
      mutationFn: ({ checklistId, texto }) =>
        api.post(`${base}/checklists/${encodeURIComponent(checklistId)}/itens`, { texto }),
      targets: ({ checklistId, texto }) => [
        {
          queryKey: keys.checklists(id),
          optimistic: (old: Checklist[] | undefined, _vars, { tempId }) =>
            onChecklist(old, checklistId, (c) => ({
              ...c,
              itens: [
                ...c.itens,
                {
                  id: `${tempId}:${checklistId}:${c.itens.length}`,
                  texto,
                  concluido: false,
                  concluido_em: null,
                  concluido_por: null,
                  posicao: c.itens.length,
                },
              ],
            })),
        },
      ],
      invalidate: checklistDerived(id),
    });

    /** Optimistic — the checkbox flips the instant it is clicked. */
    const toggleItem = useCacheWriteMutation<unknown, { checklistId: string; itemId: string; concluido: boolean }>({
      mutationFn: ({ checklistId, itemId, concluido }) => api.patch(itemPath(checklistId, itemId), { concluido }),
      targets: ({ checklistId, itemId, concluido }) => [
        {
          queryKey: keys.checklists(id),
          optimistic: (old: Checklist[] | undefined) =>
            onChecklist(old, checklistId, (cl) => ({
              ...cl,
              itens: cl.itens.map((it) => (it.id === itemId ? { ...it, concluido } : it)),
              concluidos: cl.itens.filter((it) => (it.id === itemId ? concluido : it.concluido)).length,
            })),
        },
      ],
      invalidate: checklistDerived(id),
    });

    const updateItemText = useCacheWriteMutation<unknown, { checklistId: string; itemId: string; texto: string }>({
      mutationFn: ({ checklistId, itemId, texto }) => api.patch(itemPath(checklistId, itemId), { texto }),
      targets: ({ checklistId, itemId, texto }) => [
        {
          queryKey: keys.checklists(id),
          optimistic: (old: Checklist[] | undefined) =>
            onChecklist(old, checklistId, (c) => ({
              ...c,
              itens: c.itens.map((it) => (it.id === itemId ? { ...it, texto } : it)),
            })),
        },
      ],
      invalidate: checklistDerived(id),
    });

    const removeItem = useCacheWriteMutation<unknown, { checklistId: string; itemId: string }>({
      mutationFn: ({ checklistId, itemId }) => api.delete(itemPath(checklistId, itemId)),
      targets: ({ checklistId, itemId }) => [
        {
          queryKey: keys.checklists(id),
          optimistic: (old: Checklist[] | undefined) =>
            onChecklist(old, checklistId, (c) => recount({ ...c, itens: c.itens.filter((i) => i.id !== itemId) })),
        },
      ],
      invalidate: checklistDerived(id),
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
    // Derived reads (the card's badge, the timeline entry, the product's own sub-keys) only refresh;
    // the documentos list is the one the write places.
    const derived = () => [
      keys.card(id),
      ...documentoInvalidates.map((sub) => [...keys.family(id), sub] as readonly unknown[]),
      keys.timelineAll(id),
    ];
    const base = entityBase(id);

    // Multipart through the seed client's `upload` — never `post`, which
    // would JSON-stringify the FormData into `{}`.
    const upload = useCacheWriteMutation<Documento, { file: File; tipoDocumento: string }>({
      mutationFn: async ({ file, tipoDocumento }) => {
        const formData = new FormData();
        formData.append("file", await prepareImageForUpload(file));
        formData.append("tipo_documento", tipoDocumento);
        return api.upload<Documento>(`${base}/documentos`, formData);
      },
      targets: [{ queryKey: keys.documentos(id), commit: (old: Documento[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
      invalidate: derived(),
    });

    // `motivo` travels as a REQUIRED query param (LGPD access log), not a body.
    const remove = useCacheWriteMutation<unknown, { documentoId: string; motivo: string }>({
      mutationFn: ({ documentoId, motivo }) =>
        api.delete(
          `${base}/documentos/${encodeURIComponent(documentoId)}?motivo=${encodeURIComponent(motivo)}`,
        ),
      targets: ({ documentoId }) => [
        { queryKey: keys.documentos(id), optimistic: (old: Documento[] | undefined) => listOps.remove(old, documentoId) },
      ],
      invalidate: derived(),
    });

    // 🔴 Each call is a RECORDED access — never call it speculatively.
    const getUrl = useMutation({ // noc-allow: invalidate-only — a read-through: it records an LGPD access and returns a signed URL, it writes nothing any cached read shows
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
    const reextrair = useCacheWriteMutation<Documento, string>({
      mutationFn: (documentoId) =>
        api.post<Documento>(`${base}/documentos/${encodeURIComponent(documentoId)}/extrair`),
      targets: (documentoId) => [
        {
          queryKey: keys.documentos(id),
          commit: (old: Documento[] | undefined, saved) => listOps.patch(old, documentoId, saved),
        },
      ],
      invalidate: derived(),
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
   * Create/update/upload commit the SERVER's row (it assigns ids and order and derives `concluido`);
   * deletes leave on click. Discarding a row's FILE (`DELETE .../{extraId}/documento`) keeps the row;
   * `DELETE .../{extraId}` removes the row. Only the extras list is touched.
   */
  function useChecklistExtraMutations(id: string) {
    const base = `${entityBase(id)}/checklist-extras`;
    const extras = keys.checklistExtras(id);

    const criar = useCacheWriteMutation<ChecklistExtra, { label: string; tipo: ChecklistExtraTipo }>({
      mutationFn: (body) => api.post<ChecklistExtra>(base, body),
      // The server assigns the id and the order: commit its row (no stand-in).
      targets: [{ queryKey: extras, commit: (old: ChecklistExtra[] | undefined, saved) => listOps.replace(old, saved.id, saved) }],
    });

    const atualizar = useCacheWriteMutation<
      ChecklistExtra,
      { extraId: string; body: { label?: string; valor_texto?: string | null; ordem?: number } }
    >({
      mutationFn: ({ extraId, body }) => api.patch<ChecklistExtra>(`${base}/${encodeURIComponent(extraId)}`, body),
      // `concluido` is DERIVED from the value, so the server's row (not a guess) is what lands.
      targets: ({ extraId }) => [
        { queryKey: extras, commit: (old: ChecklistExtra[] | undefined, saved) => listOps.patch(old, extraId, saved) },
      ],
    });

    const remover = useCacheWriteMutation<unknown, string>({
      mutationFn: (extraId) => api.delete(`${base}/${encodeURIComponent(extraId)}`),
      targets: (extraId) => [
        { queryKey: extras, optimistic: (old: ChecklistExtra[] | undefined) => listOps.remove(old, extraId) },
      ],
    });

    const uploadDocumento = useCacheWriteMutation<ChecklistExtra, { extraId: string; file: File }>({
      mutationFn: async ({ extraId, file }) => {
        const formData = new FormData();
        formData.append("file", await prepareImageForUpload(file));
        return api.upload<ChecklistExtra>(`${base}/${encodeURIComponent(extraId)}/documento`, formData);
      },
      targets: ({ extraId }) => [
        { queryKey: extras, commit: (old: ChecklistExtra[] | undefined, saved) => listOps.patch(old, extraId, saved) },
      ],
    });

    const removerDocumento = useCacheWriteMutation<unknown, string>({
      mutationFn: (extraId) => api.delete(`${base}/${encodeURIComponent(extraId)}/documento`),
      // The row stays; its file goes, and a file row's tick follows from the file.
      targets: (extraId) => [
        {
          queryKey: extras,
          optimistic: (old: ChecklistExtra[] | undefined) =>
            Array.isArray(old)
              ? old.map((r) => (r.id === extraId && r.documento ? { ...r, documento: null, concluido: false } : r))
              : old,
        },
      ],
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
    useLembretes,
    useLembreteMutations,
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
