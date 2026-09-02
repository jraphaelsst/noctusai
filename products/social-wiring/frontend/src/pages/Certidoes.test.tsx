/**
 * Certidoes.test.tsx — the ported ERP "Certidões Negativas" surface.
 *
 * What these tests are actually protecting:
 *
 *   1. **The four states, honestly.** loading / empty / error / success, plus
 *      the two failure modes the house rule names: the table must NOT unmount
 *      while a refetch is in flight (the 3s progress poll would otherwise blank
 *      it every three seconds), and a refresh that fails while we still hold
 *      data must show the data plus a banner, never an empty page.
 *   2. **The TJSP queue.** Its cooldown counts down locally at 1s between the
 *      15s server polls, and `na_fila` reads as "Pendente (TJSP)" rather than
 *      collapsing into plain "pendente" — the distinction is the whole reason
 *      the queue is visible.
 *   3. **Every recovery path** a user reaches for when a scrape fails: cancel,
 *      reprocess, manual PDF upload (including the non-PDF rejection), delete.
 *   4. **Both retrieval paths** — per-file through the CORS proxy, and ZIP.
 *
 * Mock strategy follows this product's existing page tests: one `vi.mock` per
 * module, hooks configured per-test, Radix-backed primitives (dialog / alert-
 * dialog / select) stubbed because their jsdom behaviour is not what is under
 * test here. Deliberately NOT stubbed: the seed `Table` and `TableSkeleton`, so
 * these tests also exercise the real cross-package imports rather than a stub
 * that would pass even if the package export map were wrong.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  vi.useRealTimers();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseCertidaoConsultas = vi.fn();
const mockUseCertidaoConsulta = vi.fn();
const mockUseTjspFila = vi.fn();
const mockCreate = vi.fn();
const mockReprocessar = vi.fn();
const mockDelete = vi.fn();
const mockCancelar = vi.fn();

vi.mock("@/hooks/useCertidoes", () => ({
  useCertidaoConsultas: (...a: any[]) => mockUseCertidaoConsultas(...a),
  useCertidaoConsulta: (...a: any[]) => mockUseCertidaoConsulta(...a),
  useTjspFila: (...a: any[]) => mockUseTjspFila(...a),
  useCreateConsulta: () => ({ mutate: mockCreate, isPending: false }),
  useReprocessarConsulta: () => ({ mutate: mockReprocessar, isPending: false }),
  useDeleteConsulta: () => ({ mutate: mockDelete, isPending: false }),
  useCancelarProcessamento: () => ({ mutate: mockCancelar, isPending: false }),
}));

// ─── IO boundary mocks ──────────────────────────────────────────────────────

const mockDownloadFile = vi.fn();
const mockAuthenticatedFetch = vi.fn();
const mockTriggerBlobDownload = vi.fn();

vi.mock("@/lib/file-download", () => ({
  downloadFile: (...a: any[]) => mockDownloadFile(...a),
  authenticatedFetch: (...a: any[]) => mockAuthenticatedFetch(...a),
  triggerBlobDownload: (...a: any[]) => mockTriggerBlobDownload(...a),
}));

const mockApiUpload = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { upload: (...a: any[]) => mockApiUpload(...a) },
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...a: any[]) => mockToastSuccess(...a),
    error: (...a: any[]) => mockToastError(...a),
  },
}));

// ─── UI stubs (Radix-backed only) ───────────────────────────────────────────

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: any) => (open ? <div data-testid="dialog">{children}</div> : null),
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));
vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: any) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: any) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: any) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: any) => <h3>{children}</h3>,
  AlertDialogDescription: ({ children }: any) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: any) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: any) => (
    <button data-testid="confirm-delete" onClick={onClick}>
      {children}
    </button>
  ),
  AlertDialogCancel: ({ children }: any) => <button>{children}</button>,
}));
vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: any) => <div>{children}</div>,
  SelectTrigger: ({ children }: any) => <div>{children}</div>,
  SelectValue: ({ placeholder }: any) => <span>{placeholder}</span>,
  SelectContent: ({ children }: any) => <div>{children}</div>,
  SelectItem: ({ children }: any) => <div>{children}</div>,
}));

// ─── Fixtures ───────────────────────────────────────────────────────────────

const makeConsulta = (overrides: Record<string, any> = {}) => ({
  id: "consulta-1",
  tipo_documento: "cpf",
  documento: "12345678901",
  nome: "Maria Souza",
  status: "concluida",
  total_certidoes: 8,
  concluidas: 6,
  erros: 1,
  created_at: "2026-08-20T10:00:00Z",
  ...overrides,
});

const makeResultado = (overrides: Record<string, any> = {}) => ({
  id: "res-1",
  consulta_id: "consulta-1",
  tipo: "tjsp",
  nome_display: "Certidao TJSP",
  ordem: 1,
  status: "sucesso",
  created_at: "2026-08-20T10:05:00Z",
  ...overrides,
});

const queryStub = (overrides: Record<string, any> = {}) => ({
  data: undefined,
  isPending: false,
  isFetching: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [] }));
  mockUseCertidaoConsulta.mockReturnValue(queryStub({ data: null }));
  mockUseTjspFila.mockReturnValue(queryStub({ data: undefined }));
});

// ─── Helpers ────────────────────────────────────────────────────────────────

async function renderCertidoes() {
  const React = (await import("react")).default;
  const { default: Certidoes } = await import("./Certidoes");
  const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
  const rtl = await import("@testing-library/react");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...rtl.render(
      React.createElement(QueryClientProvider, { client }, React.createElement(Certidoes)),
    ),
    fireEvent: rtl.fireEvent,
    waitFor: rtl.waitFor,
  };
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("Certidoes — loading / empty / error / success", () => {
  it("shows the skeleton only when there is genuinely nothing to show", async () => {
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: undefined, isPending: true, isFetching: true }),
    );
    const { container, queryByTestId } = await renderCertidoes();
    // TableSkeleton is the real seed organ — it renders a placeholder table.
    expect(container.querySelector("table")).toBeTruthy();
    expect(queryByTestId("consultas-list")).toBeNull();
    expect(queryByTestId("consultas-empty")).toBeNull();
  });

  it("renders the empty state when there are no consultas", async () => {
    const { getByTestId, getByText } = await renderCertidoes();
    expect(getByTestId("consultas-empty")).toBeTruthy();
    expect(getByText("Nenhuma consulta encontrada")).toBeTruthy();
  });

  it("renders an error state with a retry action when the load fails outright", async () => {
    const refetch = vi.fn();
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: undefined, isError: true, error: new Error("rede fora"), refetch }),
    );
    const { getByTestId, getByText, fireEvent } = await renderCertidoes();
    expect(getByTestId("consultas-error")).toBeTruthy();
    expect(getByText("rede fora")).toBeTruthy();
    fireEvent.click(getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("renders the consulta card with name, document, progress and status", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    const { getByText, getByTestId } = await renderCertidoes();
    const { within } = await import("@testing-library/react");
    expect(getByText("Maria Souza")).toBeTruthy();
    expect(getByText("CPF: 12345678901")).toBeTruthy();
    expect(getByText("6/8")).toBeTruthy();
    // Scoped to the list: "Concluída" is also one of the status-filter options.
    expect(within(getByTestId("consultas-list")).getByText("Concluída")).toBeTruthy();
  });

  it("counts the summary cards off the consultas in view", async () => {
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({
        data: [
          makeConsulta({ id: "a", status: "processando" }),
          makeConsulta({ id: "b", status: "concluida" }),
          makeConsulta({ id: "c", status: "erro" }),
        ],
      }),
    );
    const { getByText, getAllByText } = await renderCertidoes();
    // Em Processamento / Concluidas / Com Erros are each 1; Total is 3.
    expect(getAllByText("1").length).toBeGreaterThanOrEqual(3);
    expect(getByText("3")).toBeTruthy();
  });
});

describe("Certidoes — no lying loading states", () => {
  it("keeps the list mounted during a refetch and flags it as refreshing", async () => {
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: [makeConsulta()], isPending: false, isFetching: true }),
    );
    const { getByTestId, getByText } = await renderCertidoes();
    // The 3s progress poll must NOT blank the table.
    expect(getByTestId("consultas-list")).toBeTruthy();
    expect(getByText("Maria Souza")).toBeTruthy();
    expect(getByTestId("consultas-refreshing")).toBeTruthy();
  });

  it("keeps showing data when a refresh fails, with an inline banner", async () => {
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: [makeConsulta()], isError: true, error: new Error("timeout") }),
    );
    const { getByTestId, getByText, queryByTestId } = await renderCertidoes();
    expect(getByTestId("consultas-stale-error")).toBeTruthy();
    expect(getByText("Maria Souza")).toBeTruthy();
    expect(queryByTestId("consultas-error")).toBeNull();
  });
});

describe("Certidoes — TJSP queue and cooldown", () => {
  const filaComCooldown = {
    items: [
      {
        id: "fila-1",
        consulta_id: "consulta-1",
        posicao: 1,
        nome: "Maria Souza",
        documento: "12345678901",
        tipo_documento: "cpf",
        created_at: "2026-08-20T10:00:00Z",
      },
    ],
    total_na_fila: 1,
    cooldown: { ativo: true, segundos_restantes: 90 },
  };

  it("renders the queue with each item's position", async () => {
    mockUseTjspFila.mockReturnValue(queryStub({ data: filaComCooldown }));
    const { getByTestId, getByText } = await renderCertidoes();
    expect(getByTestId("tjsp-fila")).toBeTruthy();
    expect(getByText("1 na fila")).toBeTruthy();
    expect(getByText("#1")).toBeTruthy();
  });

  it("counts the cooldown down locally every second between server polls", async () => {
    vi.useFakeTimers();
    mockUseTjspFila.mockReturnValue(queryStub({ data: filaComCooldown }));
    const { getByTestId } = await renderCertidoes();
    const { act } = await import("@testing-library/react");

    expect(getByTestId("tjsp-cooldown-countdown").textContent).toBe("1:30");
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(getByTestId("tjsp-cooldown-countdown").textContent).toBe("1:29");
    act(() => {
      vi.advanceTimersByTime(29_000);
    });
    expect(getByTestId("tjsp-cooldown-countdown").textContent).toBe("1:00");
  });

  it("hides the queue card entirely when the queue is empty and no cooldown is active", async () => {
    mockUseTjspFila.mockReturnValue(
      queryStub({ data: { items: [], total_na_fila: 0, cooldown: { ativo: false } } }),
    );
    const { queryByTestId } = await renderCertidoes();
    expect(queryByTestId("tjsp-fila")).toBeNull();
  });
});

describe("Certidoes — detail dialog", () => {
  const openDetalhe = async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    const r = await renderCertidoes();
    r.fireEvent.click(r.getByText("Detalhes"));
    return r;
  };

  it("labels a queued certificate as Pendente (TJSP), not plain pendente", async () => {
    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({
        data: makeConsulta({ resultados: [makeResultado({ status: "na_fila" })] }),
      }),
    );
    const { getByText } = await openDetalhe();
    expect(getByText("Pendente (TJSP)")).toBeTruthy();
  });

  it("renders each resultado row and surfaces its error message", async () => {
    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({
        data: makeConsulta({
          resultados: [
            makeResultado({ id: "r1", nome_display: "Certidao TJSP", status: "sucesso" }),
            makeResultado({
              id: "r2",
              ordem: 2,
              nome_display: "Certidao Federal",
              status: "erro",
              erro_mensagem: "Site fora do ar",
            }),
          ],
        }),
      }),
    );
    const { getByText } = await openDetalhe();
    expect(getByText("Certidao TJSP")).toBeTruthy();
    expect(getByText("Certidao Federal")).toBeTruthy();
    expect(getByText("Site fora do ar")).toBeTruthy();
  });

  it("shows a skeleton while the detail is loading and an error state when it fails", async () => {
    mockUseCertidaoConsulta.mockReturnValue(queryStub({ data: undefined, isPending: true }));
    const loading = await openDetalhe();
    expect(loading.getByTestId("detalhe-skeleton")).toBeTruthy();
    loading.unmount();

    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({ data: undefined, isError: true, error: new Error("falhou") }),
    );
    const failed = await openDetalhe();
    expect(failed.getByTestId("detalhe-error")).toBeTruthy();
  });

  it("toggles the AI analysis expander", async () => {
    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({
        data: makeConsulta({
          resultados: [makeResultado({ analise_ia: "Nada consta em nome do requerente." })],
        }),
      }),
    );
    const { getByText, getByLabelText, container, fireEvent } = await openDetalhe();
    // The panel is always in the DOM; the 0fr→1fr grid row is what reveals it.
    expect(getByText("Nada consta em nome do requerente.")).toBeTruthy();
    const collapsed = container.querySelector('[style*="grid-template-rows: 0fr"]');
    expect(collapsed).toBeTruthy();

    fireEvent.click(getByLabelText("Analise IA Certidao TJSP"));
    expect(container.querySelector('[style*="grid-template-rows: 1fr"]')).toBeTruthy();
  });
});

describe("Certidoes — retrieval", () => {
  it("routes a per-file download through the proxy helper", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({
        data: makeConsulta({
          resultados: [
            makeResultado({
              arquivo_url: "https://tjsp.jus.br/certidao.pdf",
              arquivo_nome: "tjsp.pdf",
            }),
          ],
        }),
      }),
    );
    const { getByText, getByLabelText, fireEvent } = await renderCertidoes();
    fireEvent.click(getByText("Detalhes"));
    fireEvent.click(getByLabelText("Download Certidao TJSP"));
    expect(mockDownloadFile).toHaveBeenCalledWith("https://tjsp.jus.br/certidao.pdf", "tjsp.pdf");
  });

  it("downloads the whole consulta as a ZIP", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    mockAuthenticatedFetch.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["zip"]),
    });
    const { getByText, fireEvent, waitFor } = await renderCertidoes();
    fireEvent.click(getByText("Baixar Tudo"));
    await waitFor(() => expect(mockTriggerBlobDownload).toHaveBeenCalled());
    expect(mockAuthenticatedFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/certidoes/consultas/consulta-1/download-zip"),
    );
    expect(mockTriggerBlobDownload.mock.calls[0][1]).toBe(
      "certidoes_Maria_Souza_12345678901.zip",
    );
  });

  it("toasts the backend detail when the ZIP download fails", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    mockAuthenticatedFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Nenhuma certidao concluida" }),
    });
    const { getByText, fireEvent, waitFor } = await renderCertidoes();
    fireEvent.click(getByText("Baixar Tudo"));
    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith("Nenhuma certidao concluida"),
    );
    expect(mockTriggerBlobDownload).not.toHaveBeenCalled();
  });
});

describe("Certidoes — recovery paths", () => {
  it("cancels an in-flight consulta", async () => {
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: [makeConsulta({ status: "processando" })] }),
    );
    const { getByText, fireEvent } = await renderCertidoes();
    fireEvent.click(getByText("Cancelar"));
    expect(mockCancelar).toHaveBeenCalledWith("consulta-1");
  });

  it("reprocesses a failed consulta", async () => {
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: [makeConsulta({ status: "erro" })] }),
    );
    const { getByText, fireEvent } = await renderCertidoes();
    fireEvent.click(getByText("Reprocessar"));
    expect(mockReprocessar).toHaveBeenCalledWith("consulta-1");
  });

  it("confirms before deleting", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    const { getByLabelText, getByTestId, queryByTestId, fireEvent } = await renderCertidoes();
    expect(queryByTestId("alert-dialog")).toBeNull();
    fireEvent.click(getByLabelText("Excluir consulta Maria Souza"));
    expect(getByTestId("alert-dialog")).toBeTruthy();
    expect(mockDelete).not.toHaveBeenCalled();
    fireEvent.click(getByTestId("confirm-delete"));
    expect(mockDelete).toHaveBeenCalledWith("consulta-1");
  });

  it("uploads a manual PDF for a failed certificate via the seed multipart client", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({
        data: makeConsulta({ resultados: [makeResultado({ status: "erro" })] }),
      }),
    );
    mockApiUpload.mockResolvedValue({});
    const { getByText, getByLabelText, getByTestId, fireEvent, waitFor } =
      await renderCertidoes();
    fireEvent.click(getByText("Detalhes"));
    fireEvent.click(getByLabelText("Upload manual Certidao TJSP"));

    const file = new File(["%PDF-1.4"], "certidao.pdf", { type: "application/pdf" });
    const input = getByTestId("upload-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(mockApiUpload).toHaveBeenCalled());
    expect(mockApiUpload.mock.calls[0][0]).toBe("/api/certidoes/resultados/res-1/upload");
    expect(mockApiUpload.mock.calls[0][1]).toBeInstanceOf(FormData);
    expect(mockToastSuccess).toHaveBeenCalledWith("Certidão enviada com sucesso!");
  });

  it("rejects a non-PDF upload without calling the API", async () => {
    mockUseCertidaoConsultas.mockReturnValue(queryStub({ data: [makeConsulta()] }));
    mockUseCertidaoConsulta.mockReturnValue(
      queryStub({
        data: makeConsulta({ resultados: [makeResultado({ status: "erro" })] }),
      }),
    );
    const { getByText, getByLabelText, getByTestId, fireEvent, waitFor } =
      await renderCertidoes();
    fireEvent.click(getByText("Detalhes"));
    fireEvent.click(getByLabelText("Upload manual Certidao TJSP"));

    const file = new File(["nope"], "certidao.png", { type: "image/png" });
    fireEvent.change(getByTestId("upload-input"), { target: { files: [file] } });

    await waitFor(() =>
      expect(mockToastError).toHaveBeenCalledWith("Apenas arquivos PDF são aceitos."),
    );
    expect(mockApiUpload).not.toHaveBeenCalled();
  });
});

describe("Certidoes — nova consulta form", () => {
  it("opens the form dialog from the header action", async () => {
    const { getByText, queryByText, fireEvent } = await renderCertidoes();
    expect(queryByText("Nova Consulta de Certidões")).toBeNull();
    fireEvent.click(getByText("Nova Consulta"));
    expect(getByText("Nova Consulta de Certidões")).toBeTruthy();
  });

  it("blocks submit and shows validation messages for an empty form", async () => {
    const { getByText, fireEvent, waitFor } = await renderCertidoes();
    fireEvent.click(getByText("Nova Consulta"));
    fireEvent.click(getByText("Emitir Certidões"));
    await waitFor(() => expect(getByText("Documento é obrigatório")).toBeTruthy());
    expect(getByText("Nome é obrigatório")).toBeTruthy();
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("submits a normalised payload — blank optionals become undefined", async () => {
    const { getByText, getByPlaceholderText, fireEvent, waitFor } = await renderCertidoes();
    fireEvent.click(getByText("Nova Consulta"));
    fireEvent.change(getByPlaceholderText("Apenas números"), {
      target: { value: "12345678901" },
    });
    fireEvent.change(getByPlaceholderText("Nome completo ou razão social"), {
      target: { value: "Maria Souza" },
    });
    fireEvent.click(getByText("Emitir Certidões"));

    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    const payload = mockCreate.mock.calls[0][0];
    expect(payload).toMatchObject({
      tipo_documento: "cpf",
      documento: "12345678901",
      nome: "Maria Souza",
    });
    // The cleared Select value ("") must never reach the wire.
    expect(payload.genero).toBeUndefined();
    expect(payload.rg).toBeUndefined();
    expect(payload.data_nascimento).toBeUndefined();
  });
});
