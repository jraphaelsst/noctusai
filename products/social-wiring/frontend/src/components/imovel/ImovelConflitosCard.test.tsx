/**
 * ImovelConflitosCard.test.tsx — the imóvel decide surface (migration 154).
 * Synthetic data only. Mock strategy mirrors `ConflitosPendentesPanel.test.tsx`:
 * one stub per hook + the SSO-role modules the admin check reads.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const { mockUseAuthStore, mockUseImovelConflitos, mockMutate, mockGetUrl, mockToastError } =
  vi.hoisted(() => ({
    mockUseAuthStore: vi.fn(),
    mockUseImovelConflitos: vi.fn(),
    mockMutate: vi.fn(),
    mockGetUrl: vi.fn(),
    mockToastError: vi.fn(),
  }));

vi.mock("@noctusai/seed/infra", () => ({ useAuthStore: mockUseAuthStore }));

vi.mock("@noctusai/lib", () => ({
  resolveSSOContext: (metadata: any) => {
    const m = metadata || {};
    return {
      isProductAdmin: false,
      org: { role: m.org_role ?? "member" },
    };
  },
}));

const DOC = {
  id: "doc-1",
  codigo: "AP1234",
  nome_original: "matricula-exemplo.pdf",
  mime_type: "application/pdf",
  tamanho_bytes: 10,
  tipo_documento: "matricula",
  enviado_por: null,
  created_at: "2026-09-01T00:00:00Z",
};

vi.mock("@/hooks/useImovelDados", () => ({
  useImovelConflitos: (...a: any[]) => mockUseImovelConflitos(...a),
  useImovelDocumentos: () => ({ data: [DOC] }),
  useImovelDocumentoMutations: () => ({ getUrl: { mutateAsync: mockGetUrl } }),
  useDecidirImovelConflito: () => ({ mutate: mockMutate, isPending: false, variables: undefined }),
}));

vi.mock("sonner", () => ({ toast: { error: mockToastError, success: vi.fn() } }));

import { ImovelConflitosCard, formatarValorImovel } from "./ImovelConflitosCard";

const PENDENTE = {
  id: "c1",
  codigo: "AP1234",
  campo: "numero_registro_imoveis",
  valor_anterior: "2º RI",
  origem_anterior: "manual",
  valor_proposto: "1º RI",
  origem_proposto: "matricula",
  documento_id_proposto: "doc-1",
  confianca_proposta: null,
  fonte_tabela: "matricula_extracoes",
  fonte_id: "ext-1",
  status: "pendente" as const,
  decidido_por: null,
  decidido_em: null,
  created_at: "2026-10-01T00:00:00Z",
};

function setUser(orgRole: string | null) {
  mockUseAuthStore.mockReturnValue({
    user: { user_metadata: orgRole ? { org_role: orgRole } : {} },
  });
}

beforeEach(() => {
  mockMutate.mockReset();
  mockGetUrl.mockReset();
  mockToastError.mockReset();
});

describe("ImovelConflitosCard", () => {
  it("renders nothing while nothing is pending", async () => {
    setUser("owner");
    mockUseImovelConflitos.mockReturnValue({ data: [], isError: false });
    const { render } = await import("@testing-library/react");
    const { container } = render(<ImovelConflitosCard codigo="AP1234" />);
    expect(container.firstChild).toBeNull();
    expect(mockUseImovelConflitos).toHaveBeenCalledWith("AP1234");
  });

  it("shows a retry instead of hiding a failed read", async () => {
    setUser("owner");
    const refetch = vi.fn();
    mockUseImovelConflitos.mockReturnValue({ data: undefined, isError: true, refetch });
    const { render, screen, fireEvent } = await import("@testing-library/react");
    render(<ImovelConflitosCard codigo="AP1234" />);
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("lists the field with its current and proposed value and the source document", async () => {
    setUser("member");
    mockUseImovelConflitos.mockReturnValue({ data: [PENDENTE], isError: false });
    const { render, screen } = await import("@testing-library/react");
    render(<ImovelConflitosCard codigo="AP1234" />);
    const item = screen.getByTestId("imovel-conflito-c1");
    expect(item.textContent).toContain("Número do registro de imóveis");
    expect(item.textContent).toContain("2º RI");
    expect(item.textContent).toContain("1º RI");
    expect(screen.getByTestId("imovel-conflito-c1-documento").textContent).toContain(
      "matricula-exemplo.pdf",
    );
    // A member sees what is pending but cannot decide it.
    expect(screen.queryByTestId("imovel-conflito-c1-aprovar")).toBeNull();
  });

  it("opens the source document through the signed-URL route", async () => {
    setUser("member");
    mockUseImovelConflitos.mockReturnValue({ data: [PENDENTE], isError: false });
    mockGetUrl.mockResolvedValue({ url: "https://example.test/signed" });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const { render, screen, fireEvent, waitFor } = await import("@testing-library/react");
    render(<ImovelConflitosCard codigo="AP1234" />);
    fireEvent.click(screen.getByTestId("imovel-conflito-c1-documento"));
    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(mockGetUrl).toHaveBeenCalledWith("doc-1");
    open.mockRestore();
  });

  it("names the source in words when the document is not on this imóvel", async () => {
    setUser("member");
    mockUseImovelConflitos.mockReturnValue({
      data: [{ ...PENDENTE, documento_id_proposto: null }],
      isError: false,
    });
    const { render, screen } = await import("@testing-library/react");
    render(<ImovelConflitosCard codigo="AP1234" />);
    expect(screen.getByTestId("imovel-conflito-c1-fonte").textContent).toContain(
      "Leitura da matrícula",
    );
  });

  it("an admin approves and rejects with the imóvel code and conflict id", async () => {
    setUser("owner");
    mockUseImovelConflitos.mockReturnValue({ data: [PENDENTE], isError: false });
    const { render, screen, fireEvent } = await import("@testing-library/react");
    render(<ImovelConflitosCard codigo="AP1234" />);
    fireEvent.click(screen.getByTestId("imovel-conflito-c1-aprovar"));
    expect(mockMutate.mock.calls[0][0]).toEqual({ codigo: "AP1234", conflitoId: "c1", aceitar: true });
    fireEvent.click(screen.getByTestId("imovel-conflito-c1-rejeitar"));
    expect(mockMutate.mock.calls[1][0]).toEqual({ codigo: "AP1234", conflitoId: "c1", aceitar: false });
  });
});

describe("formatarValorImovel", () => {
  it("names a pointer group by its act, never [object Object]", () => {
    expect(
      formatarValorImovel("titulo_aquisitivo", { titulo_aquisitivo_ato_id: "R.5", titulo_aquisitivo_char_inicio: 1 }),
    ).toBe("Ato R.5");
    expect(
      formatarValorImovel("onus_fonte", { onus_fonte_atos: [{ ato_id: "R.1" }, { ato_id: "AV.2" }] }),
    ).toBe("Atos R.1, AV.2");
    expect(formatarValorImovel("x", { a: 1 })).toBe('{"a":1}');
    expect(formatarValorImovel("x", null)).toBe("—");
  });
});
