/**
 * usePersona.ts hook tests — contract §E.2
 * (`GET`/`PUT /api/agents/julia/persona`).
 */
import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
// Real seed `ApiError` — `usePersona`'s `retry` predicate does
// `error instanceof ApiError`, so the test must throw the real class, not a
// plain object shaped like one. `@/lib/errors` is not mocked in this file.
import { ApiError } from "@/lib/errors";

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
    // `usePersona` sets its own per-query `retry` predicate (404 → no
    // retry, everything else → up to 3), which overrides this `retry:
    // false` default — `retryDelay: 0` stays in effect though, so a test
    // exercising the "does retry" branch (the 500 case below) doesn't wait
    // out react-query's real exponential backoff.
    defaultOptions: { queries: { retry: false, retryDelay: 0 }, mutations: { retry: false } },
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

  it("does not retry a 404 (\"nenhuma persona ainda\") and flags isNotFound, not isError", async () => {
    mockGet.mockRejectedValue(
      new ApiError(404, "Nenhuma persona ativa configurada.", {
        detail: "Nenhuma persona ativa configurada.",
        code: "not_found",
      }),
    );
    const { usePersona } = await import("@/hooks/usePersona");
    const qc = newClient();
    const { result } = renderHook(() => usePersona(), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    // A single call proves the 404 was not retried (react-query's default
    // is up to 3 retries with backoff — a retry here would leave this
    // assertion racy/slow instead of failing fast).
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(result.current.isNotFound).toBe(true);
    expect(result.current.isError).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it("still surfaces a genuine failure (500) as isError, not isNotFound", async () => {
    mockGet.mockRejectedValue(new ApiError(500, "Internal Server Error"));
    const { usePersona } = await import("@/hooks/usePersona");
    const qc = newClient();
    const { result } = renderHook(() => usePersona(), { wrapper: wrapper(qc) });

    await waitFor(() => expect(result.current.showSkeleton).toBe(false));
    expect(result.current.isError).toBe(true);
    expect(result.current.isNotFound).toBe(false);
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
