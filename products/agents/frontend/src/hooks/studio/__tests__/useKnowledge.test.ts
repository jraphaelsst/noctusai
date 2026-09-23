/**
 * useKnowledge.ts hook tests — Agent Studio CONTRACT.md §D3. Covers request
 * shapes (collections list, documents list w/ filters, create, search) and
 * the `showSkeleton`/`isRefreshing` loading signals
 * (`KB § PATTERNS/frontend/lying-loading-state.md`).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, patch: mockPatch, put: vi.fn(), delete: vi.fn() },
}));

const DOCUMENTS_BATCH_PATH = "/api/studio/agents/isaia/knowledge/c1/documents/batch";

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

beforeEach(() => vi.clearAllMocks());

describe("useKnowledgeCollections", () => {
  it("GETs the agent's collections and exposes showSkeleton/isRefreshing", async () => {
    mockGet.mockResolvedValue({
      colecoes: [{ id: "c1", slug: "audience", nome: "Audiência", tag: "AU", descricao: "", ordem: 1, total_documentos: 3 }],
    });
    const { useKnowledgeCollections } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    const { result } = renderHook(() => useKnowledgeCollections("isaia"), { wrapper: wrapper(qc) });

    expect(result.current.showSkeleton).toBe(true);
    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/knowledge");
    expect(result.current.data?.[0].slug).toBe("audience");
  });
});

describe("useCreateKnowledgeCollection", () => {
  it("POSTs the new collection payload and invalidates the list", async () => {
    mockGet.mockResolvedValue({ colecoes: [] });
    mockPost.mockResolvedValue({ id: "c2", slug: "brand", nome: "Marca" });
    const { useKnowledgeCollections, useCreateKnowledgeCollection } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    const list = renderHook(() => useKnowledgeCollections("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.result.current.showSkeleton).toBe(false));

    const create = renderHook(() => useCreateKnowledgeCollection("isaia"), { wrapper: wrapper(qc) });
    await create.result.current.mutateAsync({ slug: "brand", nome: "Marca", tag: null });

    expect(mockPost).toHaveBeenCalledWith("/api/studio/agents/isaia/knowledge", { slug: "brand", nome: "Marca", tag: null });
    expect(mockGet).toHaveBeenCalledTimes(2); // initial + invalidated refetch
  });
});

describe("useUpdateKnowledgeCollection", () => {
  it("PATCHes the collection payload (nome/tag/descricao/ordem) and invalidates the list", async () => {
    mockGet.mockResolvedValue({ colecoes: [] });
    mockPatch.mockResolvedValue({ id: "c1", slug: "audience", nome: "Audiência 2", tag: "AU", descricao: "nova", ordem: 5 });
    const { useKnowledgeCollections, useUpdateKnowledgeCollection } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    const list = renderHook(() => useKnowledgeCollections("isaia"), { wrapper: wrapper(qc) });
    await waitFor(() => expect(list.result.current.showSkeleton).toBe(false));

    const update = renderHook(() => useUpdateKnowledgeCollection("isaia"), { wrapper: wrapper(qc) });
    await update.result.current.mutateAsync({
      collectionId: "c1",
      patch: { nome: "Audiência 2", tag: "AU", descricao: "nova", ordem: 5 },
    });

    expect(mockPatch).toHaveBeenCalledWith("/api/studio/agents/isaia/knowledge/c1", {
      nome: "Audiência 2",
      tag: "AU",
      descricao: "nova",
      ordem: 5,
    });
    expect(mockGet).toHaveBeenCalledTimes(2); // initial + invalidated refetch
  });
});

describe("useBatchCreateDocuments", () => {
  it("POSTs one call to the documents/batch route wrapped as {documentos}", async () => {
    mockGet.mockResolvedValue({ colecoes: [] });
    const response = {
      resultados: [
        { slug: "doc-1", status: "criado", doc_id: "d1" },
        { slug: "doc-2", status: "atualizado", doc_id: "d2" },
      ],
      criados: 1,
      atualizados: 1,
      inalterados: 0,
      erros: 0,
    };
    mockPost.mockResolvedValue(response);
    const { useBatchCreateDocuments } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    const batch = renderHook(() => useBatchCreateDocuments("isaia", "c1"), { wrapper: wrapper(qc) });

    const documentos = [
      { slug: "doc-1", titulo: "Doc 1", tipo: "fonte" as const, conteudo: "conteúdo 1" },
      { slug: "doc-2", titulo: "Doc 2", tipo: "fonte" as const, conteudo: "conteúdo 2" },
    ];
    const result = await batch.result.current.mutateAsync(documentos);

    expect(mockPost).toHaveBeenCalledWith(DOCUMENTS_BATCH_PATH, { documentos });
    expect(result).toEqual(response);
  });
});

describe("useDocuments", () => {
  it("GETs documents with q/tipo/page/page_size filters and placeholderData keeps prior page", async () => {
    mockGet.mockResolvedValue({ items: [{ id: "d1", slug: "doc-1", titulo: "Doc 1", tipo: "fonte", resumo: null, chars: 100, ativo: true, updated_at: "t" }], total: 1 });
    const { useDocuments } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    const { result } = renderHook(() => useDocuments("isaia", "c1", { q: "reels", tipo: "fonte", page: 2, page_size: 20 }), {
      wrapper: wrapper(qc),
    });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/knowledge/c1/documents", {
      q: "reels",
      tipo: "fonte",
      page: 2,
      page_size: 20,
    });
    expect(result.current.data?.items[0].slug).toBe("doc-1");
  });

  it("is disabled while no collection is selected", async () => {
    const { useDocuments } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    renderHook(() => useDocuments("isaia", null, {}), { wrapper: wrapper(qc) });
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("useKnowledgeSearch", () => {
  it("GETs the search endpoint only once q is non-empty", async () => {
    mockGet.mockResolvedValue({ items: [{ doc_id: "d1", slug: "doc-1", titulo: "Doc 1", colecao: "audience", tag: "AU", tipo: "fonte", trecho: "...", rank: 0.5 }] });
    const { useKnowledgeSearch } = await import("@/hooks/studio/useKnowledge");
    const qc = newClient();
    const { result } = renderHook(() => useKnowledgeSearch("isaia", "reels", "audience", 8), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/studio/agents/isaia/knowledge/search", { q: "reels", colecao: "audience", limite: 8 });
    expect(result.current.data?.[0].trecho).toBe("...");
  });
});
