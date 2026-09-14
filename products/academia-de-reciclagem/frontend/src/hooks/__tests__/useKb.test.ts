/**
 * useKb hook tests — contract §B.1.
 *
 * Stubs `@/lib/api` (the HTTP boundary) so no real HTTP is made. Verifies:
 * request path/method/body, `{items, total}` envelope parsing, and the
 * rename (`novo_slug`) + archive flows.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: mockPut, patch: vi.fn(), delete: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const SUMMARY = {
  slug: "dominio-regulatorio-pnrs",
  categoria: "dominio",
  subcategoria: "regulatorio",
  titulo: "PNRS",
  resumo: "Resumo",
  tags: ["pnrs"],
  updated_at: "2026-09-01T00:00:00Z",
};

const ENTRY = {
  ...SUMMARY,
  corpo_md: "# PNRS",
  frontmatter: {},
  arquivado: false,
  current_revision: { rev_no: 1, author_kind: "human", created_at: "2026-09-01T00:00:00Z" },
};

beforeEach(() => vi.clearAllMocks());

describe("useKbList", () => {
  it("queries /api/kb with search + filter + pagination params, parses {items,total}", async () => {
    mockGet.mockResolvedValue({ items: [SUMMARY], total: 1 });
    const { useKbList } = await import("@/hooks/useKb");
    const { result } = renderHook(
      () => useKbList({ consulta: "pnrs", categoria: "dominio", limite: 20, offset: 0 }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/kb", {
      consulta: "pnrs",
      categoria: "dominio",
      limite: 20,
      offset: 0,
    });
    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.items[0].slug).toBe("dominio-regulatorio-pnrs");
  });
});

describe("useKbEntry", () => {
  it("queries GET /api/kb/{slug}", async () => {
    mockGet.mockResolvedValue(ENTRY);
    const { useKbEntry } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useKbEntry("dominio-regulatorio-pnrs"), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/kb/dominio-regulatorio-pnrs");
    expect(result.current.data?.corpo_md).toBe("# PNRS");
  });

  it("does not query when slug is undefined", async () => {
    const { useKbEntry } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useKbEntry(undefined), { wrapper: wrapper() });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });
});

describe("useKbRevisions", () => {
  it("queries GET /api/kb/{slug}/revisions", async () => {
    mockGet.mockResolvedValue({
      items: [
        {
          rev_no: 2,
          op: "update",
          author_kind: "human",
          user_id: "u1",
          agent_id: null,
          approval_id: null,
          channel: null,
          conversation_id: null,
          motivo: "corrige regra",
          git_sha: null,
          git_committed_at: null,
          created_at: "2026-09-02T00:00:00Z",
          snapshot: {},
        },
      ],
      total: 1,
    });
    const { useKbRevisions } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useKbRevisions("dominio-regulatorio-pnrs"), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/kb/dominio-regulatorio-pnrs/revisions");
    expect(result.current.data?.items[0].author_kind).toBe("human");
    expect(result.current.data?.items[0].motivo).toBe("corrige regra");
  });
});

describe("useCreateKb", () => {
  it("posts to /api/kb with the create payload including motivo", async () => {
    mockPost.mockResolvedValue(ENTRY);
    const { useCreateKb } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useCreateKb(), { wrapper: wrapper() });

    result.current.mutate({
      categoria: "dominio",
      titulo: "PNRS",
      corpo_md: "# PNRS",
      motivo: "criação inicial",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/kb", {
      categoria: "dominio",
      titulo: "PNRS",
      corpo_md: "# PNRS",
      motivo: "criação inicial",
    });
  });
});

describe("useUpdateKb", () => {
  it("puts to /api/kb/{slug} with novo_slug for a rename", async () => {
    mockPut.mockResolvedValue({ ...ENTRY, slug: "novo-slug" });
    const { useUpdateKb } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useUpdateKb("dominio-regulatorio-pnrs"), {
      wrapper: wrapper(),
    });

    result.current.mutate({ novo_slug: "novo-slug", motivo: "renomeando" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith("/api/kb/dominio-regulatorio-pnrs", {
      novo_slug: "novo-slug",
      motivo: "renomeando",
    });
    expect(result.current.data?.slug).toBe("novo-slug");
  });
});

describe("useArchiveKb", () => {
  it("posts to /api/kb/{slug}/archive with {motivo}", async () => {
    mockPost.mockResolvedValue({ ...ENTRY, arquivado: true });
    const { useArchiveKb } = await import("@/hooks/useKb");
    const { result } = renderHook(() => useArchiveKb("dominio-regulatorio-pnrs"), {
      wrapper: wrapper(),
    });

    result.current.mutate("obsoleto");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/kb/dominio-regulatorio-pnrs/archive", {
      motivo: "obsoleto",
    });
    expect(result.current.data?.arquivado).toBe(true);
  });
});
