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
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

vi.mock("@/components/ConflitosPendentesPanel", () => ({
  ConflitosPendentesPanel: () => <div data-testid="conflitos-pendentes-stub" />,
}));

// 🔴 `useDocumentoChecklist`/`useDocumentoMutations` are keyed by the
// `clienteId` ARGUMENT, never by call order — a blind `() => ({...})` mock
// (the shape every test below but the multi-party one uses) would still pass
// if a future refactor accidentally shared one party's upload mutation with
// another's, because nothing would ever assert on WHICH id the hook was
// invoked with. `checklistById`/`uploadMutateById` let the multi-party test
// below pin that "upload from party X posts to X's cliente_id" by keeping a
// SEPARATE spy per id — cross-contamination would show up as the wrong
// spy (or both spies) firing.
const { mockChecklist, mockDadosMutate, mockUploadMutate, checklistById, uploadMutateById } =
  vi.hoisted(() => ({
    mockChecklist: vi.fn(),
    mockDadosMutate: vi.fn(),
    mockUploadMutate: vi.fn(),
    checklistById: new Map<string, unknown>(),
    uploadMutateById: new Map<string, ReturnType<typeof vi.fn>>(),
  }));

// The single-party tests below all use clienteId="cli-1" — route that id's
// mutation through the ORIGINAL shared spy so they keep working unchanged.
uploadMutateById.set("cli-1", mockUploadMutate);

vi.mock("@/hooks/useCardHub", () => ({
  useConflitosPendentes: () => ({ data: [], isPending: false, isFetching: false }),
  useDocumentoChecklist: (id: string) => checklistById.get(id) ?? mockChecklist(),
  useDocumentoChecklistMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useDocumentoMutations: (id: string) => {
    if (!uploadMutateById.has(id)) uploadMutateById.set(id, vi.fn());
    return {
      upload: { mutate: uploadMutateById.get(id), isPending: false },
      remove: { mutate: vi.fn(), isPending: false },
      getUrl: { mutate: vi.fn(), isPending: false },
      reextrair: { mutate: vi.fn(), isPending: false, variables: undefined },
    };
  },
  useDadosPessoaisMutation: () => ({ mutate: mockDadosMutate, isPending: false }),
  useDocumentos: () => ({ data: [], isPending: false, isFetching: false }),
  // Bug 2 (prod card 755253934) — the polling/invalidation side effect;
  // this suite is about the marriage-gated UI, not the poll (see
  // `useCardHub.test.ts` for that).
  useExtracaoPollingInvalidation: () => {},
  useExtracaoSugestaoMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useTiposDocumento: () => ({
    data: [
      { tipo_documento: "outro", categoria_lgpd: "contratual", descricao: "Outro", identidade: false },
      {
        tipo_documento: "certidao_casamento",
        categoria_lgpd: "identidade",
        descricao: "Certidão de casamento",
        identidade: true,
      },
    ],
  }),
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

describe("PessoaDocumentosPanel — a party's upload posts to THAT party's cliente_id (prod card 755253934)", () => {
  // 🔴 Two married parties on the SAME card (e.g. a comprador and their
  // papel="conjuge") mounted side by side — the exact shape `ClienteCardDialog`
  // produces for `compradores.map(renderParte)`. `useDocumentoMutations`
  // (and `useDocumentoChecklist`) are keyed by the `clienteId` PROP each
  // `<PessoaDocumentosPanel>` receives — never by mount order or a shared
  // instance — so party B's upload must never reach party A's spy (which is
  // what "posts to the titular's endpoint" would look like from here: one
  // spy firing for BOTH parties instead of two spies firing once each).
  it("🔴 the certidão-de-casamento slot: each party's file lands on THEIR OWN upload mutation, never the other party's", async () => {
    checklistById.set("cli-parte-a", checklist("casado"));
    checklistById.set("cli-parte-b", checklist("casado"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(
      <>
        <PessoaDocumentosPanel clienteId="cli-parte-a" />
        <PessoaDocumentosPanel clienteId="cli-parte-b" />
      </>,
    );

    const fileA = new File(["a"], "certidao-a.pdf", { type: "application/pdf" });
    fireEvent.change(
      screen.getByTestId("certidao-casamento-cli-parte-a-arquivo-input"),
      { target: { files: [fileA] } },
    );
    const fileB = new File(["b"], "certidao-b.pdf", { type: "application/pdf" });
    fireEvent.change(
      screen.getByTestId("certidao-casamento-cli-parte-b-arquivo-input"),
      { target: { files: [fileB] } },
    );

    const uploadA = uploadMutateById.get("cli-parte-a")!;
    const uploadB = uploadMutateById.get("cli-parte-b")!;
    expect(uploadA).toHaveBeenCalledWith(
      { file: fileA, tipoDocumento: "certidao_casamento" },
      expect.any(Object),
    );
    expect(uploadB).toHaveBeenCalledWith(
      { file: fileB, tipoDocumento: "certidao_casamento" },
      expect.any(Object),
    );
    // The regression this pins: TWO INDEPENDENT spies fired exactly ONCE
    // each — a shared/titular-scoped hook (the reported bug) would instead
    // route both uploads onto ONE spy (either firing twice, or firing on the
    // wrong party's mutation while the other stays uncalled).
    expect(uploadA).toHaveBeenCalledTimes(1);
    expect(uploadB).toHaveBeenCalledTimes(1);
    expect(uploadA).not.toBe(uploadB);
  });

  it("🔴 the generic Anexos upload: each party's file lands on THEIR OWN upload mutation, never the other party's", async () => {
    checklistById.set("cli-parte-c", checklist("solteiro"));
    checklistById.set("cli-parte-d", checklist("solteiro"));
    const { PessoaDocumentosPanel } = await import("./PessoaDocumentosPanel");
    render(
      <>
        <PessoaDocumentosPanel clienteId="cli-parte-c" />
        <PessoaDocumentosPanel clienteId="cli-parte-d" />
      </>,
    );
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();

    async function enviarAnexo(clienteId: string, file: File) {
      const container = screen.getByTestId(`anexos-section-${clienteId}`);
      const secao = within(container);
      await user.click(secao.getByTestId("anexo-tipo-select"));
      await user.click(
        await screen.findByRole("option", { name: "Certidão de casamento" }),
      );
      const input = container.querySelector('input[type="file"]') as HTMLInputElement;
      Object.defineProperty(input, "files", { value: [file] });
      fireEvent.change(input);
    }

    const fileC = new File(["c"], "certidao-c.pdf", { type: "application/pdf" });
    await enviarAnexo("cli-parte-c", fileC);
    const fileD = new File(["d"], "certidao-d.pdf", { type: "application/pdf" });
    await enviarAnexo("cli-parte-d", fileD);

    const uploadC = uploadMutateById.get("cli-parte-c")!;
    const uploadD = uploadMutateById.get("cli-parte-d")!;
    expect(uploadC).toHaveBeenCalledWith(
      { file: fileC, tipoDocumento: "certidao_casamento" },
      expect.any(Object),
    );
    expect(uploadD).toHaveBeenCalledWith(
      { file: fileD, tipoDocumento: "certidao_casamento" },
      expect.any(Object),
    );
    expect(uploadC).toHaveBeenCalledTimes(1);
    expect(uploadD).toHaveBeenCalledTimes(1);
  });
});
