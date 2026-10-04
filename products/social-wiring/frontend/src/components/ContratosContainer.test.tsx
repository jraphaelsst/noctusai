/**
 * ContratosContainer — real container + real hooks (only the network and the
 * SSO context are faked) with a JUST-CREATED contract: no versões, rascunho,
 * not generated. Regression for the prod bug where ticking "Processo anterior
 * à plataforma" did nothing: the box must stay checked and the render count
 * must stay bounded (no remount / refetch loop).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@noctusai/lib", async () => {
  const actual = await vi.importActual<typeof import("@noctusai/lib")>("@noctusai/lib");
  return {
    ...actual,
    resolveSSOContext: () => ({ isProductAdmin: true, org: { role: "owner" } }),
  };
});

const contratoRecemCriado = {
  id: "c1",
  titulo: "Contrato",
  status: "rascunho",
  origem: "gerado",
  processo_legado: false,
  processo_legado_por: null,
  processo_legado_em: null,
  processo_legado_motivo: null,
  versoes: [],
  versao_atual: null,
  created_at: "2026-10-03T00:00:00+00:00",
  updated_at: "2026-10-03T00:00:00+00:00",
};

let criado = false;
const geracao = {
  contrato_id: "c1",
  pronto: false,
  modelo_derivado: "compra_venda",
  modelo_confere: true,
  modelo_automatico: false,
  processo_legado: false,
  modalidade_assinatura: "digital",
  switches: {},
  faltando: [],
  bloqueios: [],
  avisos: [],
};
const getSpy = vi.fn(async (url: string) => {
  if (/\/contratos$/.test(url)) return { contratos: criado ? [contratoRecemCriado] : [] };
  if (/\/geracao$/.test(url)) return geracao;
  throw new Error(`unmocked ${url}`);
});
const postSpy = vi.fn(async (url: string) => {
  if (/\/gerar$/.test(url)) {
    criado = true;
    return { contrato: contratoRecemCriado, geracao };
  }
  throw new Error(`unmocked POST ${url}`);
});

vi.mock("@noctusai/seed/infra", async () => {
  const actual = await vi.importActual<typeof import("@noctusai/seed/infra")>(
    "@noctusai/seed/infra",
  );
  return {
    ...actual,
    api: { get: (u: string) => getSpy(u), put: vi.fn(), post: (u: string) => postSpy(u), patch: vi.fn(), delete: vi.fn() },
    useAuthStore: () => ({ user: { user_metadata: {} } }),
    supabase: { auth: { getSession: async () => ({ data: { session: null } }) } },
  };
});

import { ContratosContainer } from "./ContratosContainer";

describe("ContratosContainer — contrato recém-criado", () => {
  it("🔴 ticking 'processo anterior' stays checked, shows the motivo form, and does not loop", async () => {
    criado = true;
    const React = await import("react");
    const { render, screen, fireEvent, waitFor } = await import("@testing-library/react");
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { MemoryRouter } = await import("react-router-dom");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    let renders = 0;
    const Probe = () => {
      renders += 1;
      return null;
    };
    render(
      React.createElement(
        QueryClientProvider,
        { client: qc },
        React.createElement(
          MemoryRouter,
          null,
          React.createElement(ContratosContainer, { clienteId: "cli1", onNovoContrato: () => {} }),
          React.createElement(Probe),
        ),
      ),
    );

    const cb = await screen.findByTestId("contrato-processo-legado-checkbox-c1");
    expect(cb.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(cb);
    await waitFor(() =>
      expect(screen.getByTestId("contrato-processo-legado-checkbox-c1").getAttribute("aria-checked")).toBe("true"),
    );
    expect(screen.getByTestId("processo-legado-motivo")).toBeTruthy();
    // Let any refetch/loop play out, then assert it is still checked + bounded.
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.getByTestId("contrato-processo-legado-checkbox-c1").getAttribute("aria-checked")).toBe("true");
    expect(getSpy.mock.calls.length).toBeLessThan(30);
    expect(renders).toBeLessThan(30);
  });

  it("🔴 same, via the real 'Gerar contrato' flow (card is recemIniciado, children mounted open)", async () => {
    criado = false;
    getSpy.mockClear();
    const React = await import("react");
    const { render, screen, fireEvent, waitFor } = await import("@testing-library/react");
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
          React.createElement(ContratosContainer, { clienteId: "cli1", onNovoContrato: () => {} }),
        ),
      ),
    );
    fireEvent.click(await screen.findByTestId("contrato-gerar-btn"));
    const cb = await screen.findByTestId("contrato-processo-legado-checkbox-c1");
    fireEvent.click(cb);
    await waitFor(() =>
      expect(screen.getByTestId("contrato-processo-legado-checkbox-c1").getAttribute("aria-checked")).toBe("true"),
    );
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.getByTestId("contrato-processo-legado-checkbox-c1").getAttribute("aria-checked")).toBe("true");
    expect(screen.getByTestId("processo-legado-motivo")).toBeTruthy();
    expect(getSpy.mock.calls.length).toBeLessThan(40);
  });
});
