/** Chat (unified): rail, streaming, @ picker, propostas -> escolher, roteiro_gerado, ambiguity chips, deep links, dictation, meter. */
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
vi.mock("@/components/geracao/chat/FluxoCard", () => ({
  FluxoCard: ({ fluxo, onTentarDeNovo }: { fluxo: { etapa: string; proposta_id: string }; onTentarDeNovo: (id: string) => void }) => (
    <div data-testid="fluxo-card" data-etapa={fluxo.etapa}>
      <button type="button" onClick={() => onTentarDeNovo(fluxo.proposta_id)}>
        retry-fluxo
      </button>
    </div>
  ),
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
  escolher: vi.fn(),
  escolhendo: { current: false },
  perfilPendente: { current: null as any },
  limpar: vi.fn(),
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
  mensagemEscolher: () => "ERRO-ESCOLHER",
  useEscolherProposta: () => ({ mutateAsync: c.escolher, isPending: c.escolhendo.current, variables: c.escolhendo.current ? { proposta_id: "p1" } : undefined }),
  useEnviarMensagem: () => ({
    estado: c.estado.current,
    enviar: c.enviar,
    parar: c.parar,
    perfilPendente: c.perfilPendente.current,
    limparPerfilPendente: c.limpar,
  }),
  useDitadoChat: (_m: string | null, cb: (t: string) => void) => {
    c.ditadoCb.current = cb;
    return { enviar: vi.fn(), transcrevendo: false, erro: null };
  },
  useMencoes: () => c.mencoes(),
  useMemorias: () => ({ data: [], showSkeleton: false, isRefreshing: false }),
  useAdicionarMemoria: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoverMemoria: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const ESTADO_OCIOSO = { ativo: false, usuario: null, texto: "", truncada: false, erro: null, contextoChars: null, codigosPermitidos: null };

const conv = (over: Partial<any> = {}) => ({ id: "c1", marca_id: "m1", agente: "unificado", titulo: "Minha conversa", last_message_at: null, ...over });
const msg = (over: Partial<any> = {}) => ({
  id: "x1", role: "assistant", conteudo: "", referencias: [], status: "completa", truncada: false, created_at: "",
  tipo: "texto", propostas: [], fluxo: null, ...over,
});
const proposta = (over: Partial<any> = {}) => ({
  id: "p1", ordem: 1, texto: "Você erra isso todo dia", gatilho_tag: "Mistério", status: "proposta", headline_id: null,
  estruturas: [{ id: "e1", codigo: 7, perfil: { id: "pf1", handle: "elias", nome: null }, principal: true }], ...over,
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
  c.escolher.mockResolvedValue({ ja_existia: false, em_andamento: false });
  c.escolhendo.current = false;
  c.perfilPendente.current = null;
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

  it("rail vazio usa a cópia de referência", () => {
    c.conversas.mockReturnValue({ conversas: [], showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false });
    renderPage("/media-creation/chat");
    expect(rtl.screen.getByText("Nenhuma conversa ainda. Comece uma nova.")).toBeTruthy();
  });

  it("envia a mensagem com as referências anexadas pelo @", async () => {
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: /Mencionar/ }));
    expect(rtl.screen.getByRole("tab", { name: "Minha Pesquisa" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Segundo Cérebro" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Biblioteca" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Headlines" })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: "Estruturas" })).toBeTruthy();
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
    expect(c.criar).toHaveBeenCalledWith({ marca_id: "m1", titulo: "a".repeat(60) });
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

  it("não há abas HEADLINE/ROTEIRO: é um chat único", () => {
    renderPage();
    expect(rtl.screen.queryByRole("tab", { name: "HEADLINE" })).toBeNull();
    expect(rtl.screen.queryByRole("tab", { name: "ROTEIRO" })).toBeNull();
  });

  it("propostas do servidor viram cards com a estrutura de origem (e NÃO se derivam do texto)", () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ conteudo: "1. Linha do texto que não é proposta (Mistério)", propostas: [proposta()] })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    expect(rtl.screen.getAllByRole("button", { name: "Criar roteiro" })).toHaveLength(1);
    expect(rtl.screen.getByText("Você erra isso todo dia")).toBeTruthy();
    const chip = rtl.screen.getByRole("link", { name: "Abrir a estrutura #7 de @elias" });
    expect(chip.getAttribute("href")).toBe("/media-creation/biblioteca/estruturas/e1");
  });

  it("texto sem propostas não oferece 'Criar roteiro' (o parser do FE foi removido)", () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ conteudo: "1. Uma headline qualquer (Recompensa)\n2. Outra headline boa" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    expect(rtl.screen.queryByRole("button", { name: /Criar roteiro/ })).toBeNull();
  });

  it("clicar na proposta chama escolher com {conversaId, proposta_id}", async () => {
    c.mensagens.mockReturnValue({
      mensagens: [msg({ propostas: [proposta()], conteudo: "Aqui vão" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Criar roteiro" }));
    expect(c.escolher).toHaveBeenCalledWith({ conversaId: "c1", proposta_id: "p1" });
  });

  it("recusa do escolher aparece como toast pt-BR", async () => {
    const { toast } = await import("sonner");
    c.escolher.mockRejectedValue(new Error("x"));
    c.mensagens.mockReturnValue({
      mensagens: [msg({ propostas: [proposta()], conteudo: "Aqui vão" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Criar roteiro" }));
    await rtl.waitFor(() => expect(toast.error).toHaveBeenCalledWith("ERRO-ESCOLHER"));
  });

  it("clique repetido (ja_existia + em_andamento) avisa em vez de falhar", async () => {
    const { toast } = await import("sonner");
    c.escolher.mockResolvedValue({ ja_existia: true, em_andamento: true });
    c.mensagens.mockReturnValue({
      mensagens: [msg({ propostas: [proposta()], conteudo: "Aqui vão" })],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Criar roteiro" }));
    await rtl.waitFor(() => expect(toast.info).toHaveBeenCalledWith("Este roteiro já está sendo criado."));
  });

  it("proposta escolhida mostra 'Roteiro criado' e a mensagem roteiro_gerado renderiza o fluxo", async () => {
    c.mensagens.mockReturnValue({
      mensagens: [
        msg({ id: "a", propostas: [proposta({ status: "escolhida", headline_id: "h1" })], conteudo: "Aqui vão" }),
        msg({ id: "b", tipo: "roteiro_gerado", conteudo: "Criei o roteiro desta headline e o card na Esteira.", fluxo: { proposta_id: "p1", etapa: "roteiro_gerando" } }),
      ],
      showSkeleton: false, isRefreshing: false, isError: false, data: {}, hasNextPage: false,
    });
    renderPage();
    expect((rtl.screen.getByRole("button", { name: /Roteiro criado/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(rtl.screen.getByTestId("fluxo-card").getAttribute("data-etapa")).toBe("roteiro_gerando");
    await userEvent.click(rtl.screen.getByText("retry-fluxo"));
    expect(c.escolher).toHaveBeenCalledWith({ conversaId: "c1", proposta_id: "p1" });
  });

  it("perfil ambíguo: chips dos candidatos; escolher reenvia a mesma mensagem com perfil:<uuid>", async () => {
    c.perfilPendente.current = {
      modo: "perfil_ambiguo",
      grupos: [{ trecho: "elias", candidatos: [{ perfil_id: "pf1", handle: "elias_a", nome: "Elias A" }, { perfil_id: "pf2", handle: "elias_b", nome: null }] }],
      conteudo: "headlines no estilo do elias",
      referencias: [{ tipo: "pesquisa", id: "r1" }],
    };
    renderPage();
    expect(rtl.screen.getByText(/Mais de um perfil combina com “elias”/)).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: /@elias_b/ }));
    expect(c.enviar).toHaveBeenCalledWith("c1", "headlines no estilo do elias", [
      { tipo: "pesquisa", id: "r1" },
      { tipo: "biblioteca", id: "perfil:pf2" },
    ]);
  });

  it("perfil não encontrado mostra as sugestões", () => {
    c.perfilPendente.current = {
      modo: "perfil_nao_encontrado",
      grupos: [{ trecho: "xyz", candidatos: [{ perfil_id: "pf9", handle: "xyzz", nome: null }] }],
      conteudo: "oi",
      referencias: [],
    };
    renderPage();
    expect(rtl.screen.getByText(/Não encontramos “xyz” na biblioteca/)).toBeTruthy();
    expect(rtl.screen.getByRole("button", { name: /@xyzz/ })).toBeTruthy();
  });

  it("?conversa= abre a conversa e ?estrutura= anexa a Estrutura e limpa a URL", async () => {
    renderPage("/media-creation/chat?conversa=c1&estrutura=e1");
    await rtl.waitFor(() => expect(rtl.screen.getByRole("button", { name: "Remover Estrutura escolhida" })).toBeTruthy());
    await userEvent.type(rtl.screen.getByLabelText("Mensagem"), "oi");
    await userEvent.click(rtl.screen.getByRole("button", { name: /Enviar/ }));
    expect(c.enviar).toHaveBeenCalledWith("c1", "oi", [{ tipo: "estrutura", id: "e1" }]);
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
});
