/**
 * Extrator de Matrículas page tests.
 *
 * The four states the house rule requires, plus the two behaviours that are
 * easy to regress in a port:
 *
 *   1. skeleton ONLY while pending AND there is no data
 *   2. a poll tick (`isFetching` true WITH data) must NOT blank the table —
 *      this query polls every 3 s while an extraction runs, so an
 *      `isFetching` gate would unmount the history on every tick
 *      (`KB § PATTERNS/frontend/lying-loading-state.md`)
 *   3. a failed fetch shows an ERROR branch, never "Nenhuma extração
 *      realizada" (the empty state lying over a failure — ERP's gap)
 *   4. empty + success branches
 *   5. non-PDF is rejected client-side, PDF is uploaded
 *   6. row click selects → extracted text renders
 *   7. delete asks for confirmation before mutating
 *
 * F2 additions:
 *   8. the optional imóvel código travels into the upload mutation
 *   9. `?extracao=` auto-selects that extraction once (deep-link from
 *      `ImovelCartorioCard`'s badges)
 *  10. the Atos+Fontes section only mounts once `concluída`, renders the
 *      literal act text unchanged, and the fontes confirm/choose-other/clear
 *      flow calls `useDefinirFontes` with the right patch
 *
 * Mock strategy (mirrors Marcas.test.tsx / the leads subtab tests):
 *   · ONE vi.mock per module
 *   · hooks are vi.fn()s configured per-test in beforeEach
 *   · `@noctusai/lib/design-system`'s TableSkeleton is a marker stub — the
 *     real one is covered by its own colocated test in the seed lib
 *   · the UI primitives are NOT stubbed: Card / Button / Badge / AlertDialog
 *     come from `@/components/ui/*` and the seed `Table` renders as-is, so
 *     the delete assertion goes through the REAL Radix dialog. Sourcing them
 *     locally is also what keeps the seed-framework dual-React gap (nested
 *     `@radix-ui/*` + nested `react` under `seed/framework/frontend`) off
 *     this file — it bites only components imported from `@noctusai/seed`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ──────────────────────────────────────────────────────────────

const mockUseExtracoes = vi.fn();
const mockUseExtracao = vi.fn();
const mockUseUpload = vi.fn();
const mockUseCriarManual = vi.fn();
const mockUseDelete = vi.fn();
const mockUseRetranscrever = vi.fn();
const mockUseArquivoOriginal = vi.fn();
const mockUseVincular = vi.fn();

vi.mock("@/hooks/useMatriculas", () => ({
  useMatriculaExtracoes: mockUseExtracoes,
  useMatriculaExtracao: mockUseExtracao,
  useUploadMatricula: mockUseUpload,
  useCriarExtracaoManual: mockUseCriarManual,
  useDeleteExtracao: mockUseDelete,
  useRetranscreverExtracao: mockUseRetranscrever,
  useArquivoOriginalExtracao: mockUseArquivoOriginal,
  useVincularExtracaoImovel: mockUseVincular,
}));

// Bug H's row action mounts `ImovelCodigoPicker` inside a Dialog — the real
// component fires `useQuery`/`useMutation` (`useCardHub`'s busca/registrar
// hooks) and this file renders with no QueryClientProvider (see the module
// docblock: only the base `@/components/ui/*` primitives stay real). Stubbed
// to a single button so opening the dialog cannot crash on a missing client.
const mockOnChangeCodigo = vi.fn();
vi.mock("@/components/card/ImovelCodigoPicker", () => ({
  ImovelCodigoPicker: ({ onChange }: { onChange: (codigo: string | null) => void }) => (
    <button
      type="button"
      data-testid="imovel-codigo-picker-stub"
      onClick={() => {
        mockOnChangeCodigo("ONE9001");
        onChange("ONE9001");
      }}
    >
      Escolher ONE9001
    </button>
  ),
}));

// ─── F2: atos + fontes hook mocks ────────────────────────────────────────────

const mockUseAtos = vi.fn();
const mockUseFontes = vi.fn();
const mockUseDefinirFontes = vi.fn();

const mockUseConfirmarDetalhes = vi.fn();
vi.mock("@/hooks/useMatriculaEstrutura", async (importOriginal) => {
  // `importOriginal` — the page now also reads the real NATUREZAS_ATO /
  // NATUREZA_LABEL vocabulary through the act-details editor, and a bare
  // factory would replace those constants with undefined.
  const actual = await importOriginal<typeof import("@/hooks/useMatriculaEstrutura")>();
  return {
    ...actual,
    useMatriculaAtos: mockUseAtos,
    useMatriculaFontes: mockUseFontes,
    useDefinirFontes: mockUseDefinirFontes,
    useConfirmarDetalhesAto: mockUseConfirmarDetalhes,
  };
});

// ─── Component mocks ─────────────────────────────────────────────────────────

const mockToastError = vi.fn();
const mockToastSuccess = vi.fn();
vi.mock("sonner", () => ({
  toast: { success: (...a: unknown[]) => mockToastSuccess(...a), error: (...a: unknown[]) => mockToastError(...a) },
}));

vi.mock("@noctusai/lib/design-system", () => ({
  TableSkeleton: ({ rows, columns }: { rows?: number; columns?: number }) => (
    <div data-testid="table-skeleton" data-rows={rows} data-columns={columns} />
  ),
}));

// ABNT formatting project (`projects/abnt-formatting-CONTRACT.md` § 6) — the
// seed clipboard helper and the raw-fetch download IO boundary.
const mockCopyRichText = vi.fn();
vi.mock("@noctusai/lib/clipboard", () => ({
  copyRichText: (...a: unknown[]) => mockCopyRichText(...a),
}));

const mockAuthenticatedFetch = vi.fn();
const mockTriggerBlobDownload = vi.fn();
vi.mock("@/lib/file-download", () => ({
  authenticatedFetch: (...a: unknown[]) => mockAuthenticatedFetch(...a),
  triggerBlobDownload: (...a: unknown[]) => mockTriggerBlobDownload(...a),
}));

// ─── Fixtures ────────────────────────────────────────────────────────────────

type Extracao = {
  id: string;
  nome_arquivo: string;
  tamanho_bytes: number;
  num_paginas: number | null;
  texto_extraido: string | null;
  /** ABNT formatting project (`projects/abnt-formatting-CONTRACT.md` § 4) —
   *  `null` for rows transcribed before the feature shipped. */
  texto_html?: string | null;
  status: "pendente" | "processando" | "concluida" | "erro";
  erro_mensagem: string | null;
  imovel_documento_id?: string | null;
  arquivo_origem_id?: string | null;
  substituida_por?: string | null;
  possui_marcacao_bruta?: boolean;
  /** Bug H — `null` is what makes "Vincular a imóvel" offer itself. */
  codigo?: string | null;
  created_at: string;
};

