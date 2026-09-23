/**
 * Knowledge hooks — Agent Studio CONTRACT.md §D3.
 *
 * `agents.knowledge_collections` / `agents.knowledge_documents` are
 * agent-scoped (not version-scoped, §B2) — collections and documents are
 * queried/mutated directly against `/api/studio/agents/{key}/knowledge*`,
 * with no draft concept. Loading signals follow
 * `KB § PATTERNS/frontend/lying-loading-state.md`:
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`,
 * never a bare `isLoading`. The documents list is key-changing (collection,
 * search, filter, page) so it carries `placeholderData: (prev) => prev`.
 *
 * `# Base de conhecimento` (§C.3) lists each collection's `doc_count`, so any
 * mutation that can move that count (a collection's own fields, a document
 * created/edited/(de)activated) also invalidates `studioKeys.compiledAll` —
 * otherwise the inspector shows a stale count until an unrelated refetch.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { knowledgeDocumentsBatchPath } from "@/api/studio/batchPaths";
import { api } from "@/lib/api";
import type {
  Document,
  DocumentCreate,
  DocumentListResponse,
  DocumentPatch,
  DocumentRevisionsResponse,
  DocumentTipo,
  KnowledgeCollectionCreate,
  KnowledgeCollectionPatch,
  KnowledgeCollectionsResponse,
  KnowledgeDocumentBatchItem,
  KnowledgeDocumentsBatchResponse,
  KnowledgeSearchResponse,
} from "@/api/studio/types-ke";
import { studioKeys } from "./keys";

const collectionsKey = (agentKey: string) => ["studio", agentKey, "knowledge", "collections"] as const;
const documentsKey = (
  agentKey: string,
  collectionId: string,
  filters: { q?: string; tipo?: DocumentTipo | ""; page?: number; page_size?: number },
) => ["studio", agentKey, "knowledge", "collections", collectionId, "documents", filters] as const;
const documentKey = (agentKey: string, docId: string) => ["studio", agentKey, "knowledge", "documents", docId] as const;
const revisionsKey = (agentKey: string, docId: string) =>
  ["studio", agentKey, "knowledge", "documents", docId, "revisions"] as const;
const searchKey = (agentKey: string, q: string, colecao: string, limite: number) =>
  ["studio", agentKey, "knowledge", "search", q, colecao, limite] as const;

// ─── Collections ────────────────────────────────────────────────────────────

export function useKnowledgeCollections(agentKey: string) {
  const query = useQuery<KnowledgeCollectionsResponse>({
    queryKey: collectionsKey(agentKey),
    queryFn: () => api.get<KnowledgeCollectionsResponse>(`/api/studio/agents/${agentKey}/knowledge`),
    enabled: !!agentKey,
  });

  return {
    data: query.data?.colecoes,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useCreateKnowledgeCollection(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: KnowledgeCollectionCreate) =>
      api.post(`/api/studio/agents/${agentKey}/knowledge`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionsKey(agentKey) });
      qc.invalidateQueries({ queryKey: studioKeys.compiledAll(agentKey) });
    },
  });
}

export function useUpdateKnowledgeCollection(agentKey: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, patch }: { collectionId: string; patch: KnowledgeCollectionPatch }) =>
      api.patch(`/api/studio/agents/${agentKey}/knowledge/${collectionId}`, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: collectionsKey(agentKey) });
      qc.invalidateQueries({ queryKey: studioKeys.compiledAll(agentKey) });
    },
  });
}

// ─── Documents ──────────────────────────────────────────────────────────────

export interface DocumentFilters {
  q?: string;
  tipo?: DocumentTipo | "";
  page?: number;
  page_size?: number;
}

export function useDocuments(agentKey: string, collectionId: string | null, filters: DocumentFilters = {}) {
  const query = useQuery<DocumentListResponse>({
    queryKey: documentsKey(agentKey, collectionId ?? "", filters),
    queryFn: () =>
      api.get<DocumentListResponse>(`/api/studio/agents/${agentKey}/knowledge/${collectionId}/documents`, {
        q: filters.q || undefined,
        tipo: filters.tipo || undefined,
        page: filters.page,
        page_size: filters.page_size,
      }),
    enabled: !!agentKey && !!collectionId,
    // Key-changing query (collection/search/filter/page) — keeps the
    // previous page's rows on screen instead of flashing empty.
    placeholderData: (prev) => prev,
  });

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useCreateDocument(agentKey: string, collectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DocumentCreate) =>
      api.post<Document>(`/api/studio/agents/${agentKey}/knowledge/${collectionId}/documents`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["studio", agentKey, "knowledge", "collections", collectionId, "documents"] });
      qc.invalidateQueries({ queryKey: collectionsKey(agentKey) });
      qc.invalidateQueries({ queryKey: studioKeys.compiledAll(agentKey) });
    },
  });
}

/**
 * ONE call to `knowledgeDocumentsBatchPath` (max `KNOWLEDGE_DOCUMENTS_BATCH_MAX`
 * documents — `@/api/studio/batchPaths.ts`). Chunking a larger upload into
 * several calls is the UI's job (`sendInChunks`, `@/lib/batchUpload.ts`) —
 * this hook is deliberately one wire call per `mutateAsync`, so the caller
 * controls sequencing/progress instead of a mutation hiding a loop.
 */
