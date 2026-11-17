/** Chat hooks: SSE frame handling, pre-stream refusals, abort, endpoints, dictation. */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { ApiError } from "@noctusai/lib";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api, getAuthToken: vi.fn(async () => "tok") }));
const upload = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useCardHub", () => ({ uploadMultipart: upload }));

import {
  fluxoAguardandoRoteiro,
  lerErroCorpo,
  mensagemEscolher,
  mensagemPreStream,
  perfilPendenteDoMeta,
  useConversas,
  useEscolherProposta,
  useMensagens,
  useAdicionarMemoria,
  useDitadoChat,
  useEnviarMensagem,
  useMencoes,
  useSalvarHeadline,
} from "./useChat";

const enc = new TextEncoder();
function sseResponse(frames: unknown[], opts: { hang?: boolean; signal?: AbortSignal } = {}) {
  const chunks = frames.map((f) => enc.encode(`data: ${JSON.stringify(f)}\n\n`));
  let i = 0;
  let cancelled = false;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => {
          if (i < chunks.length) return { done: false, value: chunks[i++] };
          if (opts.hang) {
            await new Promise<void>((resolve) => {
              const iv = setInterval(() => cancelled && (clearInterval(iv), resolve()), 5);
            });
          }
          return { done: true, value: undefined };
        },
        cancel: async () => {
          cancelled = true;
        },
      }),
    },
  } as unknown as Response;
}

let qc: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("useEnviarMensagem", () => {
  it("meta -> delta -> done acumula o texto, guarda o contexto e invalida as mensagens", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        { meta: { mensagem_usuario_id: "u1", contexto_chars: 777, codigos_permitidos: [5] } },
        { delta: "Olá " },
        { delta: "mundo" },
        { done: { mensagem_id: "a1" } },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });

    let ok = false;
    await act(async () => {
      ok = await result.current.enviar("c1", "oi", [{ tipo: "pesquisa", id: "r1" }]);
    });
    expect(ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/media-creation/chat/conversas/c1/mensagens");
    expect(JSON.parse(init.body)).toEqual({ conteudo: "oi", referencias: [{ tipo: "pesquisa", id: "r1" }] });
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao", "chat", "mensagens", "c1"] });
    expect(result.current.estado.ativo).toBe(false);
    expect(result.current.estado.erro).toBeNull();
  });

  it("expõe meta e texto enquanto o stream está ativo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([{ meta: { contexto_chars: 9, codigos_permitidos: [5] } }, { delta: "parcial" }, { truncated: true }], { hang: true })));
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });
    let p: Promise<boolean>;
    act(() => {
      p = result.current.enviar("c1", "oi", []);
    });
    await waitFor(() => expect(result.current.estado.texto).toBe("parcial"));
    expect(result.current.estado.contextoChars).toBe(9);
    expect(result.current.estado.codigosPermitidos).toEqual([5]);
    expect(result.current.estado.truncada).toBe(true);
    expect(result.current.estado.ativo).toBe(true);
    act(() => result.current.parar());
    await act(async () => {
      await p;
    });
    expect(result.current.estado.ativo).toBe(false);
  });

  it("parar() aborta sem erro e recarrega as mensagens (o servidor salvou 'parcial')", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([{ delta: "a" }], { hang: true })));
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });
    let p: Promise<boolean>;
    act(() => {
      p = result.current.enviar("c1", "oi", []);
    });
    await waitFor(() => expect(result.current.estado.texto).toBe("a"));
    act(() => result.current.parar());
    let ok = true;
    await act(async () => {
      ok = await p;
    });
    expect(result.current.estado.erro).toBeNull();
    expect(ok).toBe(true);
    expect(inv).toHaveBeenCalledWith({ queryKey: ["sw", "geracao", "chat", "mensagens", "c1"] });
  });

  it("frame de erro vira mensagem de erro e mantém ok=false", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([{ delta: "x" }, { error: { code: "llm", message: "Falhou a IA" } }])));
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });
    let ok = true;
    await act(async () => {
      ok = await result.current.enviar("c1", "oi", []);
    });
    expect(ok).toBe(false);
    expect(result.current.estado.erro).toBe("Falhou a IA");
  });

  it("409 pré-stream: mensagem clara, sem invalidar nada", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ error: { code: "stream_em_andamento", message: "x" } }) }));
    const inv = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });
    let ok = true;
    await act(async () => {
      ok = await result.current.enviar("c1", "oi", []);
    });
    expect(ok).toBe(false);
    expect(result.current.estado.erro).toMatch(/Aguarde/);
    expect(inv).not.toHaveBeenCalled();
  });

  it("mensagemPreStream cobre 429 e 503", () => {
    expect(mensagemPreStream(429, null, "Limite diário atingido")).toBe("Limite diário atingido");
    expect(mensagemPreStream(503, "ia_nao_configurada", null)).toMatch(/não está configurada/);
    expect(mensagemPreStream(503, "orcamento_ia_excedido", null)).toMatch(/orçamento/);
  });
});