function makeExtracao(overrides: Partial<Extracao> = {}): Extracao {
  return {
    id: "extracao-1",
    nome_arquivo: "matricula-12345.pdf",
    tamanho_bytes: 204800,
    num_paginas: 3,
    texto_extraido: null,
    texto_html: null,
    status: "concluida",
    erro_mensagem: null,
    imovel_documento_id: null,
    arquivo_origem_id: null,
    substituida_por: null,
    possui_marcacao_bruta: false,
    codigo: null,
    created_at: "2026-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeQuery(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  };
}

const mockUploadMutate = vi.fn();
const mockCriarManualMutate = vi.fn();
const mockDeleteMutate = vi.fn();
const mockRefetch = vi.fn();
const mockDefinirFontesMutate = vi.fn();
const mockConfirmarDetalhesMutate = vi.fn();
const mockRetranscreverMutate = vi.fn();
const mockArquivoOriginalMutate = vi.fn();
const mockVincularMutate = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockUseExtracoes.mockReturnValue(makeQuery({ data: [], refetch: mockRefetch }));
  mockUseExtracao.mockReturnValue(makeQuery({ data: null }));
  mockUseUpload.mockReturnValue({ mutate: mockUploadMutate, isPending: false });
  mockUseCriarManual.mockReturnValue({ mutate: mockCriarManualMutate, isPending: false });
  mockUseDelete.mockReturnValue({ mutate: mockDeleteMutate, isPending: false });
  mockUseRetranscrever.mockReturnValue({ mutate: mockRetranscreverMutate, isPending: false });
  mockUseArquivoOriginal.mockReturnValue({ mutate: mockArquivoOriginalMutate, isPending: false });
  mockUseVincular.mockReturnValue({ mutate: mockVincularMutate, isPending: false });
  mockUseAtos.mockReturnValue(makeQuery({ data: { atos: [] } }));
  mockUseFontes.mockReturnValue(
    makeQuery({ data: { sugestoes: { titulo_aquisitivo: null, onus: [] }, titulo_aquisitivo: null, onus: null } }),
  );
  mockUseDefinirFontes.mockReturnValue({ mutate: mockDefinirFontesMutate, isPending: false });
  mockUseConfirmarDetalhes.mockReturnValue({
    mutate: mockConfirmarDetalhesMutate,
    isPending: false,
    isError: false,
    error: null,
    variables: undefined,
  });
});

