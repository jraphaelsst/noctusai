import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { CertidaoParte, CertidaoParteCelula, CertidoesPartesResponse } from "@/types/certidoesPartes";

const { mockGet, mockPost, mockUpload, mockPatch, mockDelete, mockPut, mockAntigosGet, authUser } = vi.hoisted(() => ({
  mockGet: vi.fn(), mockPost: vi.fn(), mockUpload: vi.fn(), mockPatch: vi.fn(), mockDelete: vi.fn(),
  mockPut: vi.fn(), mockAntigosGet: vi.fn(), authUser: { current: null as unknown },
}));

// The antigos header/sync/dispensa endpoints are routed apart so the existing
// partes assertions (`mockGet` called with the partes URL) stay exact.
const isAntigos = (url: string) => url.includes("/certidoes/antigos-proprietarios");
vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: authUser.current }),
  api: {
    get: (url: string, ...a: unknown[]) => (isAntigos(url) ? mockAntigosGet(url, ...a) : mockGet(url, ...a)),
    post: (url: string, ...a: unknown[]) =>
      isAntigos(url) ? mockPost(url, ...a) : mockPost(url, ...a),
    put: mockPut,
    upload: mockUpload, patch: mockPatch, delete: mockDelete,
  },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/CertidoesPartePanel", () => ({
  CertidoesPartePanel: ({ nomeParte }: { nomeParte?: string }) => <div data-testid="panel-stub">{nomeParte}</div>,
}));

import { rolarAteAlvo } from "@/hooks/useRolarAteAlvo";
import { alvoSubtabCertidoes, grupoDoAlvoCertidoes } from "../destinoDoContrato";
import { certidaoEmAndamento, partesTemEmAndamento } from "@/hooks/useCertidoesPartes";
import { CertidoesPartesTab } from "./CertidoesPartesTab";

