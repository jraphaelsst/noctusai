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
  Acesso,
  Checklist,
  ChecklistOrigem,
  Documento,
  DocumentoUrlResponse,
  ItemsEnvelope,
  CardDatas,
  CardResumo,
  DatasPatchBody,
  DatasPatchResponse,
  Membro,
  Nota,
  Tag,
  TimelineEntry,
  TimelineKind,
  TimelinePage,
  TipoDocumento,
} from "@/types/cardHub";

// ─── Query keys ─────────────────────────────────────────────────────────────

const ROOT_KEY = ["sw", "cardHub"] as const;
const FAMILY_KEY = (clienteId: string) => [...ROOT_KEY, clienteId] as const;
const CARD_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "card"] as const;
const TIMELINE_KEY = (clienteId: string, kinds?: TimelineKind[]) =>
  [...FAMILY_KEY(clienteId), "timeline", kinds ?? "all"] as const;
const MEMBROS_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "membros"] as const;
const CHECKLISTS_KEY = (clienteId: string) => [...FAMILY_KEY(clienteId), "checklists"] as const;
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

  const create = useMutation({
    mutationFn: (corpo: string) =>
      api.post<Nota>(`${clienteBase(clienteId)}/notas`, { corpo }),
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

export function useDatasMutation(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: DatasPatchBody) =>
      api.patch<DatasPatchResponse>(`${clienteBase(clienteId)}/datas`, body),
    onSuccess: (resolved) => {
      const previous = qc.getQueryData<CardResumo>(CARD_KEY(clienteId));
      if (previous) {
        const datas: CardDatas = {
          data_inicio: resolved.data_inicio,
          data_entrega: resolved.data_entrega,
          entrega_concluida: resolved.entrega_concluida,
          lembrete_minutos_antes: resolved.lembrete_minutos_antes,
          recorrencia: resolved.recorrencia,
        };
        qc.setQueryData<CardResumo>(CARD_KEY(clienteId), { ...previous, datas });
      }
      invalidateCliente(qc, clienteId);
    },
  });
}

// ─── Checklists (D11 — both halves) ────────────────────────────────────────

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
  const invalidate = () => invalidateCliente(qc, clienteId);
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

  const addItem = useMutation({
    mutationFn: ({ checklistId, texto }: { checklistId: string; texto: string }) =>
      api.post(`${base}/checklists/${encodeURIComponent(checklistId)}/itens`, { texto }),
    onSuccess: invalidate,
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
    onSuccess: invalidate,
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

  // The seed `ApiClient.delete()` is body-less (`delete<T>(path: string)`),
  // but §3 spells this route as `DELETE .../documentos/{did} {motivo}` — a
  // JSON body on DELETE. Raw `fetch` supports that fine; the wrapper just
  // doesn't expose it (flagged in this slice's `drift-found:` footer as a
  // seed-`api`-client gap, not silently worked around with a query param).
  const remove = useMutation({
    mutationFn: async ({ documentoId, motivo }: { documentoId: string; motivo: string }) => {
      const headers = { "Content-Type": "application/json", ...(await getAuthHeader()) };
      const response = await fetch(apiUrl(`${base}/documentos/${encodeURIComponent(documentoId)}`), {
        method: "DELETE",
        headers,
        body: JSON.stringify({ motivo }),
      });
      if (!response.ok && response.status !== 204) {
        const detail = await response.json().catch(() => null);
        const message = detail?.error?.message ?? `Erro HTTP ${response.status}`;
        throw new Error(message);
      }
    },
    onSuccess: invalidate,
  });

  const getUrl = useMutation({
    mutationFn: (documentoId: string) =>
      api.get<DocumentoUrlResponse>(`${base}/documentos/${encodeURIComponent(documentoId)}/url`),
  });

  return { upload, remove, getUrl };
}