async function renderPage(initialPath = "/matriculas") {
  const React = (await import("react")).default;
  const { default: Matriculas } = await import("./Matriculas");
  const rtl = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  return {
    ...rtl.render(
      React.createElement(
        MemoryRouter,
        { initialEntries: [initialPath] },
        React.createElement(Matriculas),
      ),
    ),
    fireEvent: rtl.fireEvent,
  };
}

function pdf(name = "matricula.pdf") {
  return new File(["%PDF-1.4"], name, { type: "application/pdf" });
}

// ─── Loading / error / empty / success ───────────────────────────────────────

describe("Matriculas — history states", () => {
  it("shows the table skeleton while pending with no data", async () => {
    mockUseExtracoes.mockReturnValue(makeQuery({ isPending: true, data: undefined }));
    const { getByTestId, queryByText } = await renderPage();

    expect(getByTestId("table-skeleton")).toBeTruthy();
    expect(queryByText("Nenhuma extração realizada")).toBeNull();
  });

  it("does NOT blank the table on a poll tick (isFetching WITH data)", async () => {
    mockUseExtracoes.mockReturnValue(
      makeQuery({ data: [makeExtracao({ status: "processando" })], isFetching: true })
    );
    const { queryByTestId, getByText } = await renderPage();

    expect(queryByTestId("table-skeleton")).toBeNull();
    expect(getByText("matricula-12345.pdf")).toBeTruthy();
    expect(getByText("Extraindo...")).toBeTruthy();
  });

  it("shows an error branch — never the empty state — when the fetch fails", async () => {
    mockUseExtracoes.mockReturnValue(makeQuery({ isError: true, data: undefined, refetch: mockRefetch }));
    const { getByTestId, getByText, queryByText, fireEvent } = await renderPage();

    expect(getByTestId("matriculas-historico-error")).toBeTruthy();
    expect(queryByText("Nenhuma extração realizada")).toBeNull();

    fireEvent.click(getByText("Tentar novamente"));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  it("shows the empty state when there are no extractions", async () => {
    const { getByText } = await renderPage();
    expect(getByText("Nenhuma extração realizada")).toBeTruthy();
  });

  it("renders a row per extraction with its status badge", async () => {
    mockUseExtracoes.mockReturnValue(
      makeQuery({
        data: [
          makeExtracao({ id: "a", nome_arquivo: "um.pdf", status: "concluida" }),
          makeExtracao({ id: "b", nome_arquivo: "dois.pdf", status: "erro", num_paginas: null }),
        ],
      })
    );
    const { getByTestId, getByText } = await renderPage();

    expect(getByTestId("matricula-row-a")).toBeTruthy();
    expect(getByTestId("matricula-row-b")).toBeTruthy();
    expect(getByText("Concluída")).toBeTruthy();
    expect(getByText("Erro")).toBeTruthy();
  });
});

// ─── Upload ──────────────────────────────────────────────────────────────────

describe("Matriculas — upload", () => {
  it("rejects a non-PDF client-side and never calls the mutation", async () => {
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.change(getByTestId("matricula-file-input"), {
      target: { files: [new File(["x"], "foto.png", { type: "image/png" })] },
    });

    expect(mockToastError).toHaveBeenCalledWith("Apenas arquivos PDF são aceitos.");
    expect(mockUploadMutate).not.toHaveBeenCalled();
  });

  it("uploads a PDF and auto-selects the new extraction on success", async () => {
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.change(getByTestId("matricula-file-input"), { target: { files: [pdf()] } });

    expect(mockUploadMutate).toHaveBeenCalledTimes(1);
    const [file, opts] = mockUploadMutate.mock.calls[0];
    expect(file.name).toBe("matricula.pdf");
    // The onSuccess callback is what makes the new extraction poll live.
    expect(typeof opts.onSuccess).toBe("function");
  });

  it("shows the sending state while the upload mutation is pending", async () => {
    mockUseUpload.mockReturnValue({ mutate: mockUploadMutate, isPending: true });
    const { getByText, queryByText } = await renderPage();

    expect(getByText("Enviando...")).toBeTruthy();
    expect(queryByText("Arraste o PDF aqui ou clique para selecionar")).toBeNull();
  });

  it("accepts a dropped PDF", async () => {
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.drop(getByTestId("matricula-dropzone"), {
      dataTransfer: { files: [pdf("arrastado.pdf")] },
    });

    expect(mockUploadMutate).toHaveBeenCalledTimes(1);
    expect(mockUploadMutate.mock.calls[0][0].name).toBe("arrastado.pdf");
  });
});

// ─── Transcrição manual (migration 149) ────────────────────────────────────

describe("Matriculas — transcrição manual", () => {
  it("is collapsed by default", async () => {
    const { queryByTestId, getByTestId } = await renderPage();

    expect(getByTestId("matricula-manual-toggle")).toBeTruthy();
    expect(queryByTestId("matricula-manual-criar")).toBeNull();
  });

  it("creates a manual transcription with the typed código + texto and auto-selects it", async () => {
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matricula-manual-toggle"));
    fireEvent.change(getByTestId("matricula-manual-codigo-input"), {
      target: { value: "ONE9001" },
    });
    fireEvent.change(getByTestId("matricula-manual-texto-input"), {
      target: { value: "MATRÍCULA Nº 1..." },
    });
    fireEvent.click(getByTestId("matricula-manual-criar"));

    expect(mockCriarManualMutate).toHaveBeenCalledTimes(1);
    const [input, opts] = mockCriarManualMutate.mock.calls[0];
    expect(input).toEqual({ codigo: "ONE9001", texto: "MATRÍCULA Nº 1..." });
    expect(typeof opts.onSuccess).toBe("function");
  });

  it("the button stays disabled until both código and texto are filled", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("matricula-manual-toggle"));
    const botao = () => getByTestId("matricula-manual-criar") as HTMLButtonElement;

    expect(botao().disabled).toBe(true);

    fireEvent.change(getByTestId("matricula-manual-codigo-input"), {
      target: { value: "ONE9001" },
    });
    expect(botao().disabled).toBe(true);

    fireEvent.change(getByTestId("matricula-manual-texto-input"), {
      target: { value: "algum texto" },
    });
    expect(botao().disabled).toBe(false);
  });

  it("shows the pending state while the mutation is in flight", async () => {
    mockUseCriarManual.mockReturnValue({ mutate: mockCriarManualMutate, isPending: true });
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.click(getByTestId("matricula-manual-toggle"));

    expect((getByTestId("matricula-manual-criar") as HTMLButtonElement).disabled).toBe(true);
  });
});

