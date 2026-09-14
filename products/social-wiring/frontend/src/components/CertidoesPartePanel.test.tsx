/**
 * CertidoesPartePanel.test.tsx — contract automation F1's per-parte panel.
 *
 * What these protect:
 *   1. The four states, honestly: skeleton only while genuinely empty-handed,
 *      empty state offering "vincular consulta", an error banner that keeps
 *      showing stale data when there is any, and the success table.
 *   2. The vincular flow: only unlinked consultas are offered, and picking
 *      one calls `useVincularParte` with both ids.
 *   3. Suggestion vs. confirmed rendering (`resultado_origem`), and the
 *      expired/expiring `validade_ate` flag.
 *   4. The edit+confirm dialog submits only changed fields, and an untouched
 *      submit still confirms with an empty patch.
 *   5. View/download route through `useMintResultadoUrl`, never `arquivo_url`
 *      directly.
 *
 * Mock strategy mirrors `pages/Certidoes.test.tsx`: one `vi.mock` per module,
 * hooks configured per-test. `Select` is re-mocked here (not the page's
 * children-only stub) as a native `<select>` so `fireEvent.change` can drive
 * `onValueChange` — the vincular/edit flows both depend on it firing.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── Hook mocks ─────────────────────────────────────────────────────────────

const mockUseResultadosPorParte = vi.fn();
const mockUseCertidaoConsultas = vi.fn();
const mockVincular = vi.fn();
const mockConfirmar = vi.fn();
const mockUpload = vi.fn();
const mockMintUrl = vi.fn();
const mockDownloadTranscricaoPdf = vi.fn();
const mockCopiarTranscricao = vi.fn();

vi.mock("@/hooks/useCertidoes", () => ({
  useResultadosPorParte: (...a: any[]) => mockUseResultadosPorParte(...a),
  useCertidaoConsultas: (...a: any[]) => mockUseCertidaoConsultas(...a),
  useVincularParte: () => ({ mutate: mockVincular, isPending: false }),
  useConfirmarResultado: () => ({ mutate: mockConfirmar, isPending: false }),
  useUploadResultadoManual: () => ({ mutate: mockUpload, isPending: false }),
  useMintResultadoUrl: () => ({ mutate: mockMintUrl, isPending: false }),
  // ABNT formatting project (`projects/abnt-formatting-CONTRACT.md` § 6).
  useDownloadTranscricaoPdf: () => ({ mutate: mockDownloadTranscricaoPdf, isPending: false }),
  useCopiarTranscricao: () => ({ copiar: mockCopiarTranscricao, activeId: undefined }),
}));

const mockDownloadFile = vi.fn();
vi.mock("@/lib/file-download", () => ({
  downloadFile: (...a: any[]) => mockDownloadFile(...a),
}));

// ─── UI stubs ───────────────────────────────────────────────────────────────

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: any) => (open ? <div data-testid="dialog">{children}</div> : null),
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));

// A native <select> so fireEvent.change actually fires onValueChange — the
// page-level mock (children-only) can't drive the vincular/edit flows.
vi.mock("@/components/ui/select", () => ({
  Select: ({ value, onValueChange, children }: any) => (
    <select
      data-testid="mock-select"
      value={value}
      onChange={(e: any) => onValueChange(e.target.value)}
    >
      <option value="" />
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: any) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: any) => <>{children}</>,
  SelectItem: ({ value, children }: any) => <option value={value}>{children}</option>,
}));

// ─── Fixtures ───────────────────────────────────────────────────────────────

const makeResultado = (overrides: Record<string, any> = {}) => ({
  id: "res-1",
  consulta_id: "consulta-1",
  tipo: "tjsp",
  nome_display: "Certidão TJSP",
  ordem: 1,
  status: "sucesso",
  created_at: "2026-08-20T10:05:00Z",
  numero: null,
  emitida_em: null,
  validade_ate: null,
  resultado: null,
  resultado_origem: null,
  confirmado_por: null,
  confirmado_em: null,
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
});

// ─── Helpers ────────────────────────────────────────────────────────────────

async function renderPanel(props: Record<string, any> = {}) {
  const React = (await import("react")).default;
  const { CertidoesPartePanel } = await import("./CertidoesPartePanel");
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(
      React.createElement(CertidoesPartePanel, { atendimentoParteId: "parte-1", ...props }),
    ),
    fireEvent: rtl.fireEvent,
    waitFor: rtl.waitFor,
    screen: rtl.screen,
  };
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("CertidoesPartePanel — loading / empty / error / success", () => {
  it("shows the skeleton only when there is genuinely nothing to show", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: undefined, isPending: true, isFetching: true }),
    );
    const { container } = await renderPanel();
    expect(container.querySelector('[data-testid="certidoes-parte-skeleton"]')).toBeTruthy();
  });

  it("does NOT show the skeleton while refetching if data already exists (lying-loading-state)", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado()], isPending: false, isFetching: true }),
    );
    const { container, getByTestId } = await renderPanel();
    expect(container.querySelector('[data-testid="certidoes-parte-skeleton"]')).toBeFalsy();
    expect(getByTestId("certidoes-parte-refreshing")).toBeTruthy();
    expect(getByTestId("certidoes-parte-panel")).toBeTruthy();
  });

  it("shows the empty state with a vincular-consulta action when there are no resultados", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    const { getByTestId } = await renderPanel();
    expect(getByTestId("certidoes-parte-empty")).toBeTruthy();
  });

  it("shows an error banner (no data yet) distinctly from a stale-data refresh failure", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: undefined, isError: true, error: new Error("boom") }),
    );
    const { getByTestId } = await renderPanel();
    expect(getByTestId("certidoes-parte-error")).toBeTruthy();
  });

  it("keeps showing stale resultados plus a small banner when a background refresh fails", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado()], isError: true, error: new Error("boom") }),
    );
    const { getByTestId } = await renderPanel();
    expect(getByTestId("certidoes-parte-refresh-error")).toBeTruthy();
    expect(getByTestId("certidoes-parte-panel")).toBeTruthy();
    expect(getByTestId("certidoes-parte-row-tjsp")).toBeTruthy();
  });

  it("renders resultado/origem/validade fields for a confirmed row", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({
        data: [
          makeResultado({
            numero: "12345",
            resultado: "negativa",
            resultado_origem: "manual",
            validade_ate: "2099-01-01",
          }),
        ],
      }),
    );
    const { getByTestId, getByText } = await renderPanel();
    const row = getByTestId("certidoes-parte-row-tjsp");
    expect(row.textContent).toContain("Negativa");
    expect(row.textContent).toContain("Nº 12345");
    expect(getByText("Confirmado manualmente")).toBeTruthy();
  });

  it("flags a suggestion (api/ia origem) as not-yet-confirmed", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({
        data: [makeResultado({ resultado: "positiva", resultado_origem: "api" })],
      }),
    );
    const { getByText } = await renderPanel();
    expect(getByText("Sugestão — a confirmar")).toBeTruthy();
    expect(getByText("API")).toBeTruthy();
  });

  it("flags an expired validade_ate", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ validade_ate: "2020-01-01" })] }),
    );
    const { getByTestId } = await renderPanel();
    expect(getByTestId("certidoes-parte-row-tjsp").textContent).toContain("(vencida)");
  });
});

describe("CertidoesPartePanel — vincular consulta", () => {
  it("offers only consultas without an atendimento_parte_id already", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({
        data: [
          { id: "c1", nome: "Maria", documento: "111", atendimento_parte_id: null },
          { id: "c2", nome: "João", documento: "222", atendimento_parte_id: "outra-parte" },
        ],
      }),
    );
    const { getByTestId, getByText, queryByText, fireEvent } = await renderPanel();
    fireEvent.click(getByTestId("certidoes-parte-empty").querySelector("button")!);
    expect(getByText(/Maria/)).toBeTruthy();
    expect(queryByText(/João/)).toBeFalsy();
  });

  it("calls useVincularParte with the chosen consulta id and this panel's parte id", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({ data: [{ id: "c1", nome: "Maria", documento: "111", atendimento_parte_id: null }] }),
    );
    const { getByTestId, fireEvent } = await renderPanel();
    fireEvent.click(getByTestId("certidoes-parte-empty").querySelector("button")!);
    fireEvent.change(getByTestId("mock-select"), { target: { value: "c1" } });
    fireEvent.click(getByTestId("dialog").querySelectorAll("button")[1]);
    expect(mockVincular).toHaveBeenCalledWith(
      { consultaId: "c1", atendimentoParteId: "parte-1" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});

describe("CertidoesPartePanel — edit + confirm", () => {
  it("submits an empty patch when the form is untouched (reviewed-and-correct confirmation)", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [makeResultado()] }));
    const { getByTestId, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    fireEvent.submit(getByTestId("certidoes-parte-edit-form"));
    expect(mockConfirmar).toHaveBeenCalledWith(
      { resultadoId: "res-1", patch: {} },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("submits only the fields the user changed", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [makeResultado()] }));
    const { getByTestId, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    fireEvent.change(getByLabelText("Número"), { target: { value: "999" } });
    fireEvent.submit(getByTestId("certidoes-parte-edit-form"));
    expect(mockConfirmar).toHaveBeenCalledWith(
      { resultadoId: "res-1", patch: { numero: "999" } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});

describe("CertidoesPartePanel — view / download", () => {
  it("mints a URL and opens it in a new tab for 'view'", async () => {
    mockMintUrl.mockImplementation((_vars, { onSuccess }: any) =>
      onSuccess({ url: "https://signed.example/x", expires_at: null }),
    );
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ arquivo_url: "bucket/key.pdf", arquivo_nome: "tjsp.pdf" })] }),
    );
    const { getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Visualizar Certidão TJSP"));
    expect(mockMintUrl).toHaveBeenCalledWith(
      { resultadoId: "res-1", intent: "view" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(openSpy).toHaveBeenCalledWith("https://signed.example/x", "_blank", "noopener,noreferrer");
    openSpy.mockRestore();
  });

  it("mints a URL and downloads it through the proxy for 'download'", async () => {
    mockMintUrl.mockImplementation((_vars, { onSuccess }: any) =>
      onSuccess({ url: "https://signed.example/x", expires_at: null }),
    );
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ arquivo_url: "bucket/key.pdf", arquivo_nome: "tjsp.pdf" })] }),
    );
    const { getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Baixar Certidão TJSP"));
    expect(mockDownloadFile).toHaveBeenCalledWith("https://signed.example/x", "tjsp.pdf");
  });

  it("does not offer view/download when the resultado has no file yet", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [makeResultado()] }));
    const { queryByLabelText } = await renderPanel();
    expect(queryByLabelText("Visualizar Certidão TJSP")).toBeFalsy();
    expect(queryByLabelText("Baixar Certidão TJSP")).toBeFalsy();
  });
});

// ─── ABNT formatting project § 6 — transcript retrieval ─────────────────────

describe("CertidoesPartePanel — transcrição (Transcrição PDF / Copiar)", () => {
  it("🔴 hides both actions when tem_transcricao is false or absent", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ tem_transcricao: false }), makeResultado({ id: "res-2" })] }),
    );
    const { queryByLabelText } = await renderPanel();
    expect(queryByLabelText("Transcrição PDF Certidão TJSP")).toBeFalsy();
    expect(queryByLabelText("Copiar transcrição Certidão TJSP")).toBeFalsy();
  });

  it("shows both actions when tem_transcricao is true", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ tem_transcricao: true })] }),
    );
    const { getByLabelText } = await renderPanel();
    expect(getByLabelText("Transcrição PDF Certidão TJSP")).toBeTruthy();
    expect(getByLabelText("Copiar transcrição Certidão TJSP")).toBeTruthy();
  });

  it("downloads the transcription PDF for the clicked resultado", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ tem_transcricao: true })] }),
    );
    const { getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Transcrição PDF Certidão TJSP"));
    expect(mockDownloadTranscricaoPdf).toHaveBeenCalledWith({
      resultadoId: "res-1",
      filename: "tjsp_transcricao.pdf",
    });
  });

  it("copies the transcription for the clicked resultado", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ tem_transcricao: true })] }),
    );
    const { getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Copiar transcrição Certidão TJSP"));
    expect(mockCopiarTranscricao).toHaveBeenCalledWith("res-1", expect.any(Function));
  });
});
