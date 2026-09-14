/**
 * usePerguntas hook tests — contract §B.3.
 *
 * Verifies the `estado` default (aberta), the create POST, and the answer
 * flow carrying `aviso` when `destino_kb` was set.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const Q1 = {
  codigo: "Q-01",
  pergunta: "Qual o limite de tamanho de arquivo no bundle de import?",
  por_que_importa: "Define o design do parser",
  bloqueia: "T-005",
  destino_kb: "dominio-regulatorio-pnrs",
  estado: "aberta" as const,
  resposta: null,
  respondida_em: null,
};

beforeEach(() => vi.clearAllMocks());

describe("usePerguntasList", () => {
  it("defaults to estado=aberta", async () => {
    mockGet.mockResolvedValue({ items: [Q1], total: 1 });
    const { usePerguntasList } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => usePerguntasList(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/questions", { estado: "aberta" });
    expect(result.current.data?.items[0].codigo).toBe("Q-01");
  });

  it("queries with the given estado", async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    const { usePerguntasList } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => usePerguntasList("todas"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/questions", { estado: "todas" });
  });
});

describe("useCreatePergunta", () => {
  it("posts to /api/questions", async () => {
    mockPost.mockResolvedValue(Q1);
    const { useCreatePergunta } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => useCreatePergunta(), { wrapper: wrapper() });

    result.current.mutate({
      pergunta: Q1.pergunta,
      por_que_importa: Q1.por_que_importa,
      bloqueia: Q1.bloqueia,
      destino_kb: Q1.destino_kb,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/questions", {
      pergunta: Q1.pergunta,
      por_que_importa: Q1.por_que_importa,
      bloqueia: Q1.bloqueia,
      destino_kb: Q1.destino_kb,
    });
  });
});

describe("useAnswerPergunta", () => {
  it("posts to /api/questions/{codigo}/answer and surfaces the aviso when destino_kb was set", async () => {
    mockPost.mockResolvedValue({
      ...Q1,
      estado: "respondida",
      resposta: "Registrado",
      aviso: "Registre a resposta em /kb/dominio-regulatorio-pnrs",
    });
    const { useAnswerPergunta } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => useAnswerPergunta("Q-01"), { wrapper: wrapper() });

    result.current.mutate("Registrado");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/questions/Q-01/answer", { resposta: "Registrado" });
    expect(result.current.data?.aviso).toBe("Registre a resposta em /kb/dominio-regulatorio-pnrs");
  });

  it("carries no aviso when destino_kb was not set", async () => {
    mockPost.mockResolvedValue({ ...Q1, destino_kb: null, estado: "respondida", resposta: "ok" });
    const { useAnswerPergunta } = await import("@/hooks/usePerguntas");
    const { result } = renderHook(() => useAnswerPergunta("Q-01"), { wrapper: wrapper() });

    result.current.mutate("ok");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.aviso).toBeUndefined();
  });
});