// ─── Result pane ─────────────────────────────────────────────────────────────

describe("Matriculas — result pane", () => {
  it("prompts for a selection when nothing is selected", async () => {
    const { getByText } = await renderPage();
    expect(getByText("Envie um PDF ou selecione uma extração do histórico")).toBeTruthy();
  });

  it("renders the extracted text of the selected extraction", async () => {
    mockUseExtracoes.mockReturnValue(makeQuery({ data: [makeExtracao()] }));
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "MATRÍCULA Nº 12.345 — Cartório" }) })
    );
    const { getByTestId } = await renderPage();

    expect(getByTestId("matricula-texto-extraido").textContent).toContain("MATRÍCULA Nº 12.345");
  });

  it("shows the in-flight pane while the extraction is still processing", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ status: "processando" }) }));
    const { getByText } = await renderPage();

    expect(getByText("Processando páginas com IA...")).toBeTruthy();
  });

  it("shows the failure pane and the backend message when extraction errored", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ status: "erro", erro_mensagem: "PDF protegido por senha" }) })
    );
    const { getByText } = await renderPage();

    expect(getByText("Não foi possível extrair o texto")).toBeTruthy();
    expect(getByText("PDF protegido por senha")).toBeTruthy();
  });

  it("offers 'Nova Extração', 'Baixar PDF' and 'Copiar' once an extraction is complete", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    const { getByText, queryByText } = await renderPage();

    expect(getByText("Nova Extração")).toBeTruthy();
    expect(getByText("Baixar PDF")).toBeTruthy();
    expect(getByText("Copiar")).toBeTruthy();
    // The old copy-plain-text-only action is gone, not just renamed.
    expect(queryByText("Copiar Texto")).toBeNull();
  });
});

// ─── Migration 135 — source retention, retranscribe, raw-markup legibility ──

