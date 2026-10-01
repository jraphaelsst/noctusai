import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { CertidaoParte, CertidaoParteCelula, CertidoesPartesResponse } from "@/types/certidoesPartes";

const { mockGet, mockPost, mockUpload, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(), mockPost: vi.fn(), mockUpload: vi.fn(), mockPatch: vi.fn(), mockDelete: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, upload: mockUpload, patch: mockPatch, delete: mockDelete },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/CertidoesPartePanel", () => ({
  CertidoesPartePanel: ({ nomeParte }: { nomeParte?: string }) => <div data-testid="panel-stub">{nomeParte}</div>,
}));

import { certidaoEmAndamento, partesTemEmAndamento } from "@/hooks/useCertidoesPartes";
import { CertidoesPartesTab } from "./CertidoesPartesTab";

function cel(over: Partial<CertidaoParteCelula> = {}): CertidaoParteCelula {
  return {
    status: "pendente", texto: "Pendente", tipo: "cnd_federal", resultado_id: null, consulta_id: null,
    status_processamento: null, resultado: null, numero: null, emitida_em: null, validade_ate: null,
    idade_dias: null, stale_para_contrato: false, arquivo_url: null, tem_arquivo: false,
    arquivo_nome: null, origem: null, confirmado: false, analise_ia: null, erro_mensagem: null, segunda_via: false, ...over,
  };
}
const linhas = [
  { tipo: "cnd_federal", chave: "cnd_federal", id: null, linha: "5.1", rotulo: "Receita Federal", custom: false },
  { tipo: "serasa", chave: "serasa", id: null, linha: "5.12", rotulo: "SERASA", custom: false },
];
function parte(over: Partial<CertidaoParte> = {}): CertidaoParte {
  return {
    chave: "c:cli-1", kind: "pessoa", tipo_pessoa: "PF", rotulo: "COMP 1", lado: "comprador", papel: "comprador",
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

beforeEach(() => { mockPost.mockResolvedValue({}); mockUpload.mockResolvedValue({}); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

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

  it("shows skeleton, empty and error states", async () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    const { unmount } = render(<CertidoesPartesTab clienteId="cli-1" />, { wrapper: wrap });
    expect(screen.getByTestId("certidoes-partes-skeleton")).toBeTruthy();
    unmount();
    mockGet.mockResolvedValue(resp([]));
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