export function useBatchCreateDocuments(agentKey: string, collectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentos: KnowledgeDocumentBatchItem[]) =>
      api.post<KnowledgeDocumentsBatchResponse>(knowledgeDocumentsBatchPath(agentKey, collectionId), { documentos }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["studio", agentKey, "knowledge", "collections", collectionId, "documents"] });
      qc.invalidateQueries({ queryKey: collectionsKey(agentKey) });
      qc.invalidateQueries({ queryKey: studioKeys.compiledAll(agentKey) });
    },
  });
}

export function useDocument(agentKey: string, docId: string | null) {
  const query = useQuery<Document>({
    queryKey: documentKey(agentKey, docId ?? ""),
    queryFn: () => api.get<Document>(`/api/studio/agents/${agentKey}/documents/${docId}`),
    enabled: !!agentKey && !!docId,
  });

  return {
    data: query.data,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
    error: query.error,
  };
}

export function useUpdateDocument(agentKey: string, docId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: DocumentPatch) => api.patch<Document>(`/api/studio/agents/${agentKey}/documents/${docId}`, patch),
    onSuccess: (updated) => {
      qc.setQueryData(documentKey(agentKey, docId), updated);
      qc.invalidateQueries({ queryKey: ["studio", agentKey, "knowledge"] });
      qc.invalidateQueries({ queryKey: revisionsKey(agentKey, docId) });
      qc.invalidateQueries({ queryKey: studioKeys.compiledAll(agentKey) });
    },
  });
}

export function useDocumentRevisions(agentKey: string, docId: string | null) {
  const query = useQuery<DocumentRevisionsResponse>({
    queryKey: revisionsKey(agentKey, docId ?? ""),
    queryFn: () => api.get<DocumentRevisionsResponse>(`/api/studio/agents/${agentKey}/documents/${docId}/revisions`),
    enabled: !!agentKey && !!docId,
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
  };
}

// ─── Search playground ──────────────────────────────────────────────────────

export function useKnowledgeSearch(agentKey: string, q: string, colecao = "", limite = 8) {
  const query = useQuery<KnowledgeSearchResponse>({
    queryKey: searchKey(agentKey, q, colecao, limite),
    queryFn: () =>
      api.get<KnowledgeSearchResponse>(`/api/studio/agents/${agentKey}/knowledge/search`, {
        q,
        colecao: colecao || undefined,
        limite,
      }),
    enabled: !!agentKey && q.trim().length > 0,
    placeholderData: (prev) => prev,
  });

  return {
    data: query.data?.items,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
    isError: query.isError,
  };
}