describe("Matriculas — ver original / retranscrever (migration 135)", () => {
  it("shows 'Ver original' and 'Retranscrever' for a concluded row with a retained linked source", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "texto", imovel_documento_id: "doc-1" }) }),
    );
    const { getByText } = await renderPage();

    expect(getByText("Ver original")).toBeTruthy();
    expect(getByText("Retranscrever")).toBeTruthy();
  });

  it("shows both for a concluded row with a retained STANDALONE source too", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "texto", arquivo_origem_id: "arq-1" }) }),
    );
    const { getByText } = await renderPage();

    expect(getByText("Ver original")).toBeTruthy();
    expect(getByText("Retranscrever")).toBeTruthy();
  });

  it("hides both when the row kept no retained source (a pre-135 legacy row)", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    const { queryByText } = await renderPage();

    expect(queryByText("Ver original")).toBeNull();
    expect(queryByText("Retranscrever")).toBeNull();
  });

  it("hides 'Retranscrever' (but keeps 'Ver original') once the row has already been superseded", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({
        data: makeExtracao({ texto_extraido: "texto", imovel_documento_id: "doc-1", substituida_por: "nova-id" }),
      }),
    );
    const { getByText, queryByText } = await renderPage();

    expect(getByText("Ver original")).toBeTruthy();
    expect(queryByText("Retranscrever")).toBeNull();
    expect(getByText(/substituída por uma retranscrição mais recente/i)).toBeTruthy();
  });

  it("clicking 'Retranscrever' mutates with the extraction id and selects the new row on success", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ id: "extracao-1", texto_extraido: "texto", imovel_documento_id: "doc-1" }) }),
    );
    mockRetranscreverMutate.mockImplementation((id: string, opts?: { onSuccess?: (d: unknown) => void }) => {
      opts?.onSuccess?.({ id: "extracao-2" });
    });
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Retranscrever"));
    expect(mockRetranscreverMutate).toHaveBeenCalledWith("extracao-1", expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it("clicking 'Ver original' opens the signed url in a new tab", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ id: "extracao-1", texto_extraido: "texto", arquivo_origem_id: "arq-1" }) }),
    );
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    mockArquivoOriginalMutate.mockImplementation((id: string, opts?: { onSuccess?: (d: unknown) => void }) => {
      opts?.onSuccess?.({ url: "https://signed.example/x", expires_at: "2026-01-01T00:00:00Z" });
    });
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Ver original"));
    expect(mockArquivoOriginalMutate).toHaveBeenCalledWith("extracao-1", expect.any(Object));
    expect(openSpy).toHaveBeenCalledWith("https://signed.example/x", "_blank", "noopener,noreferrer");
    openSpy.mockRestore();
  });

  it("🔴 warns when the transcription still carries raw **/<u> markup, and points at 'Retranscrever' when a source is retained", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({
        data: makeExtracao({
          texto_extraido: "Texto com **marcação",
          possui_marcacao_bruta: true,
          arquivo_origem_id: "arq-1",
        }),
      }),
    );
    const { getByTestId, getByText } = await renderPage();

    expect(getByTestId("matricula-marcacao-bruta-aviso")).toBeTruthy();
    expect(getByText(/Use "Retranscrever" para corrigir/)).toBeTruthy();
  });

  it("🔴 the raw-markup warning names 're-upload' instead when there is no retained source to retranscribe from", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "Texto com **marcação", possui_marcacao_bruta: true }) }),
    );
    const { getByTestId } = await renderPage();

    expect(getByTestId("matricula-marcacao-bruta-aviso").textContent).toMatch(/envie o arquivo novamente/i);
  });

  it("does not show the raw-markup warning for a clean transcription", async () => {
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "texto limpo", possui_marcacao_bruta: false }) }),
    );
    const { queryByTestId } = await renderPage();

    expect(queryByTestId("matricula-marcacao-bruta-aviso")).toBeNull();
  });

  it("shows the same raw-markup badge and 'substituída' badge in the history row", async () => {
    mockUseExtracoes.mockReturnValue(
      makeQuery({
        data: [makeExtracao({ id: "e1", possui_marcacao_bruta: true }), makeExtracao({ id: "e2", substituida_por: "e3" })],
      }),
    );
    const { getByTestId, getByText } = await renderPage();

    expect(getByTestId("matricula-row-e1").querySelector("svg")).toBeTruthy();
    expect(getByTestId("matricula-row-e2")).toBeTruthy();
    expect(getByText("substituída")).toBeTruthy();
  });
});

// ─── ABNT formatting project § 6 — Copiar (rich-text clipboard) ─────────────

