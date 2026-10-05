/**
 * NegociacaoContainer / FinanciamentoContainer — `loading` is FIRST-LOAD only
 * (`isPending && !data`): a save refetches the query, and the old
 * `isPending || isFetching` disabled the form the operator was typing in.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const { negQuery, finQuery } = vi.hoisted(() => ({
  negQuery: { current: {} as Record<string, unknown> },
  finQuery: { current: {} as Record<string, unknown> },
}));

vi.mock("@/hooks/useNegociacao", () => ({
  useNegociacao: () => negQuery.current,
  useNegociacaoMutation: () => ({ isPending: false, error: null, mutate: vi.fn() }),
}));
vi.mock("@/hooks/useFinanciamento", () => ({
  useFinanciamento: () => finQuery.current,
  useFinanciamentoMutation: () => ({ isPending: false, error: null, mutate: vi.fn() }),
  useFinanciamentoDocumentoMutations: () => ({
    upload: { isPending: false, error: null, mutate: vi.fn() },
    remove: { error: null, mutate: vi.fn() },
  }),
  useFinanciamentoDocumentoExtracao: () => ({
    reextrair: { isPending: false, mutate: vi.fn() },
    confirmar: { isPending: false, mutate: vi.fn() },
    descartar: { isPending: false, mutate: vi.fn() },
    reler: { isPending: false, mutate: vi.fn() },
    relerTodos: { isPending: false, mutate: vi.fn() },
  }),
  useFinanciamentoExtracaoPollingInvalidation: () => undefined,
}));
vi.mock("@/hooks/useAgentesFinanceiros", () => ({
  useAgentesFinanceiros: () => ({ data: [], isPending: false }),
}));
vi.mock("@/components/card/NegociacaoPanel", () => ({
  default: (p: { loading: boolean }) => <div data-testid="neg-panel" data-loading={String(p.loading)} />,
}));
vi.mock("@/components/card/NegociacaoEstruturadaPanel", () => ({ default: () => null }));
vi.mock("@/components/card/ImovelCodigoPicker", () => ({ ImovelCodigoPicker: () => null }));
vi.mock("@/components/card/FinanciamentoPanel", () => ({
  default: (p: { loading: boolean }) => <div data-testid="fin-panel" data-loading={String(p.loading)} />,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

import { FinanciamentoContainer } from "./FinanciamentoContainer";
import { NegociacaoContainer } from "./NegociacaoContainer";

afterEach(cleanup);

describe("NegociacaoContainer", () => {
  it("is loading only before the first data", () => {
    negQuery.current = { data: undefined, isPending: true, isFetching: true, error: null };
    render(<NegociacaoContainer clienteId="c1" />);
    expect(screen.getByTestId("neg-panel").getAttribute("data-loading")).toBe("true");
  });

  it("🔴 a background refetch (every save) does NOT put the form back into loading", () => {
    negQuery.current = { data: { atendimento_id: "a" }, isPending: false, isFetching: true, error: null };
    render(<NegociacaoContainer clienteId="c1" />);
    expect(screen.getByTestId("neg-panel").getAttribute("data-loading")).toBe("false");
  });
});

describe("FinanciamentoContainer", () => {
  it("is loading only before the first data", () => {
    finQuery.current = { data: undefined, isPending: true, isFetching: true, error: null };
    render(<FinanciamentoContainer clienteId="c1" />);
    expect(screen.getByTestId("fin-panel").getAttribute("data-loading")).toBe("true");
  });

  it("🔴 a background refetch does NOT put the panel back into loading", () => {
    finQuery.current = { data: { existe: true }, isPending: false, isFetching: true, error: null };
    render(<FinanciamentoContainer clienteId="c1" />);
    expect(screen.getByTestId("fin-panel").getAttribute("data-loading")).toBe("false");
  });
});
