/**
 * `CertidoesMatrizSection` — the "Certidões" card tab's matrix render:
 * loading signals, color mapping per cell status, per-column totals, and
 * the FGTS row's N/A on every PF column.
 */
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type {
  CertidaoMatrizCelula,
  CertidoesMatrizResponse,
} from "@/types/certidoesMatriz";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: {
    auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) },
  },
}));

// `CertidoesPartePanel` (opened in the click-through dialog) has its own,
// much larger `@/hooks/useCertidoes` surface — covered by its own test
// file. Stubbed here so this file's mocking stays scoped to the matriz's
// own GET.
vi.mock("@/components/CertidoesPartePanel", () => ({
  CertidoesPartePanel: ({ nomeParte }: { nomeParte?: string }) => (
    <div data-testid="certidoes-parte-panel-stub">{nomeParte}</div>
  ),
}));

import { CertidoesMatrizSection } from "./CertidoesMatrizSection";

function celula(over: Partial<CertidaoMatrizCelula> = {}): CertidaoMatrizCelula {
  return {
    status: "pendente",
    texto: "Pendente",
    resultado_id: null,
    consulta_id: null,
    numero: null,
    emitida_em: null,
    validade_ate: null,
    analise_ia: null,
    erro_mensagem: null,
    ...over,
  };
}

function matrizResponse(over: Partial<CertidoesMatrizResponse> = {}): CertidoesMatrizResponse {
  const linhas = [
    { tipo: "cnd_federal", linha: "5.1", rotulo: "Receita Federal" },
    { tipo: "trf3_sp", linha: "5.2", rotulo: "Justiça Federal – 1ª instância" },
    { tipo: "fgts_regularidade", linha: "5.13", rotulo: "Regularidade do FGTS (empresas)" },
  ];
  const colunas = [
    { kind: "pessoa" as const, id: "vend-1", rotulo: "VEND 1", nome: "Ronaldo" },
    { kind: "empresa" as const, id: "emp-1", rotulo: "EMP 1", nome: "Rokas", cnpj: "11222333000181" },
  ];
  return {
    atendimento_id: "at-1",
    data_levantamento: "2026-09-23",
    linhas,
    colunas,
    celulas: {
      cnd_federal: {
        "vend-1": celula({ status: "nao_constam", texto: "Não constam" }),
        "emp-1": celula({ status: "constam", texto: "Constam", numero: "123", erro_mensagem: null }),
      },
      trf3_sp: {
        "vend-1": celula(),
        "emp-1": celula(),
      },
      fgts_regularidade: {
        "vend-1": celula({ status: "na", texto: "N/A" }),
        "emp-1": celula({ status: "pendente", texto: "Pendente" }),
      },
    },
    totais: {
      "vend-1": { nao_constam: 1, constam: 0, pendente: 1 },
      "emp-1": { nao_constam: 0, constam: 1, pendente: 2 },
    },
    ...over,
  };
}

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("CertidoesMatrizSection", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => {
    cleanup();
    qc.clear();
  });

  it("shows a skeleton only while there is genuinely nothing yet", () => {
    mockGet.mockImplementation(() => new Promise(() => {}));
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    expect(screen.getByTestId("certidoes-matriz-skeleton")).toBeTruthy();
  });

  it("shows the empty state when there are no columns", async () => {
    mockGet.mockResolvedValue(matrizResponse({ colunas: [], celulas: {}, totais: {} }));
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(screen.getByTestId("certidoes-matriz-empty")).toBeTruthy());
  });

  it("renders every row and column with the right color/text per cell", async () => {
    mockGet.mockResolvedValue(matrizResponse());
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

    await waitFor(() => expect(screen.getByTestId("certidoes-matriz")).toBeTruthy());

    const naoConstam = screen.getByTestId("certidoes-matriz-celula-cnd_federal-vend-1");
    expect(naoConstam.textContent).toBe("Não constam");
    expect(naoConstam.className).toContain("bg-emerald-100");

    const constam = screen.getByTestId("certidoes-matriz-celula-cnd_federal-emp-1");
    expect(constam.textContent).toBe("Constam");
    expect(constam.className).toContain("bg-red-100");

    const pendente = screen.getByTestId("certidoes-matriz-celula-trf3_sp-vend-1");
    expect(pendente.textContent).toBe("Pendente");
    expect(pendente.className).toContain("bg-amber-100");
  });

  it("🔴 FGTS is N/A (grey, non-clickable) on the PF column but a normal cell on the empresa column", async () => {
    mockGet.mockResolvedValue(matrizResponse());
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(screen.getByTestId("certidoes-matriz")).toBeTruthy());

    const naCell = screen.getByTestId(
      "certidoes-matriz-celula-fgts_regularidade-vend-1",
    ) as HTMLButtonElement;
    expect(naCell.textContent).toBe("N/A");
    expect(naCell.className).toContain("bg-muted");
    expect(naCell.disabled).toBe(true);

    const empresaCell = screen.getByTestId(
      "certidoes-matriz-celula-fgts_regularidade-emp-1",
    ) as HTMLButtonElement;
    expect(empresaCell.disabled).toBe(false);
  });

  it("shows per-column totals", async () => {
    mockGet.mockResolvedValue(matrizResponse());
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(screen.getByTestId("certidoes-matriz")).toBeTruthy());

    // vend-1: 1 não constam, 0 constam, 1 pendente; emp-1: 0/1/2.
    const cells = screen.getAllByText("1");
    expect(cells.length).toBeGreaterThan(0);
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });

  it("clicking a clickable cell opens the party's certidões panel in a dialog", async () => {
    mockGet.mockResolvedValue(matrizResponse());
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(screen.getByTestId("certidoes-matriz")).toBeTruthy());

    fireEvent.click(screen.getByTestId("certidoes-matriz-celula-cnd_federal-vend-1"));

    await waitFor(() =>
      expect(screen.getByTestId("certidoes-parte-panel-stub").textContent).toBe("Ronaldo"),
    );
  });

  it("clicking the N/A cell does nothing (disabled, never opens the dialog)", async () => {
    mockGet.mockResolvedValue(matrizResponse());
    render(<CertidoesMatrizSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(screen.getByTestId("certidoes-matriz")).toBeTruthy());

    fireEvent.click(screen.getByTestId("certidoes-matriz-celula-fgts_regularidade-vend-1"));
    expect(screen.queryByTestId("certidoes-parte-panel-stub")).toBeNull();
  });
});
