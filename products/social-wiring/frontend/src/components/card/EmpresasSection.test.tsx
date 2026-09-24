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
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type {
  EmpresaCardItem,
  EmpresaDocumento,
  EmpresaMotivo,
  EmpresasDoCardResponse,
} from "@/types/empresas";

const { mockGet, mockPatch, mockDelete, mockBaixarArquivo, mockUseAuthStore } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
  mockBaixarArquivo: vi.fn(),
  // Defaults to a non-admin — no `user_metadata` means `resolveSSOContext`
  // (kept REAL, not mocked) resolves every role field to `null`. Tests
  // that need an admin call `mockUseAuthStore.mockReturnValue(...)`.
  mockUseAuthStore: vi.fn(() => ({ user: null })),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: vi.fn(), patch: mockPatch, put: vi.fn(), delete: mockDelete },
  supabase: {
    auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) },
  },
  useAuthStore: mockUseAuthStore,
}));

// The empresa's own certidões (`CertidoesPartePanel` in `empresaId` mode)
// are out of scope here — covered by `CertidoesPartePanel.test.tsx` — and
// stubbed so expanding a row exercises ONLY `EmpresaCartaoSlot`'s own hooks,
// not that panel's much larger `@/hooks/useCertidoes` surface.
vi.mock("@/components/CertidoesPartePanel", () => ({
  CertidoesPartePanel: () => null,
}));

// `CollapsibleSection`/`TooltipIconButton`/`formatBytes` stay REAL (they
// already render fine in jsdom without mocking, as the rest of this file's
// tests show); only `baixarArquivo` — the one export with a real side
// effect (triggers a browser download) — is replaced.
vi.mock("@noctusai/lib/components", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@noctusai/lib/components")>();
  return { ...actual, baixarArquivo: mockBaixarArquivo };
});

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

function empresaDocumento(over: Partial<EmpresaDocumento> = {}): EmpresaDocumento {
  return {
    id: "doc-1",
    nome_original: "cartao_cnpj.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 4096,
    tipo_documento: "cartao_cnpj",
    enviado_por: { id: "u-1", nome: "Operador" },
    created_at: "2026-09-24T00:00:00Z",
    extracao_status: "ok",
    extracao_erro: null,
    extracao_dados: null,
    extracao_descartada_em: null,
    ...over,
  };
}

/** Dispatches the mocked `api.get` by path — `EmpresasSection` fires four
 *  GETs unconditionally (card resumo, compradores × 2 lados, empresas), plus
 *  — once a row is expanded — `EmpresaCartaoSlot`'s own documentos/url
 *  routes. `/documentos`/`/url` are checked BEFORE the bare `/empresas`
 *  suffix check, since `/api/empresas/{id}/documentos` also contains the
 *  substring "/empresas". */
