/**
 * CertidoesPartePanel.test.tsx — contract automation F1 + F6's per-
 * parte/per-cliente panel.
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
 *   6. Titular routing (migration 116): `clienteId` reaches the cliente-
 *      scoped hooks/routes, never the per-parte ones, and vice versa.
 *   7. The situação cadastral editor's derived pt-BR badge, including the
 *      5-year `baixada` boundary.
 *   8. `negativa_com_homonimos` is offered as a `resultado` option.
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
const mockUseResultadosPorCliente = vi.fn();
const mockUseResultadosPorEmpresa = vi.fn();
const mockUseCertidaoConsultas = vi.fn();
const mockVincularParte = vi.fn();
const mockVincularCliente = vi.fn();
const mockVincularEmpresa = vi.fn();
const mockConfirmar = vi.fn();
const mockUpload = vi.fn();
const mockAtualizarSituacaoCadastral = vi.fn();
const mockCriarManual = vi.fn();
const mockMintUrl = vi.fn();
const mockDownloadTranscricaoPdf = vi.fn();
const mockCopiarTranscricao = vi.fn();

vi.mock("@/hooks/useCertidoes", () => ({
  useResultadosPorParte: (...a: any[]) => mockUseResultadosPorParte(...a),
  useResultadosPorCliente: (...a: any[]) => mockUseResultadosPorCliente(...a),
  // P0c contract §D.5 — the empresa-scoped sibling; unused by this file's
  // existing parte/cliente suites (their `resultados` picks a different
  // branch), but `CertidoesPartePanel` always calls all three hooks.
  useResultadosPorEmpresa: (...a: any[]) => mockUseResultadosPorEmpresa(...a),
  useCertidaoConsultas: (...a: any[]) => mockUseCertidaoConsultas(...a),
  useVincularParte: () => ({ mutate: mockVincularParte, isPending: false }),
  useVincularCliente: () => ({ mutate: mockVincularCliente, isPending: false }),
  useVincularEmpresa: () => ({ mutate: mockVincularEmpresa, isPending: false }),
  useConfirmarResultado: () => ({ mutate: mockConfirmar, isPending: false }),
  useUploadResultadoManual: () => ({ mutate: mockUpload, isPending: false }),
  useCriarConsultaManual: () => ({ mutate: mockCriarManual, isPending: false }),
  useAtualizarSituacaoCadastral: () => ({
    mutate: mockAtualizarSituacaoCadastral,
    isPending: false,
  }),
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
  // All three hooks are ALWAYS called (rules-of-hooks — see the component's
  // own docblock); the two not selected by `clienteId`/`atendimentoParteId`/
  // `empresaId` still need a well-shaped stub so accessing them never throws.
  mockUseResultadosPorParte.mockReturnValue(queryStub({ data: undefined }));
  mockUseResultadosPorCliente.mockReturnValue(queryStub({ data: undefined }));
  mockUseResultadosPorEmpresa.mockReturnValue(queryStub({ data: undefined }));
});

// ─── Helpers ────────────────────────────────────────────────────────────────

async function renderPanel(props: Record<string, any> = {}) {
  const React = (await import("react")).default;
  const { CertidoesPartePanel } = await import("./CertidoesPartePanel");
  const rtl = await import("@testing-library/react");
  // A test that passes `clienteId` is exercising the titular path — it must
  // NOT also inherit the parte default, or the panel would receive both.
  const defaults = "clienteId" in props ? {} : { atendimentoParteId: "parte-1" };
  return {
    ...rtl.render(React.createElement(CertidoesPartePanel, { ...defaults, ...props })),
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
    expect(mockVincularParte).toHaveBeenCalledWith(
      { consultaId: "c1", atendimentoParteId: "parte-1" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});

describe("CertidoesPartePanel — edit + confirm", () => {
  it("submits an empty patch when the form is untouched (reviewed-and-correct confirmation)", async () => {
    // `emitida_em` already set — the "untouched submit" invariant this test
    // pins only holds for a row that already has a date. A never-yet-set
    // one gets today's date prefilled (see the next test) and therefore
    // does NOT round-trip to an empty patch untouched.
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ emitida_em: "2026-08-20" })] }),
    );
    const { getByTestId, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    fireEvent.submit(getByTestId("certidoes-parte-edit-form"));
    expect(mockConfirmar).toHaveBeenCalledWith(
      { resultadoId: "res-1", patch: {} },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("submits only the fields the user changed", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ emitida_em: "2026-08-20" })] }),
    );
    const { getByTestId, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    fireEvent.change(getByLabelText("Número"), { target: { value: "999" } });
    fireEvent.submit(getByTestId("certidoes-parte-edit-form"));
    expect(mockConfirmar).toHaveBeenCalledWith(
      { resultadoId: "res-1", patch: { numero: "999" } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("prefills a never-yet-set 'emitida em' with today, so confirming it untouched still stamps a date", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ emitida_em: null })] }),
    );
    const { getByTestId, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    // Local date, matching the component's own `hojeIso()` — NOT
    // `toISOString()`, which is UTC and can disagree with the local date
    // near midnight in any timezone west of UTC.
    const agora = new Date();
    const hoje = `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}-${String(agora.getDate()).padStart(2, "0")}`;
    expect((getByLabelText("Emitida em") as HTMLInputElement).value).toBe(hoje);
    fireEvent.submit(getByTestId("certidoes-parte-edit-form"));
    expect(mockConfirmar).toHaveBeenCalledWith(
      { resultadoId: "res-1", patch: { emitida_em: hoje } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("still lets the prefilled 'emitida em' be changed to a different date", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ emitida_em: null })] }),
    );
    const { getByTestId, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    fireEvent.change(getByLabelText("Emitida em"), { target: { value: "2026-01-05" } });
    fireEvent.submit(getByTestId("certidoes-parte-edit-form"));
    expect(mockConfirmar).toHaveBeenCalledWith(
      { resultadoId: "res-1", patch: { emitida_em: "2026-01-05" } },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });
});

describe("CertidoesPartePanel — registrar certidões manualmente", () => {
  it("offers the manual-registration action alongside vincular consulta in the empty state", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    const { getByText } = await renderPanel();
    expect(getByText("Registrar certidões manualmente")).toBeTruthy();
  });

  it("creates + links a manual consulta with the person's name/documento, no InfoSimples involved", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    const { getByTestId, getByText, getByLabelText, fireEvent } = await renderPanel({
      atendimentoParteId: "parte-1",
      nomeParte: "Maria de Teste",
    });
    fireEvent.click(getByText("Registrar certidões manualmente"));
    // Nome is prefilled from `nomeParte` — the office does not retype it.
    expect((getByLabelText("Nome completo / Razão social") as HTMLInputElement).value).toBe(
      "Maria de Teste",
    );
    fireEvent.change(getByLabelText("Documento"), { target: { value: "12345678901" } });
    fireEvent.click(getByTestId("dialog").querySelectorAll("button")[1]);
    expect(mockCriarManual).toHaveBeenCalledWith(
      {
        tipo_documento: "cpf",
        documento: "12345678901",
        nome: "Maria de Teste",
        atendimentoParteId: "parte-1",
        clienteId: undefined,
      },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("prefills the documento field from the `documento` prop, still editable", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    const { getByText, getByLabelText, fireEvent } = await renderPanel({
      atendimentoParteId: "parte-1",
      nomeParte: "Maria de Teste",
      documento: "12345678901",
    });
    fireEvent.click(getByText("Registrar certidões manualmente"));
    const documentoInput = getByLabelText("Documento") as HTMLInputElement;
    expect(documentoInput.value).toBe("12345678901");
    // Still editable — the prefill is not read-only.
    fireEvent.change(documentoInput, { target: { value: "99988877766" } });
    expect(documentoInput.value).toBe("99988877766");
  });

  it("leaves documento blank when the caller has none on file", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [] }));
    const { getByText, getByLabelText, fireEvent } = await renderPanel();
    fireEvent.click(getByText("Registrar certidões manualmente"));
    expect((getByLabelText("Documento") as HTMLInputElement).value).toBe("");
  });

  it("routes the titular's manual registration through clienteId, not atendimentoParteId", async () => {
    mockUseResultadosPorCliente.mockReturnValue(queryStub({ data: [] }));
    const { getByTestId, getByText, getByLabelText, fireEvent } = await renderPanel({
      clienteId: "cliente-1",
      nomeParte: "Titular de Teste",
    });
    fireEvent.click(getByText("Registrar certidões manualmente"));
    fireEvent.change(getByLabelText("Documento"), { target: { value: "98765432100" } });
    fireEvent.click(getByTestId("dialog").querySelectorAll("button")[1]);
    expect(mockCriarManual).toHaveBeenCalledWith(
      expect.objectContaining({ atendimentoParteId: undefined, clienteId: "cliente-1" }),
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

// ─── Titular vs. parte routing (migration 116, contract F6) ─────────────────

describe("CertidoesPartePanel — titular routing (clienteId)", () => {
  it("reads through useResultadosPorCliente, never useResultadosPorParte, when given clienteId", async () => {
    mockUseResultadosPorCliente.mockReturnValue(
      queryStub({ data: [makeResultado({ id: "res-titular" })] }),
    );
    const { getByTestId } = await renderPanel({ clienteId: "cliente-1", atendimentoParteId: undefined });
    expect(mockUseResultadosPorCliente).toHaveBeenCalledWith("cliente-1");
    // The unused hook is still called (rules-of-hooks) but with no id —
    // its inert `enabled: false` shape must never be what the table reads.
    expect(mockUseResultadosPorParte).toHaveBeenCalledWith(undefined);
    expect(getByTestId("certidoes-parte-row-tjsp")).toBeTruthy();
  });

  it("shows the titular empty state and vincula through useVincularCliente", async () => {
    mockUseResultadosPorCliente.mockReturnValue(queryStub({ data: [] }));
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({
        data: [{ id: "c1", nome: "Maria", documento: "111", atendimento_parte_id: null, cliente_id: null }],
      }),
    );
    const { getByTestId, fireEvent } = await renderPanel({ clienteId: "cliente-1" });
    fireEvent.click(getByTestId("certidoes-parte-empty").querySelector("button")!);
    fireEvent.change(getByTestId("mock-select"), { target: { value: "c1" } });
    fireEvent.click(getByTestId("dialog").querySelectorAll("button")[1]);
    expect(mockVincularCliente).toHaveBeenCalledWith(
      { consultaId: "c1", clienteId: "cliente-1" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(mockVincularParte).not.toHaveBeenCalled();
  });

  it("excludes a consulta already claimed by ANY linkage (parte OR cliente) from the vincular list", async () => {
    mockUseResultadosPorCliente.mockReturnValue(queryStub({ data: [] }));
    mockUseCertidaoConsultas.mockReturnValue(
      queryStub({
        data: [
          { id: "c1", nome: "Livre", documento: "000", atendimento_parte_id: null, cliente_id: null },
          { id: "c2", nome: "JaVinculadaParte", documento: "111", atendimento_parte_id: "outra-parte", cliente_id: "outra-parte-cliente" },
          { id: "c3", nome: "JaVinculadaTitular", documento: "222", atendimento_parte_id: null, cliente_id: "outro-cliente" },
        ],
      }),
    );
    const { getByTestId, getByText, queryByText, fireEvent } = await renderPanel({ clienteId: "cliente-1" });
    fireEvent.click(getByTestId("certidoes-parte-empty").querySelector("button")!);
    expect(getByText(/Livre/)).toBeTruthy();
    expect(queryByText(/JaVinculadaParte/)).toBeFalsy();
    expect(queryByText(/JaVinculadaTitular/)).toBeFalsy();
  });
});

// ─── Situação cadastral editor (migration 116, contract F6) ─────────────────

describe("CertidoesPartePanel — situação cadastral (CNPJ only)", () => {
  it("does not render the editor for a CPF consulta", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ consulta_tipo_documento: "cpf" })] }),
    );
    const { container } = await renderPanel();
    expect(container.querySelector('[data-testid^="situacao-cadastral-"]')).toBeFalsy();
  });

  it("renders one editor per unique CNPJ consulta linked to this person", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({
        data: [
          makeResultado({ id: "r1", tipo: "cnd_federal", consulta_id: "cnpj-1", consulta_tipo_documento: "cnpj" }),
          makeResultado({ id: "r2", tipo: "tjsp", consulta_id: "cnpj-1", consulta_tipo_documento: "cnpj" }),
        ],
      }),
    );
    const { container } = await renderPanel();
    // The prefix also matches this consulta's OWN badge/erro sibling
    // testids (`situacao-cadastral-badge-cnpj-1`, `-erro-cnpj-1`) — the
    // exact wrapper testid is the one that must appear exactly once.
    expect(container.querySelectorAll('[data-testid="situacao-cadastral-cnpj-1"]').length).toBe(1);
  });

  it("shows the derived badge for the current situação", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({
        data: [
          makeResultado({
            consulta_id: "cnpj-1",
            consulta_tipo_documento: "cnpj",
            consulta_situacao_cadastral: "ativa",
          }),
        ],
      }),
    );
    const { getByTestId } = await renderPanel();
    expect(getByTestId("situacao-cadastral-badge-cnpj-1").textContent).toBe("Exigida no contrato");
  });

  it("refuses to save 'baixada' without a date, client-side", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({ data: [makeResultado({ consulta_id: "cnpj-1", consulta_tipo_documento: "cnpj" })] }),
    );
    const { getByTestId, fireEvent } = await renderPanel();
    fireEvent.change(getByTestId("mock-select"), { target: { value: "baixada" } });
    fireEvent.click(getByTestId("situacao-cadastral-cnpj-1").querySelector("button")!);
    expect(getByTestId("situacao-cadastral-erro-cnpj-1")).toBeTruthy();
    expect(mockAtualizarSituacaoCadastral).not.toHaveBeenCalled();
  });

  it("saves only the changed fields through useAtualizarSituacaoCadastral", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({
        data: [
          makeResultado({
            consulta_id: "cnpj-1",
            consulta_tipo_documento: "cnpj",
            consulta_situacao_cadastral: null,
          }),
        ],
      }),
    );
    const { getByTestId, fireEvent } = await renderPanel();
    fireEvent.change(getByTestId("mock-select"), { target: { value: "ativa" } });
    fireEvent.click(getByTestId("situacao-cadastral-cnpj-1").querySelector("button")!);
    expect(mockAtualizarSituacaoCadastral).toHaveBeenCalledWith({
      consultaId: "cnpj-1",
      patch: { situacao_cadastral: "ativa" },
    });
  });
});

// ─── negativa_com_homonimos (migration 116) ─────────────────────────────────

describe("CertidoesPartePanel — negativa_com_homonimos", () => {
  it("offers the homônimos option in the edit dialog's resultado select", async () => {
    mockUseResultadosPorParte.mockReturnValue(queryStub({ data: [makeResultado()] }));
    const { getByLabelText, getByText, fireEvent } = await renderPanel();
    fireEvent.click(getByLabelText("Editar Certidão TJSP"));
    expect(getByText("Negativa c/ homônimos")).toBeTruthy();
  });

  it("renders a confirmed negativa_com_homonimos row distinctly from a clean negativa", async () => {
    mockUseResultadosPorParte.mockReturnValue(
      queryStub({
        data: [
          makeResultado({
            resultado: "negativa_com_homonimos",
            resultado_origem: "manual",
          }),
        ],
      }),
    );
    const { getByText } = await renderPanel();
    expect(getByText("Negativa c/ homônimos")).toBeTruthy();
  });
});
