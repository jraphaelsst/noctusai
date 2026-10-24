/**
 * `salvarEspecificacoes` (CONTRACT.md §10.2) — real TanStack Query against a
 * fake `api.put`: the selection is written into the cache (the contract row
 * AND every cached readiness report of that contract), never invalidate-only;
 * a 400 rolls the draw back and surfaces the server's own sentence.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

const { mockPut } = vi.hoisted(() => ({ mockPut: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: mockPut, delete: vi.fn() },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));

import { mensagemErroServidor } from "@/lib/erroServidor";
import { useContratoMutations, type ContratoGeracaoStatus, type ContratoOut } from "./useContratos";

afterEach(() => {
  cleanup();
  mockPut.mockReset();
});

const LISTA = ["sw", "clientes", "cli-1", "contratos"];
const GERACAO = [...LISTA, "k1", "geracao", null];
const GERACAO_DATA = [...LISTA, "k1", "geracao", "2026-11-01"];

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(LISTA, [
    { id: "k1", modelo: "compra_venda", especificacoes: null, especificacoes_versao: null },
    { id: "k2", modelo: "compra_venda", especificacoes: null, especificacoes_versao: null },
  ] as unknown as ContratoOut[]);
  qc.setQueryData(GERACAO, { contrato_id: "k1", especificacoes: null } as unknown as ContratoGeracaoStatus);
  qc.setQueryData(GERACAO_DATA, { contrato_id: "k1", especificacoes: null } as unknown as ContratoGeracaoStatus);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useContratoMutations("cli-1"), { wrapper });
  return { qc, result };
}

describe("salvarEspecificacoes", () => {
  it("PUTs {especificacoes} and commits the server's answer into the list and every geracao report", async () => {
    mockPut.mockResolvedValue({
      especificacoes: ["compra_venda", "a_vista"],
      especificacoes_versao: 1,
      modelo: "compra_venda_a_vista",
    });
    const { qc, result } = setup();
    await act(async () => {
      await result.current.salvarEspecificacoes.mutateAsync({
        contratoId: "k1",
        especificacoes: ["a_vista", "compra_venda"],
      });
    });
    expect(mockPut).toHaveBeenCalledWith("/api/clientes/cli-1/contratos/k1/especificacoes", {
      especificacoes: ["a_vista", "compra_venda"],
    });
    const lista = qc.getQueryData<ContratoOut[]>(LISTA)!;
    expect(lista[0]).toMatchObject({
      id: "k1",
      especificacoes: ["compra_venda", "a_vista"],
      especificacoes_versao: 1,
      modelo: "compra_venda_a_vista",
    });
    expect(lista[1].especificacoes).toBeNull();
    for (const key of [GERACAO, GERACAO_DATA]) {
      expect(qc.getQueryData<ContratoGeracaoStatus>(key)).toMatchObject({
        especificacoes: ["compra_venda", "a_vista"],
        especificacoes_versao: 1,
      });
    }
  });

  it("draws the selection before the server answers (optimistic)", async () => {
    let resolver: (v: unknown) => void = () => {};
    mockPut.mockReturnValue(new Promise((r) => (resolver = r)));
    const { qc, result } = setup();
    act(() => {
      result.current.salvarEspecificacoes.mutate({ contratoId: "k1", especificacoes: ["compra_venda", "permuta"] });
    });
    await waitFor(() =>
      expect(qc.getQueryData<ContratoOut[]>(LISTA)![0].especificacoes).toEqual(["compra_venda", "permuta"]),
    );
    await act(async () => {
      resolver({ especificacoes: ["compra_venda", "permuta"], especificacoes_versao: 1, modelo: "compra_venda_permuta" });
    });
  });

  it("🔴 a 400 rolls the draw back and carries the server's sentence", async () => {
    const erro = Object.assign(new Error("[400] especificações exclusivas"), {
      status: 400,
      body: { error: { code: "BAD_REQUEST", message: "especificações exclusivas: 'a_vista' e 'fgts'" } },
    });
    mockPut.mockRejectedValue(erro);
    const { qc, result } = setup();
    await act(async () => {
      await result.current.salvarEspecificacoes
        .mutateAsync({ contratoId: "k1", especificacoes: ["compra_venda", "a_vista", "fgts"] })
        .catch(() => undefined);
    });
    expect(qc.getQueryData<ContratoOut[]>(LISTA)![0].especificacoes).toBeNull();
    expect(qc.getQueryData<ContratoGeracaoStatus>(GERACAO)!.especificacoes).toBeNull();
    await waitFor(() => expect(result.current.salvarEspecificacoes.isError).toBe(true));
    expect(mensagemErroServidor(result.current.salvarEspecificacoes.error, "x")).toBe(
      "especificações exclusivas: 'a_vista' e 'fgts'",
    );
  });
});
