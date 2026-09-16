/**
 * useAplicacoes hook tests — community-m1-contract.md
 * §Endpoints#Aplicações-(perguntas-+-submissões).
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
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const PERGUNTA = {
  id: "q-1",
  pergunta: "Por que quer entrar?",
  tipo: "texto_longo" as const,
  opcoes: [],
  obrigatoria: true,
  ordem: 0,
  ativa: true,
};

const APLICACAO = {
  id: "a-1",
  nome: "Beatriz",
  email: "bea@x.com",
  telefone: null,
  respostas: { "q-1": "Porque sim" },
  status: "pendente" as const,
  motivo: null,
  revisado_em: null,
  membro_id: null,
  created_at: "2026-09-16T20:00:00+00:00",
};

beforeEach(() => vi.clearAllMocks());

describe("useFormulario (PUBLIC)", () => {
  it("fetches /api/aplicacoes/formulario", async () => {
    mockGet.mockResolvedValue({ items: [PERGUNTA], total: 1 });
    const { useFormulario } = await import("@/hooks/useAplicacoes");
    const { result } = renderHook(() => useFormulario(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/aplicacoes/formulario");
    expect(result.current.data?.items[0].pergunta).toBe("Por que quer entrar?");
  });
});

describe("useSubmitAplicacao (PUBLIC)", () => {
  it("posts to /api/aplicacoes with the contract's respostas shape", async () => {
    mockPost.mockResolvedValue({ id: "a-1", status: "pendente" });
    const { useSubmitAplicacao } = await import("@/hooks/useAplicacoes");
    const { result } = renderHook(() => useSubmitAplicacao(), { wrapper: wrapper() });

    result.current.mutate({ nome: "Beatriz", email: "bea@x.com", respostas: { "q-1": "Porque sim" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/aplicacoes", {
      nome: "Beatriz",
      email: "bea@x.com",
      respostas: { "q-1": "Porque sim" },
    });
    expect(result.current.data?.status).toBe("pendente");
  });
});

describe("useAplicacoes list", () => {
  it("fetches /api/aplicacoes carrying items+total+resumo", async () => {
    mockGet.mockResolvedValue({
      items: [APLICACAO],
      total: 1,
      resumo: { pendente: 1, aprovada: 0, rejeitada: 0 },
    });
    const { useAplicacoes } = await import("@/hooks/useAplicacoes");
    const { result } = renderHook(() => useAplicacoes({ status: "pendente" }), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("/api/aplicacoes", { status: "pendente" });
    expect(result.current.data?.resumo.pendente).toBe(1);
  });
});

describe("useAprovarAplicacao", () => {
  it("posts to /api/aplicacoes/{id}/aprovar and returns {aplicacao, membro}", async () => {
    const membro = { id: "m-1", nome: "Beatriz", status: "pendente" };
    mockPost.mockResolvedValue({ aplicacao: { ...APLICACAO, status: "aprovada" }, membro });
    const { useAprovarAplicacao } = await import("@/hooks/useAplicacoes");
    const { result } = renderHook(() => useAprovarAplicacao(), { wrapper: wrapper() });

    result.current.mutate({ id: "a-1", plano_id: null });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/aplicacoes/a-1/aprovar", { plano_id: null });
    expect(result.current.data?.membro.id).toBe("m-1");
  });
});

describe("useRejeitarAplicacao", () => {
  it("posts to /api/aplicacoes/{id}/rejeitar requiring motivo", async () => {
    mockPost.mockResolvedValue({ ...APLICACAO, status: "rejeitada", motivo: "Perfil incompatível" });
    const { useRejeitarAplicacao } = await import("@/hooks/useAplicacoes");
    const { result } = renderHook(() => useRejeitarAplicacao(), { wrapper: wrapper() });

    result.current.mutate({ id: "a-1", motivo: "Perfil incompatível" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith("/api/aplicacoes/a-1/rejeitar", { motivo: "Perfil incompatível" });
  });
});