describe("Matriculas — Copiar (rich-text clipboard)", () => {
  it("🔴 copies via copyRichText(texto_html, texto_extraido) and toasts success when rich", async () => {
    mockCopyRichText.mockResolvedValue({ rich: true });
    mockUseExtracao.mockReturnValue(
      makeQuery({
        data: makeExtracao({ texto_extraido: "MATRÍCULA Nº 1", texto_html: "<p><b>MATRÍCULA</b> Nº 1</p>" }),
      }),
    );
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Copiar"));
    await vi.waitFor(() => expect(mockCopyRichText).toHaveBeenCalledWith("<p><b>MATRÍCULA</b> Nº 1</p>", "MATRÍCULA Nº 1"));
    await vi.waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith("Texto copiado!"));
  });

  it("says so — never a silent downgrade — when copyRichText falls back to plain text", async () => {
    mockCopyRichText.mockResolvedValue({ rich: false });
    mockUseExtracao.mockReturnValue(
      makeQuery({
        data: makeExtracao({ texto_extraido: "texto", texto_html: "<p>texto</p>" }),
      }),
    );
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Copiar"));
    await vi.waitFor(() =>
      expect(mockToastSuccess).toHaveBeenCalledWith("Texto copiado (sem formatação)."),
    );
  });

  it("🔴 when texto_html is null, copies plain text directly and says so", async () => {
    const mockWriteText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mockWriteText },
    });
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "texto sem html", texto_html: null }) }),
    );
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Copiar"));
    await vi.waitFor(() => expect(mockWriteText).toHaveBeenCalledWith("texto sem html"));
    expect(mockCopyRichText).not.toHaveBeenCalled();
    await vi.waitFor(() =>
      expect(mockToastSuccess).toHaveBeenCalledWith("Texto copiado (sem formatação)."),
    );
  });
});

// ─── ABNT formatting project § 6 — Baixar PDF ───────────────────────────────

describe("Matriculas — Baixar PDF", () => {
  function headers(map: Record<string, string>) {
    return { get: (name: string) => map[name] ?? null };
  }

  it("🔴 downloads the blob and saves it under the server's Content-Disposition filename", async () => {
    mockAuthenticatedFetch.mockResolvedValue({
      ok: true,
      headers: headers({ "Content-Disposition": 'attachment; filename="matricula-12345_transcricao.pdf"' }),
      blob: async () => new Blob(["%PDF"]),
    });
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ id: "extracao-9", texto_extraido: "texto" }) }),
    );
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Baixar PDF"));
    await vi.waitFor(() => expect(mockTriggerBlobDownload).toHaveBeenCalled());
    expect(mockAuthenticatedFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/matriculas/extracoes/extracao-9/pdf"),
    );
    expect(mockTriggerBlobDownload.mock.calls[0][1]).toBe("matricula-12345_transcricao.pdf");
  });

  it("falls back to `<nome_arquivo>_transcricao.pdf` when Content-Disposition is missing", async () => {
    mockAuthenticatedFetch.mockResolvedValue({
      ok: true,
      headers: headers({}),
      blob: async () => new Blob(["%PDF"]),
    });
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ nome_arquivo: "matricula-12345.pdf", texto_extraido: "texto" }) }),
    );
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Baixar PDF"));
    await vi.waitFor(() => expect(mockTriggerBlobDownload).toHaveBeenCalled());
    expect(mockTriggerBlobDownload.mock.calls[0][1]).toBe("matricula-12345.pdf_transcricao.pdf");
  });

  it("🔴 toasts the backend detail on a 409 (transcription not yet complete)", async () => {
    mockAuthenticatedFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Transcrição ainda não concluída" }),
    });
    mockUseExtracao.mockReturnValue(
      makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }),
    );
    const { getByText, fireEvent } = await renderPage();

    fireEvent.click(getByText("Baixar PDF"));
    await vi.waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith("Transcrição ainda não concluída"),
    );
    expect(mockTriggerBlobDownload).not.toHaveBeenCalled();
  });
});

// ─── Delete ──────────────────────────────────────────────────────────────────

describe("Matriculas — delete", () => {
  it("asks for confirmation before deleting, then mutates with the row id", async () => {
    mockUseExtracoes.mockReturnValue(makeQuery({ data: [makeExtracao({ id: "extracao-9" })] }));
    const { getByTitle, findByText, fireEvent } = await renderPage();

    fireEvent.click(getByTitle("Excluir"));
    expect(mockDeleteMutate).not.toHaveBeenCalled();

    const confirm = await findByText("Excluir Extração");
    expect(confirm).toBeTruthy();

    fireEvent.click(await findByText("Excluir", { selector: "button" }));
    expect(mockDeleteMutate).toHaveBeenCalledWith("extracao-9");
  });
});

// ─── F2: optional imóvel código on upload ────────────────────────────────────

describe("Matriculas — upload with an optional imóvel código", () => {
  it("uploads with `{file, codigo}` once a código is typed", async () => {
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.change(getByTestId("matricula-codigo-input"), { target: { value: "one9001" } });
    fireEvent.change(getByTestId("matricula-file-input"), { target: { files: [pdf()] } });

    expect(mockUploadMutate).toHaveBeenCalledTimes(1);
    const [input] = mockUploadMutate.mock.calls[0];
    expect(input).toEqual({ file: expect.any(File), codigo: "one9001" });
  });

  it("uploads a bare File when no código was typed — unchanged pre-F2 behaviour", async () => {
    const { getByTestId, fireEvent } = await renderPage();
    fireEvent.change(getByTestId("matricula-file-input"), { target: { files: [pdf()] } });
    expect(mockUploadMutate.mock.calls[0][0]).toBeInstanceOf(File);
  });
});

