/**
 * ContratosContainer — render stability. A contracts refetch that returns
 * IDENTICAL data (TanStack structural sharing keeps the reference) flips
 * `isFetching`, which re-renders the container; the heavy render-prop
 * subtrees (gerador / matrícula / aditivos / testemunhas / proveniência) must
 * NOT re-render because of it. Children are counting stubs here.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@noctusai/lib", async () => {
  const actual = await vi.importActual<typeof import("@noctusai/lib")>("@noctusai/lib");
  return { ...actual, resolveSSOContext: () => ({ isProductAdmin: true, org: { role: "owner" } }) };
});

const counts = vi.hoisted(() => ({ gerador: 0, matricula: 0, aditivos: 0, testemunhas: 0, proveniencia: 0 }));
vi.mock("@/components/GeradorContratoContainer", () => ({
  GeradorContratoContainer: () => { counts.gerador += 1; return null; },
}));
vi.mock("@/components/MatriculaAtosContainer", () => ({
  MatriculaAtosContainer: () => { counts.matricula += 1; return null; },
}));
vi.mock("@/components/AditivosContainer", () => ({
  AditivosContainer: () => { counts.aditivos += 1; return null; },
}));
vi.mock("@/components/TestemunhasSelectContainer", () => ({
  TestemunhasSelectContainer: () => { counts.testemunhas += 1; return null; },
}));
vi.mock("@/components/ProvenienciaContainer", () => ({
  ProvenienciaContainer: () => { counts.proveniencia += 1; return null; },
}));

const contrato = {
  id: "c1", titulo: "Contrato", status: "rascunho", origem: "gerado",
  processo_legado: false, processo_legado_por: null, processo_legado_em: null,
  processo_legado_motivo: null, versoes: [], versao_atual: null,
  created_at: "2026-10-03T00:00:00+00:00", updated_at: "2026-10-03T00:00:00+00:00",
};
const getSpy = vi.fn(async (url: string) => {
  if (/\/contratos$/.test(url)) return { contratos: [contrato] };
  throw new Error(`unmocked ${url}`);
});
vi.mock("@noctusai/seed/infra", async () => {
  const actual = await vi.importActual<typeof import("@noctusai/seed/infra")>("@noctusai/seed/infra");
  return {
    ...actual,
    api: { get: (u: string) => getSpy(u), put: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    useAuthStore: () => ({ user: { user_metadata: {} } }),
    supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
  };
});

import { ContratosContainer } from "./ContratosContainer";

describe("ContratosContainer — render stability", () => {
  it("🔴 an identical-data contracts refetch does not re-render the heavy subtrees", async () => {
    const React = await import("react");
    const { render, screen, fireEvent, waitFor, act } = await import("@testing-library/react");
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { MemoryRouter } = await import("react-router-dom");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      React.createElement(
        QueryClientProvider,
        { client: qc },
        React.createElement(
          MemoryRouter,
          null,
          // a fresh onIrPara closure per render, like the card dialog passes
          React.createElement(ContratosContainer, { clienteId: "cli1", onNovoContrato: () => {}, onIrPara: () => {} }),
        ),
      ),
    );
    await screen.findByTestId("contrato-gerador-toggle-c1");
    // open every collapsible so each stub is rendered with aberto=true
    for (const k of ["gerador", "matricula", "proveniencia", "testemunhas", "aditivos"]) {
      const t = screen.queryByTestId(`contrato-${k}-toggle-c1`);
      if (t) fireEvent.click(t);
    }
    await waitFor(() => expect(counts.gerador).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 100));
    const antes = { ...counts };
    const getsAntes = getSpy.mock.calls.length;

    await act(async () => {
      await qc.invalidateQueries({ queryKey: ["sw", "clientes", "cli1", "contratos"] });
    });
    await new Promise((r) => setTimeout(r, 100));
    expect(getSpy.mock.calls.length).toBeGreaterThan(getsAntes); // the refetch really happened
    expect(counts).toEqual(antes);
  });

  it("contratoId opens that draft's matrícula + gerador sections on mount", async () => {
    const React = await import("react");
    const { render, screen } = await import("@testing-library/react");
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { MemoryRouter } = await import("react-router-dom");
    const antes = counts.gerador;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      React.createElement(
        QueryClientProvider,
        { client: qc },
        React.createElement(
          MemoryRouter,
          null,
          React.createElement(ContratosContainer, { clienteId: "cli2", onNovoContrato: () => {}, contratoId: "c1" }),
        ),
      ),
    );
    await screen.findByTestId("contrato-gerador-toggle-c1");
    expect(counts.gerador).toBeGreaterThan(antes); // rendered open without any click
  });
});
