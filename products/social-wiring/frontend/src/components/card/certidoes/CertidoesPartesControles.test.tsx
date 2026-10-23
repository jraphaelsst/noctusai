/**
 * The card tab owns every emission control (the standalone /certidoes screen is
 * retired): discard a wrong emission, cancel one in flight, retry only the
 * failed cells, inline errors + per-party error count, "Negativa c/ homônimos",
 * per-row / zip download, x/total progress, and F57 (an empty manual
 * placeholder offers no "Voltar à leitura automática").
 */
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { CertidaoParte, CertidaoParteCelula, CertidoesPartesResponse } from "@/types/certidoesPartes";

const { mockGet, mockPost, mockDelete, mockMint, mockFetch, mockDownload } = vi.hoisted(() => ({
  mockGet: vi.fn(), mockPost: vi.fn(), mockDelete: vi.fn(), mockMint: vi.fn(),
  mockFetch: vi.fn(), mockDownload: vi.fn(),
}));

vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: () => ({ user: null }),
  api: {
    get: (url: string, ...a: unknown[]) =>
      url.includes("/antigos-proprietarios") ? Promise.resolve({ transmitentes: [], exigido: false }) : mockGet(url, ...a),
    post: mockPost, put: vi.fn(), upload: vi.fn(), patch: vi.fn(), delete: mockDelete,
  },
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/CertidoesPartePanel", () => ({ CertidoesPartePanel: () => null }));
vi.mock("@/hooks/useCertidoes", () => ({
  useMintResultadoUrl: () => ({ mutate: mockMint, isPending: false }),
}));
vi.mock("@/lib/file-download", () => ({ authenticatedFetch: mockFetch, triggerBlobDownload: mockDownload }));

import { certidaoEmAndamento } from "@/hooks/useCertidoesPartes";
import { CertidoesPartesTab } from "./CertidoesPartesTab";
import {
  chipDaCelula,
  jaVigenteOuEmEmissao,
  podeCancelarEmissao,
  podeDescartarEmissao,
  podeReemitirComErro,
  podeVoltarAoAutomatico,
  progressoDaParte,
  resumoDaParte,
} from "./certidoesCelula";

function cel(over: Partial<CertidaoParteCelula> = {}): CertidaoParteCelula {
  return {
    status: "pendente", texto: "Pendente", tipo: "cnd_federal", resultado_id: null, consulta_id: null,
    status_processamento: null, resultado: null, numero: null, emitida_em: null, validade_ate: null,
    idade_dias: null, stale_para_contrato: false, arquivo_url: null, tem_arquivo: false, arquivo_manual: false,
    arquivo_nome: null, origem: null, confirmado: false, analise_ia: null, erro_mensagem: null,
    segunda_via: false, pcen: null, aguarda_humano: false, emissao_automatica: false, ...over,
  };
}
const linhas = [
  { tipo: "cnd_federal", chave: "cnd_federal", id: null, linha: "5.1", rotulo: "Receita Federal", custom: false },
  { tipo: "trf3", chave: "trf3", id: null, linha: "5.2", rotulo: "TRF3", custom: false },
  { tipo: "serasa", chave: "serasa", id: null, linha: "5.12", rotulo: "SERASA", custom: false },
];
const emVoo = (id: string, tipo = "cnd_federal") =>
  cel({ tipo, resultado_id: id, status_processamento: "processando", emissao_automatica: true });
const comErro = (id: string, tipo = "cnd_federal") =>
  cel({ tipo, resultado_id: id, status_processamento: "erro", erro_mensagem: "InfoSimples fora do ar", emissao_automatica: true });
const ok = (id: string, tipo = "cnd_federal", over: Partial<CertidaoParteCelula> = {}) =>
  cel({
    tipo, resultado_id: id, status: "nao_constam", resultado: "negativa", status_processamento: "sucesso",
    emitida_em: "2026-10-20", emissao_automatica: true, ...over,
  });

