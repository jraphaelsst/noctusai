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

  it("re-emitir hits the contract path", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-reemitir-c:cli-1-cnd_federal"));
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

  it("solicitar todas / selecionadas post to the emissao path", async () => {
    mockGet.mockResolvedValue(resp([parte()]));
    render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
    await screen.findByTestId("parte-secao-c:cli-1");
    open("c:cli-1");
    fireEvent.click(screen.getByTestId("parte-solicitar-todas-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/emissao", { tipos: null, atendimento_id: "at-1" }));
    fireEvent.click(screen.getByLabelText("Selecionar Receita Federal"));
    fireEvent.click(screen.getByTestId("parte-solicitar-selecionadas-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/emissao", { tipos: ["cnd_federal"], atendimento_id: "at-1" }));
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
  it("polls for processando/na_fila/api-pendente but not manual placeholders or settled", () => {
    expect(certidaoEmAndamento(cel({ status_processamento: "processando" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "na_fila" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "pendente", origem: "api" }))).toBe(true);
    expect(certidaoEmAndamento(cel({ status_processamento: "pendente", origem: "manual" }))).toBe(false);
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
