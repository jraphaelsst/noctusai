/** Chat hooks: SSE frame handling, pre-stream refusals, abort, endpoints, dictation. */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api, getAuthToken: vi.fn(async () => "tok") }));
const upload = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useCardHub", () => ({ uploadMultipart: upload }));

import {
  mensagemPreStream,
  resolverViralPorCodigo,
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

  it("resolverViralPorCodigo devolve null quando o código não está na biblioteca", async () => {
    api.get.mockResolvedValue({ data: { items: [], total: 0, page: 1, filtro_automatico: false } });
    expect(await resolverViralPorCodigo("m1", 99)).toBeNull();
    expect(api.get.mock.calls[0][0]).toContain("codigo=99");
    api.get.mockResolvedValue({ data: { items: [{ id: "v", codigo: 99 }], total: 1, page: 1, filtro_automatico: false } });
    expect((await resolverViralPorCodigo("m1", 99))?.id).toBe("v");
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
