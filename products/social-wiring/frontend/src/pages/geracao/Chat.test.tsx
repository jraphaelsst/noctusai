/** Chat: rail, streaming render + stop, @ picker chips, citations, headline actions, dictation, meter. */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Chat from "./Chat";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/components/geracao/biblioteca/ViralModal", () => ({
  ViralModal: ({ open, viralId }: { open: boolean; viralId: string | null }) =>
    open ? <div data-testid="viral-modal">{viralId}</div> : null,
}));
vi.mock("@/components/geracao/roteiro/RoteiroAvancadoModal", () => ({
  RoteiroAvancadoModal: ({ open, headlineInicial }: { open: boolean; headlineInicial?: { id?: string; texto: string } | null }) =>
    open ? <div data-testid="roteiro-modal">{`${headlineInicial?.id ?? "sem-id"}|${headlineInicial?.texto}`}</div> : null,
}));
vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  usePerfisMonitorados: () => ({ data: [{ id: "p9", handle: "elias" }] }),
}));

const c = vi.hoisted(() => ({
  conversas: vi.fn(),
  mensagens: vi.fn(),
  contexto: vi.fn(),
  enviar: vi.fn(),
  parar: vi.fn(),
  estado: { current: null as any },
  criar: vi.fn(),
  salvar: vi.fn(),
  resolver: vi.fn(),
  ditadoCb: { current: null as null | ((t: string) => void) },
  mencoes: vi.fn(),
}));

vi.mock("@/hooks/geracao/useChat", () => ({
  MAX_REFERENCIAS: 10,
  LIMITE_CONTEXTO_AVISO: 50_000,
  useConversas: () => c.conversas(),
  useMensagens: () => c.mensagens(),
  useContextoChat: () => c.contexto(),
  useCriarConversa: () => ({ mutateAsync: c.criar, isPending: false }),
  useRenomearConversa: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApagarConversa: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSalvarHeadline: () => ({ mutateAsync: c.salvar, isPending: false }),
  useEnviarMensagem: () => ({ estado: c.estado.current, enviar: c.enviar, parar: c.parar }),
  useDitadoChat: (_m: string | null, cb: (t: string) => void) => {
    c.ditadoCb.current = cb;
    return { enviar: vi.fn(), transcrevendo: false, erro: null };
  },
  useMencoes: () => c.mencoes(),
  useMemorias: () => ({ data: [], showSkeleton: false, isRefreshing: false }),
  useAdicionarMemoria: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoverMemoria: () => ({ mutateAsync: vi.fn(), isPending: false }),
  resolverViralPorCodigo: (...a: unknown[]) => c.resolver(...a),
}));

const ESTADO_OCIOSO = { ativo: false, usuario: null, texto: "", truncada: false, erro: null, contextoChars: null, codigosPermitidos: null };

const conv = (over: Partial<any> = {}) => ({ id: "c1", marca_id: "m1", agente: "headline", titulo: "Minha conversa", last_message_at: null, ...over });
const msg = (over: Partial<any> = {}) => ({
  id: "x1", role: "assistant", conteudo: "", referencias: [], status: "completa", truncada: false, created_at: "", ...over,
});

function renderPage(url = "/media-creation/chat?c=c1") {
  return rtl.render(
    <MemoryRouter initialEntries={[url]}>
      <Chat />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  c.estado.current = ESTADO_OCIOSO;
  c.conversas.mockReturnValue({
    conversas: [conv()], showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    isFetchingNextPage: false, fetchNextPage: vi.fn(), refetch: vi.fn(),
  });
  c.mensagens.mockReturnValue({
    mensagens: [], showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    isFetchingNextPage: false, fetchNextPage: vi.fn(), refetch: vi.fn(),
  });
  c.contexto.mockReturnValue({ data: { contexto_chars: 1234, limite: 60000 } });
  c.mencoes.mockReturnValue({
    data: [{ tipo: "pesquisa", id: "r1", rotulo: "Item de pesquisa", detalhe: null }],
    showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn(),
  });
  c.enviar.mockResolvedValue(true);
  c.salvar.mockResolvedValue({ id: "h-salva" });
});

