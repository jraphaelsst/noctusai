/**
 * KnowledgeTab.tsx tests — Agent Studio CONTRACT.md §G "Conhecimento".
 * Stubs every `useKnowledge.ts` hook + `useIsAdmin`, asserting the tab's
 * own rendering (loading/empty/error/success, admin-only write controls),
 * not the hooks themselves (covered by `useKnowledge.test.ts`).
 */
import React from "react";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseKnowledgeCollections = vi.fn();
const mockUseDocuments = vi.fn();
const mockUseDocument = vi.fn();
const mockUseDocumentRevisions = vi.fn();
const mockUseKnowledgeSearch = vi.fn();
const mockUseCreateKnowledgeCollection = vi.fn();
const mockUseUpdateKnowledgeCollection = vi.fn();
const mockUseCreateDocument = vi.fn();
const mockUseUpdateDocument = vi.fn();
const mockUseBatchCreateDocuments = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/studio/useKnowledge", () => ({
  useKnowledgeCollections: () => mockUseKnowledgeCollections(),
  useDocuments: () => mockUseDocuments(),
  useDocument: () => mockUseDocument(),
  useDocumentRevisions: () => mockUseDocumentRevisions(),
  useKnowledgeSearch: () => mockUseKnowledgeSearch(),
  useCreateKnowledgeCollection: () => mockUseCreateKnowledgeCollection(),
  useUpdateKnowledgeCollection: () => mockUseUpdateKnowledgeCollection(),
  useCreateDocument: () => mockUseCreateDocument(),
  useUpdateDocument: () => mockUseUpdateDocument(),
  useBatchCreateDocuments: () => mockUseBatchCreateDocuments(),
}));

vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockUseIsAdmin() }));

const COLLECTION = { id: "c1", slug: "audience", nome: "Audiência", tag: "AU", descricao: "", ordem: 1, total_documentos: 1 };
const DOC = { id: "d1", slug: "doc-1", titulo: "Doc 1", tipo: "fonte" as const, resumo: "resumo", chars: 120, ativo: true, updated_at: "t" };

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(false);
  mockUseKnowledgeCollections.mockReturnValue({ data: [COLLECTION], showSkeleton: false, isError: false, error: null });
  mockUseDocuments.mockReturnValue({ data: { items: [DOC], total: 1 }, showSkeleton: false, isError: false });
  mockUseDocument.mockReturnValue({ data: undefined, showSkeleton: false, isError: false, error: null });
  mockUseDocumentRevisions.mockReturnValue({ data: [] });
  mockUseKnowledgeSearch.mockReturnValue({ data: undefined, showSkeleton: false, isError: false });
  mockUseCreateKnowledgeCollection.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateKnowledgeCollection.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseCreateDocument.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseUpdateDocument.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  mockUseBatchCreateDocuments.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

afterEach(() => cleanup());

async function renderTab() {
  const KnowledgeTab = (await import("@/pages/studio/tabs/KnowledgeTab")).default;
  render(React.createElement(KnowledgeTab, { agentKey: "isaia" }));
}

describe("KnowledgeTab — loading/empty/error", () => {
  it("shows a skeleton while collections load", async () => {
    mockUseKnowledgeCollections.mockReturnValue({ data: undefined, showSkeleton: true, isError: false, error: null });
    await renderTab();
    expect(screen.queryByTestId("knowledge-collection-audience")).toBeNull();
  });

  it("shows an error state when collections fail to load", async () => {
    mockUseKnowledgeCollections.mockReturnValue({ data: undefined, showSkeleton: false, isError: true, error: new Error("boom") });
    await renderTab();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("shows an empty prompt when there are no collections", async () => {
    mockUseKnowledgeCollections.mockReturnValue({ data: [], showSkeleton: false, isError: false, error: null });
    await renderTab();
    expect(screen.getByText("Crie uma coleção para começar.")).toBeTruthy();
  });
});

describe("KnowledgeTab — success + role gating", () => {
  it("member: lists the collection and its documents, no write controls", async () => {
    await renderTab();
    expect(screen.getByTestId("knowledge-collection-audience")).toBeTruthy();
    expect(screen.getByTestId("knowledge-document-row-doc-1")).toBeTruthy();
    expect(screen.queryByText("Nova coleção")).toBeNull();
    expect(screen.queryByTestId("knowledge-new-document-toggle")).toBeNull();
  });

  it("admin: sees the 'Nova coleção' and 'Novo documento' controls", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderTab();
    expect(screen.getByText("Nova coleção")).toBeTruthy();
    expect(screen.getByTestId("knowledge-new-document-toggle")).toBeTruthy();
  });

  it("renders the search playground with contract-shaped results", async () => {
    mockUseKnowledgeSearch.mockReturnValue({
      data: [{ doc_id: "d1", slug: "doc-1", titulo: "Doc 1", colecao: "audience", tag: "AU", tipo: "fonte", trecho: "trecho…", rank: 0.9 }],
      showSkeleton: false,
      isError: false,
    });
    await renderTab();
    expect(screen.getByTestId("knowledge-search-playground")).toBeTruthy();
  });
});

describe("KnowledgeTab — document editor: provenance + content guard", () => {
  const DOC_DETAIL = {
    id: "d1",
    collection_id: "c1",
    slug: "doc-1",
    titulo: "Doc 1",
    tipo: "fonte" as const,
    resumo: "resumo",
    conteudo: "Conteúdo original.",
    proveniencia: { autor: "Fonte X", origem: "livro" },
    ativo: true,
    chars: 120,
    updated_at: "t",
  };

  it("admin: edits provenance fields and the save payload carries them", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    mockUseDocument.mockReturnValue({ data: DOC_DETAIL, showSkeleton: false, isError: false, error: null });
    const mutateAsync = vi.fn().mockResolvedValue(DOC_DETAIL);
    mockUseUpdateDocument.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("knowledge-document-row-doc-1"));
    const autor = (await screen.findByTestId("knowledge-provenance-autor")) as HTMLInputElement;
    expect(autor.value).toBe("Fonte X");
    const referencia = screen.getByTestId("knowledge-provenance-referencia") as HTMLInputElement;
    fireEvent.change(referencia, { target: { value: "p. 12" } });

    fireEvent.click(screen.getByTestId("knowledge-document-save"));

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        proveniencia: expect.objectContaining({ autor: "Fonte X", origem: "livro", referencia: "p. 12" }),
      }),
    );
    const [[payload]] = mutateAsync.mock.calls;
    expect(payload.proveniencia).not.toHaveProperty("pagina");
  });
});