// ─── F2: `?extracao=` deep-link ───────────────────────────────────────────────

describe("Matriculas — ?extracao= deep-link", () => {
  it("🔴 auto-selects the extraction named in the query string", async () => {
    mockUseExtracao.mockImplementation((id?: string) =>
      makeQuery({ data: id ? makeExtracao({ id, texto_extraido: "texto do link" }) : null }),
    );
    const { getByTestId } = await renderPage("/matriculas?extracao=extracao-77");
    expect(getByTestId("matricula-texto-extraido").textContent).toContain("texto do link");
  });
});

// ─── Bug 2: `?codigo=` deep-link prefills the upload "Imóvel (opcional)" ──────
//
// `ImovelContratoCard`'s "Abrir a matrícula" links here as
// `/matriculas?codigo=<codigo>` whenever the imóvel has no extraction yet
// (see `linkDaMatricula`) — the upload field must already carry that código
// so the next PDF the operator drops lands linked to the right imóvel.

describe("Matriculas — ?codigo= deep-link prefills the upload field", () => {
  it("🔴 prefills 'Imóvel (opcional)' from the query string", async () => {
    const { getByTestId } = await renderPage("/matriculas?codigo=E2E-IMV-LIVRE");
    const input = getByTestId("matricula-codigo-input") as HTMLInputElement;
    expect(input.value).toBe("E2E-IMV-LIVRE");
  });

  it("leaves the field empty with no ?codigo= param", async () => {
    const { getByTestId } = await renderPage();
    const input = getByTestId("matricula-codigo-input") as HTMLInputElement;
    expect(input.value).toBe("");
  });

  it("never overwrites a value the operator already typed", async () => {
    const { getByTestId, fireEvent } = await renderPage("/matriculas?codigo=E2E-IMV-LIVRE");
    const input = getByTestId("matricula-codigo-input") as HTMLInputElement;
    expect(input.value).toBe("E2E-IMV-LIVRE");

    fireEvent.change(input, { target: { value: "" } });
    fireEvent.change(input, { target: { value: "OUTRO123" } });
    expect(input.value).toBe("OUTRO123");
  });
});

// ─── F2: Atos + Fontes section ────────────────────────────────────────────────

function makeAto(over: Record<string, unknown> = {}) {
  return {
    id: "ato-1",
    ordem: 0,
    kind: "R",
    numero: 1,
    char_inicio: 0,
    char_fim: 40,
    header_inicio: null,
    header_fim: null,
    rotulo: "R-1 Compra e venda",
    texto: "R-1  Compra e venda a Joao,  CPF incorreto proposiltalmente.",
    ...over,
  };
}