function cel(over: Partial<CertidaoParteCelula> = {}): CertidaoParteCelula {
  return {
    status: "pendente", texto: "Pendente", tipo: "cnd_federal", resultado_id: null, consulta_id: null,
    status_processamento: null, resultado: null, numero: null, emitida_em: null, validade_ate: null,
    idade_dias: null, stale_para_contrato: false, arquivo_url: null, tem_arquivo: false, arquivo_manual: false,
    arquivo_nome: null, origem: null, confirmado: false, analise_ia: null, erro_mensagem: null, segunda_via: false, pcen: null, ...over,
  };
}
const linhas = [
  { tipo: "cnd_federal", chave: "cnd_federal", id: null, linha: "5.1", rotulo: "Receita Federal", custom: false },
  { tipo: "serasa", chave: "serasa", id: null, linha: "5.12", rotulo: "SERASA", custom: false },
];
function parte(over: Partial<CertidaoParte> = {}): CertidaoParte {
  return {
    chave: "c:cli-1", kind: "pessoa", tipo_pessoa: "PF", rotulo: "COMP 1", lado: "comprador", grupo: "comprador", papel: "comprador",
    titular: true, nome: "Maria Silva", documento: "12345678901", cliente_id: "cli-1", empresa_id: null, parte_id: null,
    totais: { nao_constam: 1, constam: 0, pendente: 1, vencidas: 1 },
    celulas: {
      cnd_federal: cel({ status: "nao_constam", resultado: "negativa", status_processamento: "sucesso", resultado_id: "res-1", emitida_em: "2026-08-01", idade_dias: 61, stale_para_contrato: true }),
      serasa: cel({ tipo: "serasa" }),
    },
    ...over,
  };
}
function resp(partes: CertidaoParte[]): CertidoesPartesResponse {
  return { atendimento_id: "at-1", data_referencia: "2026-10-01", max_dias: 30, linhas, partes };
}
function wrap({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
const open = (chave: string) => fireEvent.click(screen.getByTestId(`parte-secao-header-${chave}`));

const antigosEstado = (over: Record<string, unknown> = {}) => ({
  atendimento_id: "at-1", exigido: true, motivo: "transferencia_menos_de_5_anos", janela_anos: 5,
  ultima_transferencia: null, origem_dados: "titulo_confirmado", transmitentes: [], dispensado: null,
  sincronizacao_pendente: 0, ...over,
});
beforeEach(() => {
  mockPost.mockResolvedValue({}); mockUpload.mockResolvedValue({});
  mockAntigosGet.mockResolvedValue(antigosEstado());
  authUser.current = null;
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("CertidoesPartesTab — failed first load is an error, never a skeleton", () => {
  // 409 = the stale/missing acting-org refusal; 500 = a server fault. Both must
  // end in the error state with retry once the query settles.
  it.each([[409, "A organização selecionada mudou."], [500, "Erro interno"]])(
    "HTTP %i -> error state with retry (no skeleton)",
    async (status, message) => {
      const err = Object.assign(new Error(message), { status });
      mockGet.mockRejectedValueOnce(err);
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      expect(screen.getByTestId("certidoes-partes-skeleton")).toBeTruthy();
      await screen.findByTestId("certidoes-partes-error");
      expect(screen.queryByTestId("certidoes-partes-skeleton")).toBeNull();
      mockGet.mockResolvedValueOnce(resp([parte()]));
      fireEvent.click(screen.getByText("Tentar novamente"));
      await screen.findByTestId("parte-secao-c:cli-1");
    },
  );
});

describe("CertidoesPartesTab — certidões opcionais (owner 2026-10-21)", () => {
  const linhasFgts = [...linhas, { tipo: "fgts_regularidade", chave: "fgts_regularidade", id: null, linha: "5.13", rotulo: "Regularidade do FGTS (empresas)", custom: false }];
  const empresa = (opcional: boolean) => parte({
    chave: "e:emp-1", kind: "empresa", tipo_pessoa: "PJ", rotulo: "EMP 1", lado: null, grupo: "comprador", nome: "Acme",
    cliente_id: null, empresa_id: "emp-1", titular: false,
    celulas: { cnd_federal: cel(), serasa: cel({ tipo: "serasa", status: "na", texto: "N/A" }), fgts_regularidade: cel({ tipo: "fgts_regularidade", opcional }) },
  });

  it("shows FGTS as 'Opcional' (not 'Pendente') when the deal does not require it", async () => {
    mockGet.mockResolvedValue({ ...resp([empresa(true)]), linhas: linhasFgts, exigencias: { exigir_certidoes_antigos: false, exigir_crf_fgts: false } });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-e:emp-1");
    open("e:emp-1");
    expect(screen.getByTestId("parte-chip-e:emp-1-fgts_regularidade").textContent).toContain("Opcional");
    expect(screen.getByTestId("parte-chip-e:emp-1-cnd_federal").textContent).toContain("Pendente");
  });

  it("shows FGTS as 'Pendente' once the deal requires it", async () => {
    mockGet.mockResolvedValue({ ...resp([empresa(false)]), linhas: linhasFgts, exigencias: { exigir_certidoes_antigos: false, exigir_crf_fgts: true } });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-e:emp-1");
    open("e:emp-1");
    expect(screen.getByTestId("parte-chip-e:emp-1-fgts_regularidade").textContent).toContain("Pendente");
    expect((screen.getByTestId("exigencia-exigir_crf_fgts") as HTMLElement).getAttribute("data-state")).toBe("checked");
  });

  it("the switches PUT the deal's opt-in (CRF/FGTS and antigos)", async () => {
    mockGet.mockResolvedValue({ ...resp([parte()]), exigencias: { exigir_certidoes_antigos: false, exigir_crf_fgts: false } });
    mockPut.mockResolvedValue({ atendimento_id: "at-1", exigencias: { exigir_certidoes_antigos: false, exigir_crf_fgts: true } });
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("certidoes-exigencias");
    expect((screen.getByTestId("exigencia-exigir_certidoes_antigos") as HTMLElement).getAttribute("data-state")).toBe("unchecked");
    fireEvent.click(screen.getByTestId("exigencia-exigir_crf_fgts"));
    await waitFor(() => expect(mockPut).toHaveBeenCalledWith(
      "/api/clientes/cli-1/certidoes/exigencias", { exigir_crf_fgts: true, atendimento_id: "at-1" },
    ));
  });
});

describe("CertidoesPartesTab", () => {
  it("renders one section per party, all collapsed by default", async () => {
    mockGet.mockResolvedValue(resp([parte(), parte({ chave: "c:cli-2", rotulo: "VEND 1", lado: "vendedor", titular: false, nome: "João", parte_id: "p-2", cliente_id: "cli-2" })]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    expect(screen.getByTestId("parte-secao-c:cli-2")).toBeTruthy();
    expect(screen.getByText("Maria Silva")).toBeTruthy();
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).toContain("1/2 ok");
    expect(screen.queryByTestId("parte-linha-c:cli-1-cnd_federal")).toBeNull();
    expect(screen.getByTestId("parte-stale-flag-c:cli-1")).toBeTruthy();
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/partes", {});
  });

  it("expanding shows only that party's table, with the stale warning", async () => {
    mockGet.mockResolvedValue(resp([parte(), parte({ chave: "c:cli-2", rotulo: "VEND 1", nome: "João", cliente_id: "cli-2" })]));
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    expect(mockGet).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/partes", { atendimento_id: "at-1" });
    open("c:cli-1");
    expect(screen.getByTestId("parte-linha-c:cli-1-cnd_federal")).toBeTruthy();
    expect(screen.queryByTestId("parte-linha-c:cli-2-cnd_federal")).toBeNull();
    expect(screen.getByTestId("parte-stale-c:cli-1-cnd_federal").textContent).toContain("Emitida há 61 dias — vencida para contrato");
  });

  it("shows a failed re-emission inline while the older evidence keeps the cell (F100)", async () => {
    const p = parte();
    p.celulas.cnd_federal = cel({
      ...p.celulas.cnd_federal, emissao_automatica: true,
      ultima_tentativa: { status: "erro", erro: "A API foi pausada temporariamente", em: "2026-10-24T20:29:00Z", resultado_id: "res-2" },
    });
    mockGet.mockResolvedValue(resp([p]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    const nota = screen.getByTestId("parte-ultima-tentativa-c:cli-1-cnd_federal").textContent ?? "";
    expect(nota).toContain("Última emissão falhou: A API foi pausada temporariamente");
    expect(nota).toContain("evidência anterior mantida");
    expect(screen.getByTestId("parte-reemitir-c:cli-1-cnd_federal")).toBeTruthy();
    expect(certidaoEmAndamento(p.celulas.cnd_federal)).toBe(false);
    expect(certidaoEmAndamento({ ...p.celulas.cnd_federal, ultima_tentativa: { status: "processando", erro: null, em: null, resultado_id: "r" } })).toBe(true);
  });

  it("re-emitir hits the contract path", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-reemitir-c:cli-1-cnd_federal"));
    // Re-emitir is a paid emission too: nothing is sent until the dialog is confirmed.
    expect(mockPost).not.toHaveBeenCalled();
    expect((await screen.findByTestId("parte-confirmar-emissao-c:cli-1")).textContent).toMatch(/paga/);
    fireEvent.click(screen.getByTestId("parte-confirmar-emissao-ok-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/resultados/res-1/reemitir", {}));
  });

  describe("reler", () => {
    const comUpload = () => parte({
      celulas: {
        cnd_federal: cel({ status: "nao_constam", status_processamento: "sucesso", resultado_id: "res-1", tem_arquivo: true, arquivo_url: "k/api.pdf" }),
        serasa: cel({ tipo: "serasa", status: "nao_constam", status_processamento: "sucesso", resultado_id: "res-2", tem_arquivo: true, arquivo_manual: true, arquivo_url: "k/up.pdf" }),
      },
    });

    it("is offered on every row with a stored PDF — upload or live receipt", async () => {
      const p = comUpload();
      p.celulas.cnd_federal = { ...p.celulas.cnd_federal, pode_reler: true };
      p.celulas.serasa = { ...p.celulas.serasa, pode_reler: true };
      mockGet.mockResolvedValue(resp([p]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      expect(screen.getByTestId("parte-linha-c:cli-1-serasa-reextrair").textContent).toContain("Reler");
      expect(screen.getByTestId("parte-linha-c:cli-1-cnd_federal-reextrair").textContent).toContain("Reler");
      expect(screen.getByTestId("certidoes-partes-reextrair")).toBeTruthy();
    });

    it("falls back to the manual-upload flag on a payload without pode_reler", async () => {
      mockGet.mockResolvedValue(resp([comUpload()]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      expect(screen.getByTestId("parte-linha-c:cli-1-serasa-reextrair")).toBeTruthy();
      expect(screen.queryByTestId("parte-linha-c:cli-1-cnd_federal-reextrair")).toBeNull();
    });

    it("shows 'Relendo…' disabled while the certidão is being read, and nothing with no stored PDF", async () => {
      const lendo = comUpload();
      lendo.celulas.serasa = { ...lendo.celulas.serasa, status_processamento: "processando" };
      lendo.celulas.cnd_federal = {
        ...lendo.celulas.cnd_federal, pode_reler: true,
        releitura: { em_andamento: true, concluida_em: null, divergencias: [] },
      };
      mockGet.mockResolvedValue(resp([lendo]));
      const { unmount } = render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      for (const linha of ["serasa", "cnd_federal"]) {
        const b = screen.getByTestId(`parte-linha-c:cli-1-${linha}-reextrair`) as HTMLButtonElement;
        expect(b.textContent).toContain("Relendo…");
        expect(b.disabled).toBe(true);
      }
      // Nothing left to re-read on this party ⇒ its "Reler todas" is gone.
      expect(screen.queryByTestId("parte-reler-todas-c:cli-1")).toBeNull();
      unmount();
      mockGet.mockResolvedValue(resp([parte()]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      expect(screen.queryByTestId("certidoes-partes-reextrair")).toBeNull();
    });

    it("re-reads one certidão and refreshes every certidões query", async () => {
      mockGet.mockResolvedValue(resp([comUpload()]));
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const spy = vi.spyOn(qc, "invalidateQueries");
      render(
        <QueryClientProvider client={qc}><CertidoesPartesTab clienteId="cli-1" /></QueryClientProvider>,
      );
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-linha-c:cli-1-serasa-reextrair"));
      await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/certidoes/resultados/res-2/reler", {}));
      await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: ["sw", "clientes", "cli-1", "certidoes", "partes"] }));
      expect(spy).toHaveBeenCalledWith({ queryKey: ["certidao-resultados-parte"] });
      expect(spy).toHaveBeenCalledWith({ queryKey: ["certidao-consulta"] });
    });

    it("'Reler todas as certidões' posts the card-level re-read with the atendimento", async () => {
      mockGet.mockResolvedValue(resp([comUpload()]));
      mockPost.mockResolvedValue({ relidos: 2, sem_arquivo: 1, em_andamento: 0, erros: 0 });
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const spy = vi.spyOn(qc, "invalidateQueries");
      render(
        <QueryClientProvider client={qc}><CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" /></QueryClientProvider>,
      );
      fireEvent.click(await screen.findByTestId("certidoes-partes-reextrair"));
      await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/reler", { atendimento_id: "at-1" }));
      await waitFor(() => expect(spy).toHaveBeenCalledWith({ queryKey: ["sw", "clientes", "cli-1", "certidoes", "partes"] }));
    });

    it("'Reler todas' of one party re-reads each of its stored PDFs", async () => {
      const p = comUpload();
      p.celulas.cnd_federal = { ...p.celulas.cnd_federal, pode_reler: true };
      p.celulas.serasa = { ...p.celulas.serasa, pode_reler: true };
      mockGet.mockResolvedValue(resp([p]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-reler-todas-c:cli-1"));
      await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/certidoes/resultados/res-2/reler", {}));
      expect(mockPost).toHaveBeenCalledWith("/api/certidoes/resultados/res-1/reler", {});
    });

    it("surfaces a re-read divergence and applies the read values only on a human click", async () => {
      const p = comUpload();
      p.celulas.serasa = {
        ...p.celulas.serasa, numero: "CONFIRMADO", pode_reler: true,
        releitura: {
          em_andamento: false, concluida_em: "2026-10-03T10:00:00+00:00",
          divergencias: [{ campo: "numero", valor_atual: "CONFIRMADO", valor_lido: "0123456789" }],
        },
      };
      mockGet.mockResolvedValue(resp([p]));
      mockPatch.mockResolvedValue({ data: {} });
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      const aviso = screen.getByTestId("parte-divergencia-c:cli-1-serasa");
      expect(aviso.textContent).toContain("nada foi alterado");
      expect(aviso.textContent).toContain("Número: lido 0123456789 (atual: CONFIRMADO)");
      expect(screen.getByTestId("parte-numero-c:cli-1-serasa").textContent).toContain("CONFIRMADO");
      expect(mockPatch).not.toHaveBeenCalled();
      fireEvent.click(screen.getByTestId("parte-aplicar-lidos-c:cli-1-serasa"));
      await waitFor(() => expect(mockPatch).toHaveBeenCalledWith("/api/certidoes/resultados/res-2", { numero: "0123456789" }));
    });

    it("keeps polling while a live receipt is being re-read", () => {
      const c = cel({ status_processamento: "sucesso", releitura: { em_andamento: true, concluida_em: null, divergencias: [] } });
      expect(certidaoEmAndamento(c)).toBe(true);
      expect(certidaoEmAndamento({ ...c, releitura: { em_andamento: false, concluida_em: null, divergencias: [] } })).toBe(false);
    });
  });

  it("solicitar todas / selecionadas post to the emissao path ONLY after the paid-emission confirmation", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-solicitar-todas-c:cli-1"));
    // The dialog names the paid nature and the certidões; nothing was sent yet.
    const dlg = await screen.findByTestId("parte-confirmar-emissao-c:cli-1");
    expect(dlg.textContent).toMatch(/paga/);
    expect(screen.getByTestId("parte-confirmar-emissao-lista-c:cli-1").textContent).toContain("Receita Federal");
    expect(mockPost).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("parte-confirmar-emissao-ok-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/emissao", { tipos: null, atendimento_id: "at-1" }));
    fireEvent.click(screen.getByLabelText("Selecionar Receita Federal"));
    fireEvent.click(screen.getByTestId("parte-solicitar-selecionadas-c:cli-1"));
    fireEvent.click(await screen.findByTestId("parte-confirmar-emissao-ok-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/emissao", { tipos: ["cnd_federal"], atendimento_id: "at-1" }));
  });

  it("cancelling the paid-emission confirmation sends nothing", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-solicitar-todas-c:cli-1"));
    fireEvent.click(await screen.findByTestId("parte-confirmar-emissao-cancelar-c:cli-1"));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("upload ensures the cell then uses the existing upload route", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    mockPost.mockResolvedValue({ resultado_id: "res-9", consulta_id: "con-9", criado: true });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-upload-c:cli-1-serasa"));
    const file = new File(["x"], "a.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("parte-upload-input-c:cli-1"), { target: { files: [file] } });
    await waitFor(() => expect(mockUpload).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/celulas", { kind: "pessoa", alvo_id: "cli-1", linha_chave: "serasa", atendimento_id: null });
    expect(mockUpload.mock.calls[0][0]).toBe("/api/certidoes/resultados/res-9/upload");
  });

  describe("a refused upload / emission is drawn on the row (F86 — never a silent drop)", () => {
    it("a party WITHOUT document can still upload a PDF; a celulas refusal shows the server message on that row", async () => {
      mockGet.mockResolvedValue(resp([parte({ documento: null })]));
      mockPost.mockRejectedValueOnce(Object.assign(
        new Error("[422] Linha de certidão inválida."), { status: 422 },
      ));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      // Emission needs the CPF; the manual upload does not.
      expect((screen.getByTestId("parte-solicitar-todas-c:cli-1") as HTMLButtonElement).disabled).toBe(true);
      const enviar = screen.getByTestId("parte-upload-c:cli-1-serasa") as HTMLButtonElement;
      expect(enviar.disabled).toBe(false);
      fireEvent.click(enviar);
      const file = new File(["x"], "a.pdf", { type: "application/pdf" });
      fireEvent.change(screen.getByTestId("parte-upload-input-c:cli-1"), { target: { files: [file] } });
      const recusa = await screen.findByTestId("parte-recusa-c:cli-1-serasa");
      // The seed upload-refusal organ: the server's words AND the file name.
      expect(recusa.textContent).toBe('"a.pdf" não foi enviado: Linha de certidão inválida.');
      expect(recusa.getAttribute("role")).toBe("alert");
      expect(mockUpload).not.toHaveBeenCalled();
      // The next attempt clears it; a success leaves nothing behind.
      mockPost.mockResolvedValueOnce({ resultado_id: "res-9", consulta_id: "con-9", criado: true });
      fireEvent.click(screen.getByTestId("parte-upload-c:cli-1-serasa"));
      fireEvent.change(screen.getByTestId("parte-upload-input-c:cli-1"), { target: { files: [file] } });
      await waitFor(() => expect(mockUpload).toHaveBeenCalled());
      await waitFor(() => expect(screen.queryByTestId("parte-recusa-c:cli-1-serasa")).toBeNull());
    });

    it("an upload-route refusal is shown on the row too", async () => {
      mockGet.mockResolvedValue(resp([parte()]));
      mockPost.mockResolvedValue({ resultado_id: "res-9", consulta_id: "con-9", criado: true });
      mockUpload.mockRejectedValueOnce(new Error("[413] Arquivo grande demais."));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-upload-c:cli-1-serasa"));
      fireEvent.change(screen.getByTestId("parte-upload-input-c:cli-1"), {
        target: { files: [new File(["x"], "a.pdf", { type: "application/pdf" })] },
      });
      expect((await screen.findByTestId("parte-recusa-c:cli-1-serasa")).textContent).toBe('"a.pdf" não foi enviado: Arquivo grande demais.');
    });

    it("an emission refusal is shown on the party (todas) or on the selected rows", async () => {
      mockGet.mockResolvedValue(resp([parte()]));
      mockPost.mockRejectedValueOnce(new Error("[422] Credencial InfoSimples ausente."));
      render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-solicitar-todas-c:cli-1"));
      fireEvent.click(await screen.findByTestId("parte-confirmar-emissao-ok-c:cli-1"));
      expect((await screen.findByTestId("parte-recusa-c:cli-1")).textContent).toBe("Credencial InfoSimples ausente.");
      mockPost.mockRejectedValueOnce(new Error("[422] Receita indisponível."));
      fireEvent.click(screen.getByLabelText("Selecionar Receita Federal"));
      fireEvent.click(screen.getByTestId("parte-solicitar-selecionadas-c:cli-1"));
      fireEvent.click(await screen.findByTestId("parte-confirmar-emissao-ok-c:cli-1"));
      expect((await screen.findByTestId("parte-recusa-c:cli-1-cnd_federal")).textContent).toBe("Receita indisponível.");
    });
  });

  it("pending cell: 'Preencher manualmente' ensures the cell, PATCHes the typed values, then shows them as Digitado", async () => {
    mockGet.mockResolvedValueOnce(resp([parte()]));
    mockPost.mockResolvedValue({ resultado_id: "res-7", consulta_id: "con-7", criado: true });
    mockPatch.mockResolvedValue({ data: {} });
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    expect(screen.queryByTestId("parte-digitado-c:cli-1-serasa")).toBeNull();
    expect(screen.getByTestId("parte-digitar-c:cli-1-serasa").textContent).toContain("Preencher manualmente");
    fireEvent.click(screen.getByTestId("parte-digitar-c:cli-1-serasa"));
    fireEvent.change(await screen.findByLabelText("Número"), { target: { value: "ABC-123" } });
    fireEvent.change(screen.getByLabelText("Emitida em"), { target: { value: "2026-10-20" } });
    fireEvent.change(screen.getByLabelText("Validade até"), { target: { value: "2026-11-19" } });
    // The refetch after saving returns the cell as typed.
    mockGet.mockResolvedValue(resp([parte({
      celulas: {
        ...parte().celulas,
        serasa: cel({ tipo: "serasa", status: "nao_constam", resultado: "negativa", resultado_id: "res-7", numero: "ABC-123", emitida_em: "2026-10-20", validade_ate: "2026-11-19", origem: "manual", confirmado: true }),
      },
    })]));
    fireEvent.click(screen.getByText("Confirmar"));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith("/api/certidoes/resultados/res-7", { numero: "ABC-123", emitida_em: "2026-10-20", validade_ate: "2026-11-19" }));
    expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/celulas", { kind: "pessoa", alvo_id: "cli-1", linha_chave: "serasa", atendimento_id: "at-1" });
    await screen.findByTestId("parte-digitado-c:cli-1-serasa");
    expect(screen.getByTestId("parte-numero-c:cli-1-serasa").textContent).toContain("ABC-123");
  });

  it("filled cell exposes 'Editar' and PATCHes its existing resultado without ensuring a new cell", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    mockPatch.mockResolvedValue({ data: {} });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    const btn = screen.getByTestId("parte-digitar-c:cli-1-cnd_federal");
    expect(btn.textContent).toContain("Editar");
    fireEvent.click(btn);
    fireEvent.change(await screen.findByLabelText("Número"), { target: { value: "N-1" } });
    fireEvent.click(screen.getByText("Confirmar"));
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith("/api/certidoes/resultados/res-1", { numero: "N-1" }));
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("adicionar certidão posts to the custom-row route", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-adicionar-c:cli-1"));
    fireEvent.change(screen.getByTestId("certidoes-partes-novo-nome-input"), { target: { value: "Municipal" } });
    fireEvent.click(screen.getByTestId("certidoes-partes-adicionar-confirmar"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/matriz/linhas", { nome: "Municipal" }));
  });

  it("explains a 2ª via: the original emission date, in the row and in the chip tooltip", async () => {
    const segunda = parte({
      celulas: {
        cnd_federal: cel({
          status: "nao_constam", resultado: "negativa", status_processamento: "sucesso",
          resultado_id: "res-1", emitida_em: "2026-07-01", idade_dias: 92,
          stale_para_contrato: true, segunda_via: true,
        }),
        serasa: cel({ tipo: "serasa" }),
      },
    });
    mockGet.mockResolvedValue(resp([segunda, parte({ chave: "c:cli-2", cliente_id: "cli-2", titular: false, rotulo: "COMP 2" })]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    expect(screen.getByTestId("parte-segunda-via-c:cli-1-cnd_federal").textContent).toBe(
      "2ª via — data de emissão original",
    );
    // A normal emission carries no such note.
    open("c:cli-2");
    expect(screen.queryByTestId("parte-segunda-via-c:cli-2-cnd_federal")).toBeNull();
  });

  it("shows a missing GOV.BR login as PENDING with the reason, keeps manual upload, hides re-emit", async () => {
    const msg = "Requer login GOV.BR do escritório — configure em Configurações ou envie o PDF manualmente";
    const base = resp([parte({
      celulas: {
        cnd_federal: cel({}),
        divida_ativa_sp: cel({
          tipo: "divida_ativa_sp", status: "pendente", status_processamento: "pendente",
          resultado_id: "res-da", erro_mensagem: msg, pendencia: "credencial_govbr",
        }),
      },
    })]);
    mockGet.mockResolvedValue({
      ...base,
      linhas: [...linhas, { tipo: "divida_ativa_sp", chave: "divida_ativa_sp", id: null, linha: "5.12", rotulo: "Dívida ativa", custom: false }],
    });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    const linha = screen.getByTestId("parte-linha-c:cli-1-divida_ativa_sp");
    expect(screen.getByTestId("parte-pendencia-c:cli-1-divida_ativa_sp").textContent).toBe(msg);
    expect(screen.getByTestId("parte-chip-c:cli-1-divida_ativa_sp").textContent).toContain("Pendente");
    expect(linha.textContent).not.toContain("Erro");
    expect(screen.getByTestId("parte-upload-c:cli-1-divida_ativa_sp")).toBeTruthy();
    expect(screen.queryByTestId("parte-reemitir-c:cli-1-divida_ativa_sp")).toBeNull();
  });

  describe("Receita PCEN 2ª via — acknowledgment (owner 2026-10-01)", () => {
    const pcen = (over: Record<string, unknown> = {}) => ({
      titulo: "Certidão da Receita Federal: positiva com efeitos de negativa",
      mensagem: "Receita: certidão positiva com efeitos de negativa — 2ª via emitida em 01/08/2026, válida até 30/11/2026 (a PGFN não emite nova enquanto esta for válida)",
      explicacao: ["Primeiro parágrafo.", "A PGFN não consegue emitir uma certidão nova."],
      validade_ate: "2026-11-30", vencida: false, ciente: false, ciente_em: null, duvida_em: null,
      acoes: { entendi: "Entendi — seguir com esta certidão", duvida: "Tenho dúvida — falar com o suporte" },
      ...over,
    });
    const comPcen = (p = pcen()) => parte({
      celulas: {
        cnd_federal: cel({
          status: "constam", resultado: "positiva_com_efeito_de_negativa", status_processamento: "sucesso",
          resultado_id: "res-9", emitida_em: "2026-08-01", idade_dias: 61, validade_ate: "2026-11-30",
          stale_para_contrato: false, segunda_via: true, pcen: p,
        }),
        serasa: cel({ tipo: "serasa" }),
      },
    });

    it("shows the educational block, the validity note and no 'vencida' warning while valid", async () => {
      mockGet.mockResolvedValue(resp([comPcen()]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      expect(screen.getByTestId("parte-pcen-c:cli-1-cnd_federal")).toBeTruthy();
      expect(screen.getByText("A PGFN não consegue emitir uma certidão nova.")).toBeTruthy();
      expect(screen.getByTestId("parte-segunda-via-c:cli-1-cnd_federal").textContent).toContain("válida até 30/11/2026");
      expect(screen.queryByTestId("parte-stale-c:cli-1-cnd_federal")).toBeNull();
    });

    it("'Entendi' posts the acknowledgment", async () => {
      mockGet.mockResolvedValue(resp([comPcen()]));
      mockPost.mockResolvedValue({ resultado_id: "res-9", acao: "entendi", pcen: pcen({ ciente: true }), suporte: null });
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-pcen-c:cli-1-cnd_federal-entendi"));
      await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
        "/api/clientes/cli-1/certidoes/resultados/res-9/ciencia-pcen", { acao: "entendi" },
      ));
    });

    it("'Tenho dúvida' records it and offers the configured WhatsApp — never a dead button", async () => {
      mockGet.mockResolvedValue(resp([comPcen()]));
      mockPost.mockResolvedValue({
        resultado_id: "res-9", acao: "duvida", pcen: pcen(),
        suporte: { nome: "Escritório", email: null, whatsapp: "5511999990000" },
      });
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-pcen-c:cli-1-cnd_federal-duvida"));
      const box = await screen.findByTestId("parte-pcen-c:cli-1-cnd_federal-suporte");
      const link = box.querySelector("a") as HTMLAnchorElement;
      expect(link.href).toContain("https://wa.me/5511999990000?text=");
      expect(mockPost).toHaveBeenCalledWith(
        "/api/clientes/cli-1/certidoes/resultados/res-9/ciencia-pcen", { acao: "duvida" },
      );
    });

    it("with no support contact configured it says so instead of linking nowhere", async () => {
      mockGet.mockResolvedValue(resp([comPcen()]));
      mockPost.mockResolvedValue({ resultado_id: "res-9", acao: "duvida", pcen: pcen(), suporte: null });
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      fireEvent.click(screen.getByTestId("parte-pcen-c:cli-1-cnd_federal-duvida"));
      await screen.findByTestId("parte-pcen-c:cli-1-cnd_federal-sem-contato");
    });

    it("an acknowledged certidão shows the registered ciência and no buttons", async () => {
      mockGet.mockResolvedValue(resp([comPcen(pcen({ ciente: true }))]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      expect(screen.getByTestId("parte-pcen-c:cli-1-cnd_federal-ciente")).toBeTruthy();
      expect(screen.queryByTestId("parte-pcen-c:cli-1-cnd_federal-entendi")).toBeNull();
    });

    it("an expired printed validity reads as vencida by validity, with no acknowledgment offered", async () => {
      const vencida = parte({
        celulas: {
          cnd_federal: cel({
            status: "constam", resultado: "positiva_com_efeito_de_negativa", status_processamento: "sucesso",
            resultado_id: "res-9", emitida_em: "2026-08-01", idade_dias: 61, validade_ate: "2026-09-01",
            stale_para_contrato: true, segunda_via: true, pcen: pcen({ vencida: true, validade_ate: "2026-09-01" }),
          }),
          serasa: cel({ tipo: "serasa" }),
        },
      });
      mockGet.mockResolvedValue(resp([vencida]));
      render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
      await screen.findByTestId("parte-secao-c:cli-1");
      open("c:cli-1");
      expect(screen.getByTestId("parte-stale-c:cli-1-cnd_federal").textContent).toContain("Validade impressa venceu em 01/09/2026");
      expect(screen.queryByTestId("parte-pcen-c:cli-1-cnd_federal")).toBeNull();
    });
  });

  it("shows skeleton, empty and error states", async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { unmount } = render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    expect(screen.getByTestId("certidoes-partes-skeleton")).toBeTruthy();
    unmount();
    mockGet.mockResolvedValue({ ...resp([]), atendimento_id: null });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("certidoes-partes-empty");
    cleanup();
    mockGet.mockRejectedValue(new Error("boom"));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("certidoes-partes-error");
  });
});

describe("polling predicate", () => {
  it("polls for processando/na_fila/api-pendente but not aguarda_humano placeholders or settled", () => {
    expect(certidaoEmAndamento(cel({ status_processamento: "processando" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "na_fila" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "pendente", origem: "api" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "pendente", aguarda_humano: true }))).toBe(false);
    // `origem` is who produced the VALUES — never the polling signal (F57).
    expect(certidaoEmAndamento(cel({ status_processamento: "pendente", origem: "manual" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "sucesso" }))).toBe(false);
    expect(partesTemEmAndamento(resp([parte()]))).toBe(false);
  });
});

describe("subtabs by grupo + antigos proprietários", () => {
  const comp = () => parte();
  const vend = () => parte({ chave: "c:cli-2", rotulo: "VEND 1", lado: "vendedor", grupo: "vendedor", papel: "vendedor", nome: "João Vendedor", cliente_id: "cli-2", parte_id: "p-2" });
  // Label deliberately lies about the group: grouping must read `grupo`, never `rotulo`/`papel`.
  const ant = () => parte({ chave: "c:cli-3", rotulo: "VEND 9", lado: "vendedor", grupo: "antigo_proprietario", papel: "antigo_proprietario", nome: "Zé Antigo", cliente_id: "cli-3", parte_id: "p-3" });
  const mountAll = () => {
    mockGet.mockResolvedValue(resp([comp(), vend(), ant()]));
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
  };
  const trocar = (grupo: string) => {
    const el = screen.getByTestId(`certidoes-subtab-${grupo}`);
    fireEvent.mouseDown(el, { button: 0 });
    fireEvent.focus(el);
  };

  it("splits rows by the explicit grupo (not label/papel)", async () => {
    mountAll();
    await screen.findByTestId("parte-secao-c:cli-1");
    expect(screen.queryByTestId("parte-secao-c:cli-2")).toBeNull();
    expect(screen.queryByTestId("parte-secao-c:cli-3")).toBeNull();
    trocar("vendedor");
    await screen.findByTestId("parte-secao-c:cli-2");
    expect(screen.queryByTestId("parte-secao-c:cli-3")).toBeNull();
    trocar("antigo_proprietario");
    await screen.findByTestId("parte-secao-c:cli-3");
    expect(screen.queryByTestId("parte-secao-c:cli-2")).toBeNull();
  });

  it("deep link: alvo certidoes-subtab-<grupo> selects the subtab through rolarAteAlvo", async () => {
    mountAll();
    await screen.findByTestId("parte-secao-c:cli-1");
    expect(grupoDoAlvoCertidoes("certidoes-subtab-antigo_proprietario")).toBe("antigo_proprietario");
    expect(grupoDoAlvoCertidoes("certidoes-subtab-inexistente")).toBeNull();
    rolarAteAlvo(alvoSubtabCertidoes("antigo_proprietario"));
    await screen.findByTestId("parte-secao-c:cli-3");
    expect(screen.getByTestId("certidoes-subtab-antigo_proprietario").getAttribute("data-state")).toBe("active");
  });

  it("opening the antigos subtab syncs from the matrícula and shows refused emissions", async () => {
    mockPost.mockResolvedValue({
      atendimento_id: "at-1", criados: [{ parte_id: "p-3", nome: "Zé Antigo", tipo_pessoa: "PF" }], ja_no_card: [],
      emissoes: [{ parte_id: "p-3", status: "nao_iniciada", codigo: "DOCUMENTO_AUSENTE", consulta_id: null }], ignorado: null,
    });
    mockAntigosGet.mockResolvedValue(antigosEstado({
      transmitentes: [{ nome: "Zé Antigo", documento_mascarado: "***.982.247-**", tipo_pessoa: "PF", ja_no_card: false }],
      sincronizacao_pendente: 1,
    }));
    mountAll();
    await screen.findByTestId("parte-secao-c:cli-1");
    expect(mockPost).not.toHaveBeenCalledWith(expect.stringContaining("sincronizar"), expect.anything());
    trocar("antigo_proprietario");
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/antigos-proprietarios/sincronizar", { atendimento_id: "at-1" }));
    const aviso = await screen.findByTestId("antigos-emissoes-problema");
    expect(aviso.textContent).toContain("Zé Antigo");
    expect(aviso.textContent).toContain("documento (CPF/CNPJ) ausente");
    expect((await screen.findByTestId("antigos-transmitentes")).textContent).toContain("***.982.247-**");
    expect(screen.getByTestId("antigos-pendentes").textContent).toContain("1 transmitente");
  });

  it("shows the not-required empty state and no remove for non-antigo rows", async () => {
    mockAntigosGet.mockResolvedValue(antigosEstado({ exigido: false, motivo: "transferencia_5_anos_ou_mais" }));
    mockGet.mockResolvedValue(resp([comp()]));
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    trocar("antigo_proprietario");
    expect((await screen.findByTestId("antigos-nao-exigido")).textContent).toContain("5 anos");
    await screen.findByTestId("certidoes-subtab-vazio-antigo_proprietario");
  });

  it("removes an antigo row via DELETE and hides the control on non-antigo rows", async () => {
    mockDelete.mockResolvedValue(null);
    mountAll();
    await screen.findByTestId("parte-secao-c:cli-1");
    trocar("antigo_proprietario");
    fireEvent.click(await screen.findByTestId("antigo-remover-c:cli-3"));
    fireEvent.click(await screen.findByTestId("antigo-remover-confirmar"));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/antigos-proprietarios/p-3?atendimento_id=at-1"));
  });

  it("hides Dispensar from non-admins", async () => {
    mountAll();
    await screen.findByTestId("parte-secao-c:cli-1");
    trocar("antigo_proprietario");
    await screen.findByTestId("antigos-header");
    expect(screen.queryByTestId("antigos-dispensar")).toBeNull();
  });

  it("admin dispense: validates motivo length and renders a 403 as permission denied", async () => {
    authUser.current = { user_metadata: { org_role: "admin" } };
    mockPut.mockRejectedValue(Object.assign(new Error("[403] forbidden"), { status: 403 }));
    mountAll();
    await screen.findByTestId("parte-secao-c:cli-1");
    trocar("antigo_proprietario");
    fireEvent.click(await screen.findByTestId("antigos-dispensar"));
    const confirmar = await screen.findByTestId("antigos-dispensar-confirmar");
    fireEvent.change(screen.getByTestId("antigos-motivo-input"), { target: { value: "ab" } });
    expect((confirmar as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("antigos-motivo-input"), { target: { value: "Vendedor já era o proprietário" } });
    fireEvent.click(confirmar);
    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/antigos-proprietarios/dispensa",
        { motivo: "Vendedor já era o proprietário", atendimento_id: "at-1" }));
    expect((await screen.findByTestId("antigos-dispensa-403")).textContent).toContain("Sem permissão");
  });
});

describe("certidões: célula manual, releitura honesta, data inferida", () => {
  it("Editar writes the saved row into the grid at once — no waiting for the refetch (owner: row kept '—')", async () => {
    mockGet.mockResolvedValueOnce(resp([parte()]));
    mockPost.mockResolvedValue({ resultado_id: "res-7", consulta_id: "con-7", criado: true });
    // The server's answer for the typed (complete) cell.
    mockPatch.mockResolvedValue({
      id: "res-7", status: "sucesso", resultado: "negativa", numero: "ABC-123",
      emitida_em: "2026-10-20", resultado_origem: "manual", confirmado_em: "2026-10-22T00:00:00Z",
    });
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).toContain("1 pendente");
    fireEvent.click(screen.getByTestId("parte-digitar-c:cli-1-serasa"));
    fireEvent.change(await screen.findByLabelText("Número"), { target: { value: "ABC-123" } });
    fireEvent.change(screen.getByLabelText("Emitida em"), { target: { value: "2026-10-20" } });
    // The settle refetch NEVER lands here: whatever shows is the cache write.
    mockGet.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByText("Confirmar"));
    await waitFor(() => expect(screen.getByTestId("parte-numero-c:cli-1-serasa").textContent).toContain("ABC-123"));
    expect(screen.getByTestId("parte-chip-c:cli-1-serasa").textContent).toContain("Negativa");
    // A complete typed cell is done: no longer counted as a pendência.
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).toContain("2/2 ok");
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).not.toContain("pendente");
  });

  it("'Voltar à leitura automática' only on hand-edited cells; it POSTs and shows the cell as re-reading", async () => {
    const manual = cel({
      status: "nao_constam", resultado: "negativa", status_processamento: "sucesso", resultado_id: "res-1",
      numero: "N-1", emitida_em: "2026-10-20", origem: "manual", confirmado: true,
    });
    mockGet.mockResolvedValueOnce(resp([parte({
      totais: { nao_constam: 1, constam: 0, pendente: 1, vencidas: 0 },
      celulas: { cnd_federal: manual, serasa: cel({ tipo: "serasa" }) },
    })]));
    mockPost.mockResolvedValue({
      id: "res-1", status: "processando", resultado: null, numero: null, emitida_em: null,
      resultado_origem: null, confirmado_em: null, releitura: { estado: "em_andamento", divergencias: [] },
    });
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    expect(screen.queryByTestId("parte-voltar-automatico-c:cli-1-serasa")).toBeNull();
    mockGet.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByTestId("parte-voltar-automatico-c:cli-1-cnd_federal"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/certidoes/resultados/res-1/voltar-automatico", {}));
    await waitFor(() => expect(screen.getByTestId("parte-chip-c:cli-1-cnd_federal").textContent).toContain("Processando"));
    expect(screen.queryByTestId("parte-voltar-automatico-c:cli-1-cnd_federal")).toBeNull();
    expect(screen.queryByTestId("parte-digitado-c:cli-1-cnd_federal")).toBeNull();
  });

  it("a cell being re-read is counted as 'relendo', never as pendente, with a progress bar", async () => {
    const lendo = (id: string, over: Partial<CertidaoParteCelula> = {}) =>
      cel({ status_processamento: "processando", resultado_id: id, ...over });
    mockGet.mockResolvedValue(resp([parte({
      totais: { nao_constam: 0, constam: 0, pendente: 0, processando: 2, relendo: 0, vencidas: 0 },
      celulas: { cnd_federal: lendo("a"), serasa: lendo("b", { tipo: "serasa" }) },
    })]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    const resumo = screen.getByTestId("parte-resumo-c:cli-1").textContent ?? "";
    expect(resumo).toContain("relendo 2/2");
    expect(resumo).not.toContain("pendente");
    expect(screen.getByTestId("parte-relendo-progresso-c:cli-1")).toBeTruthy();
  });

  it("a RE-read keeps the previous value visible", async () => {
    mockGet.mockResolvedValue(resp([parte({
      totais: { nao_constam: 1, constam: 0, pendente: 0, processando: 0, relendo: 1, vencidas: 0 },
      celulas: {
        cnd_federal: cel({
          status: "nao_constam", resultado: "negativa", status_processamento: "processando",
          resultado_id: "a", numero: "N-9", emitida_em: "2026-10-01",
        }),
        serasa: cel({ tipo: "serasa", status: "na", texto: "N/A" }),
      },
    })]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    expect(screen.getByTestId("parte-numero-c:cli-1-cnd_federal").textContent).toContain("N-9");
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).toContain("1/1 ok · relendo 1/1");
  });

  it("flags a date inferred from the PDF metadata so it never reads as a printed one", async () => {
    mockGet.mockResolvedValue(resp([parte({
      celulas: {
        cnd_federal: cel({ status: "nao_constam", resultado: "negativa", status_processamento: "sucesso", resultado_id: "a", emitida_em: "2026-02-10", emitida_em_origem: "metadados_pdf" }),
        serasa: cel({ tipo: "serasa" }),
      },
    })]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    expect(screen.getByTestId("parte-data-inferida-c:cli-1-cnd_federal").textContent).toContain("metadados do PDF");
    expect(screen.queryByTestId("parte-data-inferida-c:cli-1-serasa")).toBeNull();
  });
});
