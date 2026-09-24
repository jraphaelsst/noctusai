/**
 * `EmpresasSection` — the P0c contract's "Empresas" tab
 * (`project-history/roadmaps/sw-drive-extraction-P0c-contract.md` §F).
 *
 * Covers the collapsed-row surface (nome/CNPJ, situação, the E1
 * `motivo`/`exige_certidoes` badge) and the section's own loading signals —
 * `CollapsibleSection`'s rows default CLOSED, so `useEmpresaDocumentos` /
 * `CertidoesPartePanel` never mount for these assertions, which keeps this
 * file's mocking surface to the three card routes `EmpresasSection` itself
 * calls unconditionally (`useCardResumo`, `useCompradores` × 2 lados,
 * `useEmpresasDoCard`).
 */
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { EmpresaCardItem, EmpresaMotivo, EmpresasDoCardResponse } from "@/types/empresas";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  supabase: {
    auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) },
  },
}));

import { EmpresasSection } from "./EmpresasSection";

function empresaItem(over: Partial<EmpresaCardItem> = {}): EmpresaCardItem {
  return {
    empresa: {
      id: "emp-1",
      cnpj: "12345678000199",
      razao_social: "Padaria do Zé Ltda",
      nome_fantasia: null,
      natureza_juridica: null,
      data_abertura: null,
      situacao_cadastral: "ativa",
      data_situacao_cadastral: null,
      motivo_situacao: null,
      uf: "SP",
      dados_origem: "cartao_cnpj",
      dados_confirmado_em: "2026-09-20T00:00:00Z",
    },
    owners: [
      {
        cliente_id: "cli-2",
        nome: "Maria Vendedora",
        lado: "vendedor",
        papel: "proprietario",
        participacao_pct: 100,
        origem: "cartao_cnpj",
        certificando: true,
      },
    ],
    cartao: { documento_id: null, extracao_status: null, extracao_descartada_em: null, aviso: null },
    exige_certidoes: true,
    motivo: "ativa",
    certidoes: {
      consulta_ids: [],
      total: 0,
      por_resultado: {
        negativa: 0,
        positiva: 0,
        positiva_com_efeito_de_negativa: 0,
        negativa_com_homonimos: 0,
        nao_emitida: 0,
        pendente: 0,
      },
    },
    ...over,
  };
}

function empresasResponse(items: EmpresaCardItem[]): EmpresasDoCardResponse {
  return { atendimento_id: "at-1", referencia: "2026-09-24", items };
}

/** Dispatches the mocked `api.get` by path — `EmpresasSection` fires four
 *  GETs unconditionally (card resumo, compradores × 2 lados, empresas). */
function mockRoutes(empresas: EmpresasDoCardResponse) {
  mockGet.mockImplementation((path: string) => {
    if (path.includes("/empresas")) return Promise.resolve(empresas);
    if (path.includes("/compradores")) return Promise.resolve({ items: [] });
    if (path.includes("/card")) return Promise.resolve({ cliente: { nome: "Titular" } });
    return Promise.resolve({});
  });
}

function makeWrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("EmpresasSection", () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockGet.mockReset();
  });

  afterEach(() => {
    cleanup();
    qc.clear();
  });

  it("shows a skeleton only while there is genuinely nothing yet", async () => {
    mockGet.mockImplementation(() => new Promise(() => {})); // never resolves
    render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    expect(screen.getByTestId("empresas-section-skeleton")).toBeTruthy();
  });

  it("🔴 never unmounts existing rows during a background refetch — no skeleton, no empty flash", async () => {
    mockRoutes(empresasResponse([empresaItem()]));
    render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

    await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());

    // A background refetch that is slow to resolve must not blank the row —
    // `showSkeleton = isPending && !data` stays false once `data` exists.
    mockGet.mockImplementation((path: string) => {
      if (path.includes("/empresas")) return new Promise(() => {});
      return Promise.resolve({ items: [] });
    });
    void qc.refetchQueries({ queryKey: ["sw", "clientes", "cli-1", "empresas"] });

    await waitFor(() => expect(screen.getByTestId("empresas-section-refreshing")).toBeTruthy());
    expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy();
    expect(screen.queryByTestId("empresas-section-skeleton")).toBeNull();
  });

  it("shows the empty state once loaded with zero empresas", async () => {
    mockRoutes(empresasResponse([]));
    render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
    await waitFor(() => expect(screen.getByTestId("empresas-section-empty")).toBeTruthy());
  });

  const motivoCases: Array<[EmpresaMotivo, string, boolean]> = [
    ["ativa", "Ativa", true],
    ["baixada_menos_5_anos", "Baixada há menos de 5 anos", true],
    [
      "baixada_5_anos_ou_mais",
      "Baixada há 5 anos ou mais — certidões dispensadas",
      false,
    ],
    ["sem_cartao_cnpj", "Falta Cartão CNPJ", false],
    ["outra_situacao", "Outra situação", false],
    ["sem_socio_certificando", "Sem sócio certificando", false],
  ];

  it.each(motivoCases)(
    "renders the pt-BR motivo badge for %s",
    async (motivo, label, exigeCertidoes) => {
      mockRoutes(empresasResponse([empresaItem({ motivo, exige_certidoes: exigeCertidoes })]));
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() =>
        expect(screen.getByTestId("empresa-row-emp-1-motivo").textContent).toBe(label),
      );
    },
  );

  it("renders the owner and the situação cadastral badge", async () => {
    mockRoutes(empresasResponse([empresaItem()]));
    render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

    await waitFor(() =>
      expect(screen.getByTestId("empresa-row-emp-1-situacao").textContent).toContain("Ativa"),
    );
    expect(screen.getByTestId("empresa-row-emp-1-nome").textContent).toBe("Padaria do Zé Ltda");
  });
});
