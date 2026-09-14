/**
 * usePersona.ts hook tests — contract §E.2
 * (`GET`/`PUT /api/agents/julia/persona`).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPut = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: mockPut, patch: vi.fn(), delete: vi.fn() },
}));

function wrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

const PERSONA = {
  versao: 3,
  nome: "Julia",
  papel: "Assistente de conhecimento",
  tom: "acolhedor",
  system_prompt_append: null,
  model: "claude-sonnet-5",
  effort: "medium",
  idioma: "pt-BR",
  org_display_name: null,
  project_display_name: null,
  ativa: true,
  created_by: "u1",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

beforeEach(() => vi.clearAllMocks());

describe("usePersona", () => {
  it("GETs /api/agents/julia/persona", async () => {
    mockGet.mockResolvedValue(PERSONA);
    const { usePersona } = await import("@/hooks/usePersona");
    const qc = newClient();
    const { result } = renderHook(() => usePersona(), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(mockGet).toHaveBeenCalledWith("/api/agents/julia/persona");
    expect(result.current.data?.versao).toBe(3);
  });
});

describe("useUpdatePersona", () => {
  it("PUTs /api/agents/julia/persona with the full payload", async () => {
    mockPut.mockResolvedValue({ ...PERSONA, versao: 4, papel: "Novo papel" });
    const { useUpdatePersona } = await import("@/hooks/usePersona");
    const qc = newClient();
    const { result } = renderHook(() => useUpdatePersona(), { wrapper: wrapper(qc) });

    const payload = {
      nome: "Julia",
      papel: "Novo papel",
      model: "claude-opus-5",
      effort: "high",
      tom: "direto",
      system_prompt_append: "Seja objetiva.",
      idioma: "pt-BR",
      org_display_name: "Acme",
      project_display_name: "Projeto X",
    };
    result.current.mutate(payload);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPut).toHaveBeenCalledWith("/api/agents/julia/persona", payload);
    expect(result.current.data?.versao).toBe(4);
  });
});