describe("KnowledgeTab — new document form: content required non-empty", () => {
  it("blocks submit with only whitespace content, never calls the mutation", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    const mutateAsync = vi.fn();
    mockUseCreateDocument.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("knowledge-new-document-toggle"));
    const form = await screen.findByTestId("knowledge-new-document-form");
    fireEvent.change(within(form).getAllByRole("textbox")[0], { target: { value: "titulo" } });
    fireEvent.submit(form);

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByText("Informe o conteúdo do documento.")).toBeTruthy();
  });
});

describe("KnowledgeTab — new document form: proveniência settable at creation", () => {
  it("includes a filled provenance field in the create payload", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseCreateDocument.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("knowledge-new-document-toggle"));
    const form = await screen.findByTestId("knowledge-new-document-form");
    fireEvent.change(within(form).getAllByRole("textbox")[0], { target: { value: "slug-x" } }); // slug
    fireEvent.change(within(form).getAllByRole("textbox")[1], { target: { value: "Título X" } }); // titulo
    fireEvent.change(within(form).getByTestId("knowledge-new-document-provenance-autor"), { target: { value: "Curso Audience" } });
    const textareas = within(form).getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA") as HTMLTextAreaElement[];
    const conteudoField = textareas[textareas.length - 1]; // Resumo then Conteúdo — last one is Conteúdo
    fireEvent.change(conteudoField, { target: { value: "conteúdo" } });
    fireEvent.submit(form);

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ proveniencia: expect.objectContaining({ autor: "Curso Audience" }) }),
    );
  });
});

describe("KnowledgeTab — collection edit", () => {
  it("admin: opens the edit form and the update payload carries nome/tag/descricao/ordem", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseUpdateKnowledgeCollection.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("knowledge-collection-edit-audience"));
    const form = await screen.findByTestId("knowledge-edit-collection-form");
    const nome = within(form).getByDisplayValue("Audiência") as HTMLInputElement;
    fireEvent.change(nome, { target: { value: "Audiência 2" } });
    fireEvent.submit(form);

    expect(mutateAsync).toHaveBeenCalledWith({
      collectionId: "c1",
      patch: { nome: "Audiência 2", tag: "AU", descricao: "", ordem: 1 },
    });
  });

  it("member: has no edit control", async () => {
    await renderTab();
    expect(screen.queryByTestId("knowledge-collection-edit-audience")).toBeNull();
  });
});

describe("KnowledgeTab — document metadata (titulo/tipo/ativo)", () => {
  const DOC_DETAIL = {
    id: "d1",
    collection_id: "c1",
    slug: "doc-1",
    titulo: "Doc 1",
    tipo: "fonte" as const,
    resumo: "resumo",
    conteudo: "Conteúdo original.",
    proveniencia: {},
    ativo: true,
    chars: 120,
    updated_at: "t",
  };

  it("admin: edits título/tipo/ativo and the save payload carries them", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    mockUseDocument.mockReturnValue({ data: DOC_DETAIL, showSkeleton: false, isError: false, error: null });
    const mutateAsync = vi.fn().mockResolvedValue(DOC_DETAIL);
    mockUseUpdateDocument.mockReturnValue({ mutateAsync, isPending: false });
    await renderTab();

    fireEvent.click(screen.getByTestId("knowledge-document-row-doc-1"));
    const titulo = (await screen.findByTestId("knowledge-document-titulo")) as HTMLInputElement;
    expect(titulo.value).toBe("Doc 1");
    fireEvent.change(titulo, { target: { value: "Doc 1 renomeado" } });
    fireEvent.change(screen.getByTestId("knowledge-document-tipo"), { target: { value: "sintese" } });
    fireEvent.click(screen.getByTestId("knowledge-document-ativo"));

    fireEvent.click(screen.getByTestId("knowledge-document-save"));

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ titulo: "Doc 1 renomeado", tipo: "sintese", ativo: false }),
    );
  });

  it("the ativo checkbox is labeled honestly as archive-only (no delete)", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    mockUseDocument.mockReturnValue({ data: DOC_DETAIL, showSkeleton: false, isError: false, error: null });
    await renderTab();
    fireEvent.click(screen.getByTestId("knowledge-document-row-doc-1"));
    await screen.findByTestId("knowledge-document-ativo");
    expect(screen.getByText(/não há exclusão de documentos, apenas arquivamento/i)).toBeTruthy();
  });
});