function parte(celulas: Record<string, CertidaoParteCelula>, totais: Partial<CertidaoParte["totais"]> = {}): CertidaoParte {
  return {
    chave: "c:cli-1", kind: "pessoa", tipo_pessoa: "PF", rotulo: "COMP 1", lado: "comprador", grupo: "comprador",
    papel: "comprador", titular: true, nome: "Maria Silva", documento: "12345678901", cliente_id: "cli-1",
    empresa_id: null, parte_id: null,
    totais: { nao_constam: 0, constam: 0, pendente: 0, vencidas: 0, ...totais }, celulas,
  };
}
const resp = (p: CertidaoParte): CertidoesPartesResponse => ({
  atendimento_id: "at-1", data_referencia: "2026-10-23", max_dias: 30, linhas, partes: [p],
});
function wrap({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
const abrir = async () => {
  render(<CertidoesPartesTab clienteId="cli-1" atendimentoId="at-1" />, { wrapper: wrap });
  fireEvent.click(await screen.findByTestId("parte-secao-header-c:cli-1"));
};

beforeEach(() => { mockPost.mockResolvedValue({}); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("helpers", () => {
  it("homônimos: the chip does not collapse into a plain Negativa", () => {
    expect(chipDaCelula(cel({ resultado: "negativa_com_homonimos" }))).toEqual({
      rotulo: "Negativa c/ homônimos", tom: "ok",
    });
    expect(chipDaCelula(cel({ resultado: "negativa" })).rotulo).toBe("Negativa");
  });

  it("cancel only an automatic emission running; discard any finished automatic one", () => {
    expect(podeCancelarEmissao(emVoo("a"))).toBe(true);
    expect(podeCancelarEmissao({ ...emVoo("a"), emissao_automatica: false })).toBe(false); // manual upload being read
    expect(podeCancelarEmissao(ok("a"))).toBe(false);
    expect(podeDescartarEmissao(ok("a"))).toBe(true);
    expect(podeDescartarEmissao(comErro("a"))).toBe(true);
    expect(podeDescartarEmissao(emVoo("a"))).toBe(false);
    expect(podeDescartarEmissao({ ...ok("a"), emissao_automatica: false })).toBe(false);
  });

  it("retry only a failed automatic cell — not a credential pendência, not a manual one", () => {
    expect(podeReemitirComErro(comErro("a"))).toBe(true);
    expect(podeReemitirComErro({ ...comErro("a"), pendencia: "credencial_govbr" })).toBe(false);
    expect(podeReemitirComErro({ ...comErro("a"), emissao_automatica: false })).toBe(false);
    expect(podeReemitirComErro(ok("a"))).toBe(false);
  });

  it("'emitir todas' skips cells valid in date or in emission", () => {
    expect(jaVigenteOuEmEmissao(ok("a"))).toBe(true);
    expect(jaVigenteOuEmEmissao(ok("a", "cnd_federal", { stale_para_contrato: true }))).toBe(false);
    expect(jaVigenteOuEmEmissao(emVoo("a"))).toBe(true);
    expect(jaVigenteOuEmEmissao(comErro("a"))).toBe(false);
    expect(jaVigenteOuEmEmissao(cel())).toBe(false);
  });

  it("summary counts the failed cells; progress is x of total only while something is being read", () => {
    const p = parte({}, { nao_constam: 2, pendente: 3, erros: 2, processando: 1, relendo: 0 });
    expect(resumoDaParte(p)).toContain("2 com erro");
    expect(progressoDaParte(p)).toEqual({ feitas: 5, total: 6 });
    expect(progressoDaParte(parte({}, { nao_constam: 2 }))).toBeNull();
  });

  it("F57: the poll stops on aguarda_humano; origem alone neither polls nor offers Voltar on an empty placeholder", () => {
    const vazio = cel({ resultado_id: "p", status_processamento: "pendente", aguarda_humano: true, origem: null });
    expect(certidaoEmAndamento(vazio)).toBe(false);
    expect(podeVoltarAoAutomatico(vazio)).toBe(false);
    expect(podeVoltarAoAutomatico(cel({ resultado_id: "p", status: "nao_constam", origem: "manual", confirmado: true }))).toBe(true);
  });
});

describe("card tab — emission controls", () => {
  it("shows the error text inline (not tooltip-only) and the per-party error count", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: comErro("a"), trf3: comErro("b", "trf3"), serasa: cel({ tipo: "serasa" }) },
      { pendente: 3, erros: 2 },
    )));
    await abrir();
    expect(screen.getByTestId("parte-erro-c:cli-1-cnd_federal").textContent).toContain("InfoSimples fora do ar");
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).toContain("2 com erro");
  });

  it("shows x/total progress while something is being emitted", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: ok("a"), trf3: emVoo("b", "trf3"), serasa: cel({ tipo: "serasa", status: "na" }) },
      { nao_constam: 1, processando: 1 },
    )));
    await abrir();
    expect(screen.getByTestId("parte-progresso-texto-c:cli-1").textContent).toBe("1/2");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
  });

  it("discard: confirm in pt-BR, DELETE, and the previous evidence wins in the grid at once", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: ok("bad", "cnd_federal", { resultado: "positiva", status: "constam" }), trf3: cel({ tipo: "trf3" }), serasa: cel({ tipo: "serasa" }) },
      { constam: 1, pendente: 2 },
    )));
    const depois = parte(
      { cnd_federal: ok("old", "cnd_federal", { emitida_em: "2026-10-10" }), trf3: cel({ tipo: "trf3" }), serasa: cel({ tipo: "serasa" }) },
      { nao_constam: 1, pendente: 2 },
    );
    mockDelete.mockResolvedValue({ resultado_id: "bad", parte: depois });
    await abrir();
    fireEvent.click(screen.getByTestId("parte-descartar-c:cli-1-cnd_federal"));
    expect((await screen.findByTestId("parte-confirmar-descarte-c:cli-1")).textContent).toContain("Descartar esta emissão?");
    expect(mockDelete).not.toHaveBeenCalled();
    mockGet.mockReturnValue(new Promise(() => {})); // the settle refetch never answers: the write alone must show it
    fireEvent.click(screen.getByTestId("parte-confirmar-descarte-ok-c:cli-1"));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/resultados/bad"));
    await waitFor(() => expect(screen.getByTestId("parte-chip-c:cli-1-cnd_federal").textContent).toContain("Negativa"));
  });

  it("cancel: only on automatic in-flight cells; one cell and the whole party", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: emVoo("a"), trf3: { ...emVoo("m", "trf3"), emissao_automatica: false }, serasa: emVoo("c", "serasa") },
      { processando: 3 },
    )));
    mockPost.mockResolvedValue({
      cancelados: 1,
      parte: parte({ cnd_federal: comErro("a"), trf3: { ...emVoo("m", "trf3"), emissao_automatica: false }, serasa: emVoo("c", "serasa") }, { erros: 1, processando: 2 }),
    });
    await abrir();
    expect(screen.queryByTestId("parte-cancelar-c:cli-1-trf3")).toBeNull(); // a manual cell is never cancelled
    mockGet.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByTestId("parte-cancelar-c:cli-1-cnd_federal"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/clientes/cli-1/certidoes/resultados/a/cancelar", {}));
    await waitFor(() => expect(screen.getByTestId("parte-chip-c:cli-1-cnd_federal").textContent).toContain("Erro"));
    // party-level button (counts only the cancellable cell)
    fireEvent.click(screen.getByTestId("parte-cancelar-todas-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      "/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/cancelar", { atendimento_id: "at-1" },
    ));
  });

  it("'Reemitir com erro' lists only the failed cells, confirms the cost, and writes the retried party", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: comErro("a"), trf3: ok("b", "trf3"), serasa: cel({ tipo: "serasa" }) },
      { nao_constam: 1, pendente: 2, erros: 1 },
    )));
    mockPost.mockResolvedValue({
      reemitidos: 1,
      parte: parte({
        cnd_federal: cel({ resultado_id: "a", status_processamento: "pendente", emissao_automatica: true }),
        trf3: ok("b", "trf3"), serasa: cel({ tipo: "serasa" }),
      }, { nao_constam: 1, pendente: 2 }),
    });
    await abrir();
    fireEvent.click(screen.getByTestId("parte-reemitir-erros-c:cli-1"));
    const lista = await screen.findByTestId("parte-confirmar-emissao-lista-c:cli-1");
    expect(lista.textContent).toContain("Receita Federal");
    expect(lista.textContent).not.toContain("TRF3");
    expect(mockPost).not.toHaveBeenCalled();
    mockGet.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByTestId("parte-confirmar-emissao-ok-c:cli-1"));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith(
      "/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/reemitir-erros", { atendimento_id: "at-1" },
    ));
    await waitFor(() => expect(screen.queryByTestId("parte-erro-c:cli-1-cnd_federal")).toBeNull());
    expect(screen.getByTestId("parte-chip-c:cli-1-cnd_federal").textContent).toContain("Pendente");
    expect(screen.getByTestId("parte-resumo-c:cli-1").textContent).not.toContain("com erro");
  });

  it("'Solicitar emissão (todas)' states what is already valid and will not be bought again", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: ok("a"), trf3: cel({ tipo: "trf3" }), serasa: cel({ tipo: "serasa" }) },
      { nao_constam: 1, pendente: 2 },
    )));
    await abrir();
    fireEvent.click(screen.getByTestId("parte-solicitar-todas-c:cli-1"));
    const ignoradas = await screen.findByTestId("parte-confirmar-emissao-ignoradas-c:cli-1");
    expect(ignoradas.textContent).toContain("1 certidão já válida");
    expect(ignoradas.textContent).toContain("Receita Federal");
    const lista = screen.getByTestId("parte-confirmar-emissao-lista-c:cli-1").textContent ?? "";
    expect(lista).toContain("TRF3");
    expect(lista).not.toContain("Receita Federal");
  });

  it("downloads one row's PDF (signed URL) and the party's .zip", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: ok("a", "cnd_federal", { tem_arquivo: true, arquivo_url: "k" }), trf3: cel({ tipo: "trf3" }), serasa: cel({ tipo: "serasa" }) },
      { nao_constam: 1, pendente: 2 },
    )));
    mockFetch.mockResolvedValue({
      ok: true, headers: { get: () => 'attachment; filename="certidoes_Maria.zip"' }, blob: async () => new Blob(["z"]),
    });
    await abrir();
    fireEvent.click(screen.getByTestId("parte-baixar-c:cli-1-cnd_federal"));
    expect(mockMint).toHaveBeenCalledWith({ resultadoId: "a", intent: "download" }, expect.anything());
    fireEvent.click(screen.getByTestId("parte-baixar-zip-c:cli-1"));
    await waitFor(() => expect(mockDownload).toHaveBeenCalled());
    expect(mockFetch.mock.calls[0][0]).toContain("/api/clientes/cli-1/certidoes/partes/pessoa/cli-1/download-zip?atendimento_id=at-1");
    expect(mockDownload.mock.calls[0][1]).toBe("certidoes_Maria.zip");
  });

  it("F57: an empty manual placeholder offers no 'Voltar à leitura automática'", async () => {
    mockGet.mockResolvedValue(resp(parte(
      { cnd_federal: cel({ resultado_id: "p", status_processamento: "pendente", aguarda_humano: true }), trf3: cel({ tipo: "trf3" }), serasa: cel({ tipo: "serasa" }) },
      { pendente: 3 },
    )));
    await abrir();
    expect(screen.queryByTestId("parte-voltar-automatico-c:cli-1-cnd_federal")).toBeNull();
  });
});