describe("Matriculas — Atos + Fontes (only once concluída)", () => {
  it("does NOT mount the section while processing", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ status: "processando" }) }));
    const { queryByText } = await renderPage();
    expect(queryByText("Atos e Fontes")).toBeNull();
  });

  it("🔴 renders each act's literal text unchanged — double spaces and a typo included", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    mockUseAtos.mockReturnValue(makeQuery({ data: { atos: [makeAto()] } }));
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matriculas-ato-toggle-ato-1"));
    expect(getByTestId("matriculas-ato-texto-ato-1").textContent).toBe(
      "R-1  Compra e venda a Joao,  CPF incorreto proposiltalmente.",
    );
  });

  it("confirming the título aquisitivo suggestion PUTs its ato_id", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    mockUseFontes.mockReturnValue(
      makeQuery({
        data: {
          sugestoes: {
            titulo_aquisitivo: { ato_id: "ato-1", rotulo: "R-1", termo: "compra e venda" },
            onus: [],
          },
          titulo_aquisitivo: null,
          onus: null,
        },
      }),
    );
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matriculas-titulo-confirmar-sugestao"));
    expect(mockDefinirFontesMutate).toHaveBeenCalledWith({ titulo_aquisitivo_ato_id: "ato-1" });
  });

  it("🔴 clearing a confirmed título aquisitivo sends null, not an omitted key", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    mockUseFontes.mockReturnValue(
      makeQuery({
        data: {
          sugestoes: { titulo_aquisitivo: null, onus: [] },
          titulo_aquisitivo: {
            extracao_id: "extracao-1",
            ato_id: "ato-1",
            char_inicio: 0,
            char_fim: 10,
            texto: "R-1 compra e venda",
            origem: "sugerido",
            confirmado_por: { id: "u1", nome: "Ana" },
            confirmado_em: "2026-02-01T00:00:00Z",
          },
          onus: null,
        },
      }),
    );
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matriculas-titulo-limpar"));
    expect(mockDefinirFontesMutate).toHaveBeenCalledWith({ titulo_aquisitivo_ato_id: null });
  });

  it("using ônus suggestions PUTs only the still-suggested ato ids", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    mockUseFontes.mockReturnValue(
      makeQuery({
        data: {
          sugestoes: {
            titulo_aquisitivo: null,
            onus: [
              { ato_id: "ato-2", rotulo: "R-2", tipo: "hipoteca", sugerido: true, cancelamento_citado_por: [] },
              { ato_id: "ato-3", rotulo: "AV-3", tipo: "hipoteca", sugerido: false, cancelamento_citado_por: ["ato-4"] },
            ],
          },
          titulo_aquisitivo: null,
          onus: null,
        },
      }),
    );
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matriculas-onus-usar-sugestoes"));
    expect(mockDefinirFontesMutate).toHaveBeenCalledWith({ onus_ato_ids: ["ato-2"] });
  });

  it("🔴 clearing a confirmed ônus sends an empty list", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    mockUseFontes.mockReturnValue(
      makeQuery({
        data: {
          sugestoes: { titulo_aquisitivo: null, onus: [] },
          titulo_aquisitivo: null,
          onus: {
            extracao_id: "extracao-1",
            atos: [{ ato_id: "ato-2", char_inicio: 0, char_fim: 5, texto: "x" }],
            origem: "manual",
            confirmado_por: { id: "u1", nome: "Ana" },
            confirmado_em: "2026-02-01T00:00:00Z",
          },
        },
      }),
    );
    const { getByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matriculas-onus-limpar"));
    expect(mockDefinirFontesMutate).toHaveBeenCalledWith({ onus_ato_ids: [] });
  });

  it("shows the error branches — never a silent empty catalog", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    mockUseAtos.mockReturnValue(makeQuery({ isError: true, data: undefined }));
    mockUseFontes.mockReturnValue(makeQuery({ isError: true, data: undefined }));
    const { getByTestId } = await renderPage();

    expect(getByTestId("matriculas-atos-erro")).toBeTruthy();
    expect(getByTestId("matriculas-fontes-erro")).toBeTruthy();
  });
});

describe("Matriculas — Bug H: 'Vincular a imóvel' row action", () => {
  it("🔴 offers the action only for a row with no codigo", async () => {
    mockUseExtracoes.mockReturnValue(
      makeQuery({
        data: [
          makeExtracao({ id: "sem-codigo", codigo: null }),
          makeExtracao({ id: "com-codigo", codigo: "ONE9001" }),
        ],
      }),
    );
    const { getByTestId, queryByTestId } = await renderPage();

    expect(getByTestId("matricula-row-sem-codigo-vincular")).toBeTruthy();
    expect(queryByTestId("matricula-row-com-codigo-vincular")).toBeNull();
  });

  it("🔴 opens the picker dialog and links the chosen imóvel", async () => {
    mockUseExtracoes.mockReturnValue(
      makeQuery({ data: [makeExtracao({ id: "sem-codigo", codigo: null })] }),
    );
    const { getByTestId, queryByTestId, fireEvent } = await renderPage();

    expect(queryByTestId("matricula-vincular-dialog")).toBeNull();
    fireEvent.click(getByTestId("matricula-row-sem-codigo-vincular"));
    expect(getByTestId("matricula-vincular-dialog")).toBeTruthy();

    fireEvent.click(getByTestId("imovel-codigo-picker-stub"));
    expect(mockVincularMutate).toHaveBeenCalledWith(
      { extracaoId: "sem-codigo", codigo: "ONE9001" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("closes the dialog once the link succeeds", async () => {
    mockUseExtracoes.mockReturnValue(
      makeQuery({ data: [makeExtracao({ id: "sem-codigo", codigo: null })] }),
    );
    mockVincularMutate.mockImplementation((_vars, opts) => opts?.onSuccess?.());
    const { getByTestId, queryByTestId, fireEvent } = await renderPage();

    fireEvent.click(getByTestId("matricula-row-sem-codigo-vincular"));
    fireEvent.click(getByTestId("imovel-codigo-picker-stub"));

    expect(queryByTestId("matricula-vincular-dialog")).toBeNull();
  });
});