describe("Chat", () => {
  it("mostra skeleton, e não 'vazio', enquanto as mensagens carregam", () => {
    c.mensagens.mockReturnValue({ mensagens: [], showSkeleton: true, isRefreshing: false, isError: false, data: undefined, hasNextPage: false });
    renderPage();
    expect(rtl.screen.getByTestId("mensagens-skeleton")).toBeTruthy();
    expect(rtl.screen.queryByText(/Peça headlines/)).toBeNull();
  });

  it("estado de erro das mensagens oferece Tentar novamente", async () => {
    const refetch = vi.fn();
    c.mensagens.mockReturnValue({ mensagens: [], showSkeleton: false, isRefreshing: false, isError: true, data: undefined, refetch });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Tentar novamente" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("rail vazio usa a cópia do CoreStudio", () => {
    c.conversas.mockReturnValue({ conversas: [], showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false });
    renderPage("/media-creation/chat");
    expect(rtl.screen.getByText("Nenhuma conversa para este agente.")).toBeTruthy();
  });

  it("envia a mensagem com as referências anexadas pelo @", async () => {
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: /Mencionar/ }));
    expect(rtl.screen.getByRole("tab", { name: "Minha Pesquisa" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Segundo Cérebro" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Biblioteca" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Headlines" })).toBeTruthy();
    await userEvent.click(rtl.screen.getByText("Item de pesquisa"));
    expect(rtl.screen.getByRole("button", { name: "Remover Item de pesquisa" })).toBeTruthy();

    await userEvent.type(rtl.screen.getByLabelText("Mensagem"), "oi");
    await userEvent.click(rtl.screen.getByRole("button", { name: /Enviar/ }));
    expect(c.enviar).toHaveBeenCalledWith("c1", "oi", [{ tipo: "pesquisa", id: "r1" }]);
  });

  it("cria a conversa no primeiro envio, com o título dos 60 primeiros caracteres", async () => {
    c.criar.mockResolvedValue(conv({ id: "novo" }));
    renderPage("/media-creation/chat");
    const longo = "a".repeat(80);
    await userEvent.type(rtl.screen.getByLabelText("Mensagem"), longo);
    await userEvent.click(rtl.screen.getByRole("button", { name: /Enviar/ }));
    expect(c.criar).toHaveBeenCalledWith({ marca_id: "m1", agente: "headline", titulo: "a".repeat(60) });
    expect(c.enviar).toHaveBeenCalledWith("novo", longo, []);
  });

  it("durante o stream mostra o texto parcial e Parar aborta", async () => {
    c.estado.current = { ...ESTADO_OCIOSO, ativo: true, usuario: "pergunta", texto: "resposta parcial" };
    renderPage();
    expect(rtl.screen.getByText("pergunta")).toBeTruthy();
    expect(rtl.screen.getByText("resposta parcial")).toBeTruthy();
    expect(rtl.screen.queryByRole("button", { name: /Enviar/ })).toBeNull();
    await userEvent.click(rtl.screen.getByRole("button", { name: /Parar/ }));
    expect(c.parar).toHaveBeenCalled();
  });

  it("citação (estrutura #N) abre o viral resolvido; código desconhecido avisa", async () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ conteudo: "1. Ninguém te conta isso (estrutura #123)" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    c.resolver.mockResolvedValue({ id: "viral-uuid", codigo: 123 });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("link", { name: "estrutura #123" }));
    await rtl.waitFor(() => expect(rtl.screen.getByTestId("viral-modal").textContent).toBe("viral-uuid"));
    expect(c.resolver).toHaveBeenCalledWith("m1", 123);
  });

  it("em streaming, só linka códigos que o servidor permitiu", () => {
    c.estado.current = { ...ESTADO_OCIOSO, ativo: true, usuario: "p", texto: "- A (estrutura #1) e B (estrutura #2)", codigosPermitidos: [1] };
    renderPage();
    expect(rtl.screen.getByRole("link", { name: "estrutura #1" })).toBeTruthy();
    expect(rtl.screen.queryByRole("link", { name: "estrutura #2" })).toBeNull();
  });

  it("salvar headline e criar roteiro a partir dela (salva e abre o modal com o id)", async () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ conteudo: "1. **Você erra isso todo dia** (estrutura #5)\n2. Outra headline boa aqui" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    const salvarBtns = rtl.screen.getAllByRole("button", { name: "Salvar headline" });
    expect(salvarBtns).toHaveLength(2);
    await userEvent.click(salvarBtns[0]);
    expect(c.salvar).toHaveBeenCalledWith({ marca_id: "m1", texto: "Você erra isso todo dia" });

    await userEvent.click(rtl.screen.getAllByRole("button", { name: "Criar roteiro a partir desta headline" })[0]);
    await rtl.waitFor(() => expect(rtl.screen.getByTestId("roteiro-modal").textContent).toBe("h-salva|Você erra isso todo dia"));
    expect(c.salvar).toHaveBeenCalledTimes(1);
  });

  it("'headline editável' abre o modal sem salvar nem vincular id", async () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ conteudo: "- Uma headline qualquer" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Criar roteiro com headline editável" }));
    expect(rtl.screen.getByTestId("roteiro-modal").textContent).toBe("sem-id|Uma headline qualquer");
    expect(c.salvar).not.toHaveBeenCalled();
  });

  it("ditado preenche o campo e NÃO envia", async () => {
    renderPage();
    rtl.act(() => c.ditadoCb.current?.("texto ditado"));
    expect((rtl.screen.getByLabelText("Mensagem") as HTMLTextAreaElement).value).toBe("texto ditado");
    expect(c.enviar).not.toHaveBeenCalled();
  });

  it("medidor de contexto avisa a partir de 50.000", () => {
    c.contexto.mockReturnValue({ data: { contexto_chars: 52000, limite: 60000 } });
    renderPage();
    expect(rtl.screen.getByTestId("medidor-contexto").textContent).toMatch(/perto do limite/);
  });

  it("?cite_perfil anexa '@perfil — Todos os vídeos'", async () => {
    renderPage("/media-creation/chat?c=c1&cite_perfil=p9");
    await rtl.waitFor(() => expect(rtl.screen.getByRole("button", { name: "Remover @elias — Todos os vídeos" })).toBeTruthy());
  });

  it("agente ROTEIRO não mostra ações de headline", async () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ conteudo: "- Uma headline qualquer" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("tab", { name: "ROTEIRO" }));
    expect(rtl.screen.queryByRole("button", { name: "Salvar headline" })).toBeNull();
  });
});
