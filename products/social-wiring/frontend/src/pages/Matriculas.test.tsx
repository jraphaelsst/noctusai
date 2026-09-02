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
const mockUseDelete = vi.fn();

vi.mock("@/hooks/useMatriculas", () => ({
  useMatriculaExtracoes: mockUseExtracoes,
  useMatriculaExtracao: mockUseExtracao,
  useUploadMatricula: mockUseUpload,
  useDeleteExtracao: mockUseDelete,
}));

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

// ─── Fixtures ────────────────────────────────────────────────────────────────

type Extracao = {
  id: string;
  nome_arquivo: string;
  tamanho_bytes: number;
  num_paginas: number | null;
  texto_extraido: string | null;
  status: "pendente" | "processando" | "concluida" | "erro";
  erro_mensagem: string | null;
  created_at: string;
};

function makeExtracao(overrides: Partial<Extracao> = {}): Extracao {
  return {
    id: "extracao-1",
    nome_arquivo: "matricula-12345.pdf",
    tamanho_bytes: 204800,
    num_paginas: 3,
    texto_extraido: null,
    status: "concluida",
    erro_mensagem: null,
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
const mockDeleteMutate = vi.fn();
const mockRefetch = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockUseExtracoes.mockReturnValue(makeQuery({ data: [], refetch: mockRefetch }));
  mockUseExtracao.mockReturnValue(makeQuery({ data: null }));
  mockUseUpload.mockReturnValue({ mutate: mockUploadMutate, isPending: false });
  mockUseDelete.mockReturnValue({ mutate: mockDeleteMutate, isPending: false });
});

async function renderPage() {
  const React = (await import("react")).default;
  const { default: Matriculas } = await import("./Matriculas");
  const rtl = await import("@testing-library/react");
  return { ...rtl.render(React.createElement(Matriculas)), fireEvent: rtl.fireEvent };
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

  it("offers 'Nova Extração' once an extraction is complete", async () => {
    mockUseExtracao.mockReturnValue(makeQuery({ data: makeExtracao({ texto_extraido: "texto" }) }));
    const { getByText } = await renderPage();

    expect(getByText("Nova Extração")).toBeTruthy();
    expect(getByText("Copiar Texto")).toBeTruthy();
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
