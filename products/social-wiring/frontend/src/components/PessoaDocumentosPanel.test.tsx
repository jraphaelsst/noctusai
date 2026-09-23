/**
 * PessoaDocumentosPanel.test.tsx — the party-scoped "Casado(a)" toggle and
 * certidão-de-casamento slot this slice added, gated on the SAME
 * `estado_civil` the checklist response already carries.
 *
 * `ConflitosPendentesPanel` is stubbed out (its own suite covers it): it
 * pulls `useAuthStore`/`resolveSSOContext` in ways unrelated to this file's
 * concern. Every OTHER `useCardHub` hook is mocked directly, mirroring
 * `ClienteDetailModal.test.tsx`'s own convention for this file's sibling
 * container.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

vi.mock("@/components/ConflitosPendentesPanel", () => ({
  ConflitosPendentesPanel: () => <div data-testid="conflitos-pendentes-stub" />,
}));

const { mockChecklist, mockDadosMutate, mockUploadMutate } = vi.hoisted(() => ({
  mockChecklist: vi.fn(),
  mockDadosMutate: vi.fn(),
  mockUploadMutate: vi.fn(),
}));

vi.mock("@/hooks/useCardHub", () => ({
  useConflitosPendentes: () => ({ data: [], isPending: false, isFetching: false }),
  useDocumentoChecklist: () => mockChecklist(),
  useDocumentoChecklistMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useDocumentoMutations: () => ({
    upload: { mutate: mockUploadMutate, isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
    getUrl: { mutate: vi.fn(), isPending: false },
    reextrair: { mutate: vi.fn(), isPending: false, variables: undefined },
  }),
  useDadosPessoaisMutation: () => ({ mutate: mockDadosMutate, isPending: false }),
  useDocumentos: () => ({ data: [], isPending: false, isFetching: false }),
  useExtracaoSugestaoMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useTiposDocumento: () => ({ data: [] }),
}));

function checklist(estadoCivil: string | null) {
  return {
    data: {
      items: [],
      total: 0,
      concluidos: 0,
      valores: { estado_civil: estadoCivil },
    },
    isPending: false,
    isFetching: false,
  };
}

describe("PessoaDocumentosPanel — marriage-gated UI (this slice)", () => {
  it("a married party (casado) renders the toggle AND the certidão slot", async () => {
    mockChecklist.mockReturnValue(checklist("casado"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(<PessoaDocumentosPanel clienteId="cli-1" />);
    expect(screen.getByTestId("casado-toggle-cli-1")).toBeTruthy();
    expect(screen.getByTestId("certidao-casamento-cli-1-row")).toBeTruthy();
  });

  it("a married party (união estável) ALSO renders both", async () => {
    mockChecklist.mockReturnValue(checklist("uniao_estavel"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(<PessoaDocumentosPanel clienteId="cli-1" />);
    expect(screen.getByTestId("casado-toggle-cli-1")).toBeTruthy();
    expect(screen.getByTestId("certidao-casamento-cli-1-row")).toBeTruthy();
  });

  it("🔴 a single party renders NEITHER — no empty card, no placeholder", async () => {
    mockChecklist.mockReturnValue(checklist("solteiro"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(<PessoaDocumentosPanel clienteId="cli-1" />);
    expect(screen.queryByTestId("casado-toggle-cli-1")).toBeNull();
    expect(screen.queryByTestId("certidao-casamento-cli-1-row")).toBeNull();
  });

  it("a party with no estado_civil on file renders neither", async () => {
    mockChecklist.mockReturnValue(checklist(null));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(<PessoaDocumentosPanel clienteId="cli-1" />);
    expect(screen.queryByTestId("casado-toggle-cli-1")).toBeNull();
    expect(screen.queryByTestId("certidao-casamento-cli-1-row")).toBeNull();
  });

  it("🔴 toggling off writes estado_civil THROUGH THE MUTATION — never local-only state", async () => {
    mockChecklist.mockReturnValue(checklist("casado"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(<PessoaDocumentosPanel clienteId="cli-1" />);
    fireEvent.click(screen.getByTestId("casado-toggle-cli-1-checkbox"));
    expect(mockDadosMutate).toHaveBeenCalledWith(
      { estado_civil: null },
      expect.any(Object),
    );
  });

  it("uploads the certidão with tipo_documento 'certidao_casamento'", async () => {
    mockChecklist.mockReturnValue(checklist("casado"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(<PessoaDocumentosPanel clienteId="cli-1" />);
    const file = new File(["x"], "certidao.pdf", { type: "application/pdf" });
    const input = screen.getByTestId(
      "certidao-casamento-cli-1-arquivo-input",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    expect(mockUploadMutate).toHaveBeenCalledWith(
      { file, tipoDocumento: "certidao_casamento" },
      expect.any(Object),
    );
  });
});