describe("endpoints", () => {
  it("menções: tipo, busca e marca na query", async () => {
    api.get.mockResolvedValue({ data: [{ tipo: "cerebro", id: "b1", rotulo: "Núcleo", detalhe: null }] });
    const { result } = renderHook(() => useMencoes("m1", "cerebro", "nuc", true), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
    expect(api.get).toHaveBeenCalledWith("/api/media-creation/chat/mencoes?marca_id=m1&tipo=cerebro&q=nuc");
  });

  it("memória: POST {marca_id, texto}", async () => {
    api.post.mockResolvedValue({ data: { id: "mm", texto: "t", created_at: "" } });
    const { result } = renderHook(() => useAdicionarMemoria(), { wrapper });
    await result.current.mutateAsync({ marca_id: "m1", texto: "t" });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/chat/memorias", { marca_id: "m1", texto: "t" });
  });

  it("salvar headline: POST /headlines com favoritar", async () => {
    api.post.mockResolvedValue({ data: { id: "h1" } });
    const { result } = renderHook(() => useSalvarHeadline(), { wrapper });
    await result.current.mutateAsync({ marca_id: "m1", texto: "x" });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/headlines", { marca_id: "m1", texto: "x", favoritar: true });
  });
});

describe("useDitadoChat", () => {
  it("envia o áudio com contexto chat_ditado e entrega o texto UMA vez, sem enviar a mensagem", async () => {
    upload.mockResolvedValue({ id: "t1", status: "na_fila" });
    api.get.mockResolvedValue({ id: "t1", status: "concluida", texto: "  texto falado " });
    const onTexto = vi.fn();
    const { result } = renderHook(() => useDitadoChat("m1", onTexto), { wrapper });
    act(() => result.current.enviar(new Blob(["a"], { type: "audio/webm" }), "audio/webm"));
    await waitFor(() => expect(onTexto).toHaveBeenCalledWith("texto falado"));
    const [path, form] = upload.mock.calls[0] as [string, FormData];
    expect(path).toBe("/api/transcricoes");
    expect(form.get("contexto_tipo")).toBe("chat_ditado");
    expect(form.get("contexto_ref")).toBe("m1");
    expect(onTexto).toHaveBeenCalledTimes(1);
  });

  it("falha da transcrição vira erro, sem texto", async () => {
    upload.mockResolvedValue({ id: "t2", status: "na_fila" });
    api.get.mockResolvedValue({ id: "t2", status: "falhou", erro: { mensagem: "Áudio vazio" } });
    const onTexto = vi.fn();
    const { result } = renderHook(() => useDitadoChat("m1", onTexto), { wrapper });
    act(() => result.current.enviar(new Blob(["a"]), "audio/webm"));
    await waitFor(() => expect(result.current.erro).toBe("Áudio vazio"));
    expect(onTexto).not.toHaveBeenCalled();
  });
});

describe("unified chat", () => {
  it("conversas: sem agente na URL e na chave", async () => {
    api.get.mockResolvedValue({ data: { items: [], tem_mais: false } });
    renderHook(() => useConversas("m1"), { wrapper });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(api.get.mock.calls[0][0]).toBe("/api/media-creation/chat/conversas?marca_id=m1&limit=15&offset=0");
  });

  it("lerErroCorpo lê o formato plano {code, detail} e o aninhado {error:{code,message}}", () => {
    expect(lerErroCorpo({ code: "limite_de_mensagens", detail: "Limite" })).toEqual({ code: "limite_de_mensagens", message: "Limite" });
    expect(lerErroCorpo({ error: { code: "FORBIDDEN", message: "Sem acesso" } })).toEqual({ code: "FORBIDDEN", message: "Sem acesso" });
    expect(lerErroCorpo(null)).toEqual({ code: null, message: null });
  });

  it("409 pré-stream no formato plano também vira a mensagem pt-BR", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ code: "stream_em_andamento", detail: "x" }) }));
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });
    await act(async () => {
      await result.current.enviar("c1", "oi", []);
    });
    expect(result.current.estado.erro).toMatch(/Aguarde/);
  });

  it("meta com perfil_ambiguo guarda os candidatos e a mensagem para reenviar; o próximo envio limpa", async () => {
    const resolucao = {
      resolvidos: [],
      ambiguos: [{ trecho: "elias", candidatos: [{ perfil_id: "p1", handle: "a", nome: null }] }],
      nao_encontrados: [],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(sseResponse([{ meta: { modo_estrutura: "perfil_ambiguo", resolucao_perfis: resolucao } }, { delta: "Qual?" }, { done: { mensagem_id: "a1", propostas: [] } }])));
    const { result } = renderHook(() => useEnviarMensagem(), { wrapper });
    await act(async () => {
      await result.current.enviar("c1", "estilo do elias", [{ tipo: "pesquisa", id: "r1" }]);
    });
    expect(result.current.perfilPendente).toEqual({
      modo: "perfil_ambiguo",
      grupos: [{ trecho: "elias", candidatos: [{ perfil_id: "p1", handle: "a", nome: null }] }],
      conteudo: "estilo do elias",
      referencias: [{ tipo: "pesquisa", id: "r1" }],
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([{ done: { mensagem_id: "a2" } }])));
    await act(async () => {
      await result.current.enviar("c1", "outra", []);
    });
    expect(result.current.perfilPendente).toBeNull();
  });

  it("perfilPendenteDoMeta: não_encontrados usa as sugestões; modos resolvidos não pedem nada", () => {
    const r = { resolvidos: [], ambiguos: [], nao_encontrados: [{ trecho: "x", sugestoes: [{ perfil_id: "p", handle: "h", nome: null }] }] };
    expect(perfilPendenteDoMeta({ modo_estrutura: "perfil_nao_encontrado", resolucao_perfis: r }, "m", [])?.grupos[0].candidatos).toHaveLength(1);
    expect(perfilPendenteDoMeta({ modo_estrutura: "mencoes", resolucao_perfis: r }, "m", [])).toBeNull();
    expect(perfilPendenteDoMeta({ modo_estrutura: "perfil_ambiguo" }, "m", [])).toBeNull();
  });

  it("fluxoAguardandoRoteiro: só quando o fluxo anda e ainda não há roteiro", () => {
    const pag = (fluxo: unknown) => ({ pages: [{ items: [{ fluxo }], tem_mais: false }] });
    expect(fluxoAguardandoRoteiro(pag({ etapa: "roteiro_gerando", roteiro: null }) as never)).toBe(true);
    expect(fluxoAguardandoRoteiro(pag({ etapa: "roteiro_gerando", roteiro: { id: "r" } }) as never)).toBe(false);
    expect(fluxoAguardandoRoteiro(pag({ etapa: "roteiro_pronto", roteiro: null }) as never)).toBe(false);
    expect(fluxoAguardandoRoteiro(undefined)).toBe(false);
  });

  it("mensagemEscolher: cada recusa tem texto pt-BR", () => {
    const err = (status: number, body: unknown) => new ApiError(status, "x", body);
    expect(mensagemEscolher(err(429, { code: "limite_diario_roteiros", detail: "d" }))).toMatch(/limite diário/);
    expect(mensagemEscolher(err(404, { code: "proposta_nao_encontrada", detail: "d" }))).toMatch(/não foi encontrada/);
    expect(mensagemEscolher(err(503, { error: { code: "ia_nao_configurada", message: "m" } }))).toMatch(/não está configurada/);
    expect(mensagemEscolher(new Error("boom"))).toMatch(/Não foi possível criar o roteiro/);
  });

  it("escolher: POST só com proposta_id; marca a proposta e anexa a mensagem roteiro_gerado (sem duplicar)", async () => {
    const msgs = { pages: [{ items: [{ id: "a", propostas: [{ id: "p1", status: "proposta", headline_id: null }], fluxo: null }], tem_mais: false }], pageParams: [null] };
    qc.setQueryData(["sw", "geracao", "chat", "mensagens", "c1"], msgs);
    const fluxo = { proposta_id: "p1", etapa: "roteiro_gerando", headline: { id: "h1", texto: "t" }, roteiro: null, post: null, estruturas: [], legenda: "pendente", erro_codigo: null };
    api.post.mockResolvedValue({ data: { proposta: { id: "p1", status: "escolhida", headline_id: "h1" }, fluxo, mensagem_id: "m9", ja_existia: false, em_andamento: false } });
    const { result } = renderHook(() => useEscolherProposta(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ conversaId: "c1", proposta_id: "p1" });
    });
    expect(api.post).toHaveBeenCalledWith("/api/media-creation/chat/conversas/c1/escolher", { proposta_id: "p1" });
    const itens = (qc.getQueryData(["sw", "geracao", "chat", "mensagens", "c1"]) as typeof msgs).pages[0].items as any[];
    expect(itens.map((i) => i.id)).toEqual(["a", "m9"]);
    expect(itens[0].propostas[0]).toMatchObject({ status: "escolhida", headline_id: "h1" });
    expect(itens[1]).toMatchObject({ tipo: "roteiro_gerado", role: "assistant", fluxo });
    await act(async () => {
      await result.current.mutateAsync({ conversaId: "c1", proposta_id: "p1" });
    });
    expect(((qc.getQueryData(["sw", "geracao", "chat", "mensagens", "c1"]) as typeof msgs).pages[0].items as any[]).filter((i) => i.id === "m9")).toHaveLength(1);
  });

  it("escolher: erro não altera o cache e propaga para o chamador mostrar a recusa", async () => {
    qc.setQueryData(["sw", "geracao", "chat", "mensagens", "c1"], { pages: [{ items: [], tem_mais: false }], pageParams: [null] });
    api.post.mockRejectedValue(new ApiError(429, "limite", { code: "limite_diario_roteiros", detail: "d" }));
    const { result } = renderHook(() => useEscolherProposta(), { wrapper });
    await act(async () => {
      await expect(result.current.mutateAsync({ conversaId: "c1", proposta_id: "p1" })).rejects.toBeInstanceOf(ApiError);
    });
    expect((qc.getQueryData(["sw", "geracao", "chat", "mensagens", "c1"]) as any).pages[0].items).toEqual([]);
  });

  it("mensagens: não carrega as mensagens de outra conversa enquanto a nova busca roda", async () => {
    api.get.mockResolvedValueOnce({ data: { items: [{ id: "x" }], tem_mais: false } });
    const { result, rerender } = renderHook(({ id }) => useMensagens(id), { wrapper, initialProps: { id: "c1" } });
    await waitFor(() => expect(result.current.mensagens).toHaveLength(1));
    api.get.mockReturnValue(new Promise(() => undefined));
    rerender({ id: "c2" });
    expect(result.current.mensagens).toHaveLength(0);
    expect(result.current.showSkeleton).toBe(true);
  });
});