function mockRoutes(
  empresas: EmpresasDoCardResponse,
  opts: { documentos?: EmpresaDocumento[]; url?: string } = {},
) {
  mockGet.mockImplementation((path: string) => {
    if (path.includes("/documentos/") && path.endsWith("/url")) {
      return Promise.resolve({ url: opts.url ?? "https://signed.example/doc-1", expires_at: "2026-09-24T01:00:00Z" });
    }
    if (path.includes("/documentos")) {
      return Promise.resolve({ items: opts.documentos ?? [] });
    }
    if (path.endsWith("/empresas")) return Promise.resolve(empresas);
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
    mockPatch.mockReset();
    mockDelete.mockReset();
    mockBaixarArquivo.mockReset();
    mockUseAuthStore.mockReturnValue({ user: null });
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

  // Slice D (owner decision, 2026-09-24): a dispensada empresa (`exige_
  // certidoes=false`) shows "Dispensada — <motivo>" on the badge — the
  // signal a collapsed row (never expanded) still carries.
  const motivoCases: Array<[EmpresaMotivo, string, boolean]> = [
    ["ativa", "Ativa", true],
    ["baixada_menos_5_anos", "Baixada há menos de 5 anos", true],
    [
      "baixada_5_anos_ou_mais",
      "Dispensada — Baixada há 5 anos ou mais — certidões dispensadas",
      false,
    ],
    ["sem_cartao_cnpj", "Dispensada — Falta Cartão CNPJ", false],
    ["outra_situacao", "Dispensada — Outra situação", false],
    ["sem_socio_certificando", "Dispensada — Sem sócio certificando", false],
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

  // Slice D (owner decision, 2026-09-24).
  describe("edit / delete / greying", () => {
    it("greys a dispensada row (never unlinks it)", async () => {
      mockRoutes(empresasResponse([empresaItem({ exige_certidoes: false })]));
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      expect(screen.getByTestId("empresa-row-emp-1-wrapper").className).toContain("opacity-60");
    });

    it("does not grey a row that still requires certidões", async () => {
      mockRoutes(empresasResponse([empresaItem({ exige_certidoes: true })]));
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      expect(screen.getByTestId("empresa-row-emp-1-wrapper").className).not.toContain(
        "opacity-60",
      );
    });

    it("hides the delete icon for a non-admin", async () => {
      mockRoutes(empresasResponse([empresaItem()]));
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      expect(screen.queryByTestId("empresa-row-emp-1-remover")).toBeNull();
      // The edit icon stays available regardless of role.
      expect(screen.getByTestId("empresa-row-emp-1-editar")).toBeTruthy();
    });

    it("shows the delete icon for an admin and opens the pt-BR confirm dialog", async () => {
      mockUseAuthStore.mockReturnValue({ user: { user_metadata: { org_role: "owner" } } });
      mockRoutes(empresasResponse([empresaItem()]));
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      fireEvent.click(screen.getByTestId("empresa-row-emp-1-remover"));

      await waitFor(() =>
        expect(screen.getByTestId("remover-empresa-confirm")).toBeTruthy(),
      );
      expect(screen.getByText(/Remover empresa\?/)).toBeTruthy();
    });

    it("toggles the edit form open, prefilled with the current values", async () => {
      mockRoutes(empresasResponse([empresaItem()]));
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      // The edit FORM lives inside the collapsible's own content, only
      // mounted once expanded — the edit ICON itself sits in the always-
      // rendered header (`resumo`), so a collapsed row's icon is clickable
      // without the form appearing until the row is also opened.
      fireEvent.click(screen.getByTestId("empresa-row-emp-1-toggle"));
      fireEvent.click(screen.getByTestId("empresa-row-emp-1-editar"));

      const razaoInput = (await screen.findByTestId(
        "empresa-editar-emp-1-razao-input",
      )) as HTMLInputElement;
      expect(razaoInput.value).toBe("Padaria do Zé Ltda");

      fireEvent.click(screen.getByTestId("empresa-editar-emp-1-cancelar"));
      await waitFor(() =>
        expect(screen.queryByTestId("empresa-editar-emp-1")).toBeNull(),
      );
    });

    it("PATCHes only the touched field on save", async () => {
      mockRoutes(empresasResponse([empresaItem()]));
      mockPatch.mockResolvedValue({
        ...empresaItem().empresa,
        nome_fantasia: "Padaria Nova",
        pendente_confirmacao: [],
      });
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });

      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      fireEvent.click(screen.getByTestId("empresa-row-emp-1-toggle"));
      fireEvent.click(screen.getByTestId("empresa-row-emp-1-editar"));
      const fantasiaInput = await screen.findByTestId("empresa-editar-emp-1-fantasia-input");
      fireEvent.change(fantasiaInput, { target: { value: "Padaria Nova" } });
      fireEvent.click(screen.getByTestId("empresa-editar-emp-1-salvar"));

      await waitFor(() => expect(mockPatch).toHaveBeenCalled());
      expect(mockPatch).toHaveBeenCalledWith("/api/empresas/emp-1", {
        nome_fantasia: "Padaria Nova",
      });
    });
  });

  // §D.4 — the Cartão CNPJ slot's view/download/remove, wired the same way
  // `CertidaoCasamentoSlot`'s owner wires the person-scoped slot's own three
  // callbacks (tech-lead review, 2026-09-24).
  describe("Cartão CNPJ — view / download / remove", () => {
    async function expandirLinha() {
      render(<EmpresasSection clienteId="cli-1" />, { wrapper: makeWrapper(qc) });
      await waitFor(() => expect(screen.getByTestId("empresa-row-emp-1")).toBeTruthy());
      fireEvent.click(screen.getByTestId("empresa-row-emp-1-toggle"));
      await waitFor(() =>
        expect(screen.getByTestId("empresa-cartao-emp-1-valor").textContent).toContain(
          "cartao_cnpj.pdf",
        ),
      );
    }

    it("mints a signed URL and opens it in a new tab for 'visualizar'", async () => {
      mockRoutes(empresasResponse([empresaItem()]), {
        documentos: [empresaDocumento()],
        url: "https://signed.example/cartao-view",
      });
      const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

      await expandirLinha();
      fireEvent.click(screen.getByTestId("empresa-cartao-emp-1-visualizar"));

      await waitFor(() =>
        expect(openSpy).toHaveBeenCalledWith(
          "https://signed.example/cartao-view",
          "_blank",
          "noopener,noreferrer",
        ),
      );
      // ONE route for both actions — no `?intent=` on the mint call.
      expect(mockGet).toHaveBeenCalledWith("/api/empresas/emp-1/documentos/doc-1/url");
    });

    it("mints the SAME URL route and downloads it under the original filename for 'baixar'", async () => {
      mockRoutes(empresasResponse([empresaItem()]), {
        documentos: [empresaDocumento()],
        url: "https://signed.example/cartao-download",
      });

      await expandirLinha();
      fireEvent.click(screen.getByTestId("empresa-cartao-emp-1-baixar"));

      await waitFor(() =>
        expect(mockBaixarArquivo).toHaveBeenCalledWith(
          "https://signed.example/cartao-download",
          "cartao_cnpj.pdf",
        ),
      );
      expect(mockGet).toHaveBeenCalledWith("/api/empresas/emp-1/documentos/doc-1/url");
    });

    it("🔴 removes with the slot's own motivo, as a query param — never a JSON body, mirroring the person-scoped documentos' LGPD-access-log transport", async () => {
      mockRoutes(empresasResponse([empresaItem()]), { documentos: [empresaDocumento()] });
      mockDelete.mockResolvedValue(undefined);

      await expandirLinha();
      fireEvent.click(screen.getByTestId("empresa-cartao-emp-1-descartar"));

      await waitFor(() => expect(mockDelete).toHaveBeenCalledTimes(1));
      const [path] = mockDelete.mock.calls[0];
      expect(path).toBe(
        "/api/empresas/emp-1/documentos/doc-1?motivo=" +
          encodeURIComponent("Descartado para reenvio: Cartão CNPJ"),
      );
    });

    it("invalidates the empresa's documentos AND the card's empresas list after a remove", async () => {
      mockRoutes(empresasResponse([empresaItem()]), { documentos: [empresaDocumento()] });
      mockDelete.mockResolvedValue(undefined);
      const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

      await expandirLinha();
      fireEvent.click(screen.getByTestId("empresa-cartao-emp-1-descartar"));

      await waitFor(() =>
        expect(invalidateSpy).toHaveBeenCalledWith(
          expect.objectContaining({ queryKey: ["sw", "empresas", "emp-1", "documentos"] }),
        ),
      );
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["sw", "clientes", "cli-1", "empresas"] }),
      );
    });
  });
});
