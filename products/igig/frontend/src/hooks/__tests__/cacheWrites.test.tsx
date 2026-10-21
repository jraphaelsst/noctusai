/**
 * Cache-write contract for igig's mutation hooks: a write puts what it knows
 * into the cache — drawn on the click when predictable, committed from the
 * server's answer otherwise — instead of waiting for a refetch.
 *
 * Every test freezes the network on a deferred promise and asserts the cache
 * WHILE the request is still in flight (or right after it answered, with the
 * follow-up GET still hanging). They fail on the old invalidate-only hooks.
 * KB § PATTERNS/frontend/mutation-cache-writes.md
 */
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { get, post, patch, put, del, upload } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  del: vi.fn(),
  upload: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { get, post, patch, put, delete: del, upload } };
});

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { qc, wrapper };
}

/** A request the test answers (or fails) by hand. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

vi.setConfig({ testTimeout: 60_000, hookTimeout: 120_000 });

beforeEach(() => {
  vi.clearAllMocks();
  get.mockReturnValue(new Promise(() => {})); // a refetch must never be what makes the screen right
});

describe("clientes", () => {
  it("an edit shows in the list AND the open card on the click, and a refusal puts it back", async () => {
    const { qc, wrapper } = setup();
    const KEY = ["igig", "clientes", "", "", "", ""];
    const DETAIL = ["igig", "clientes", "detalhe", "c1"];
    qc.setQueryData(KEY, { itens: [{ id: "c1", nome: "Sol" }], total: 1 });
    qc.setQueryData(DETAIL, { id: "c1", nome: "Sol" });
    const answer = deferred<unknown>();
    patch.mockReturnValue(answer.promise);
    const { useAtualizarCliente } = await import("../useClientes");
    const { result } = renderHook(() => useAtualizarCliente(), { wrapper });

    result.current.mutate({ id: "c1", nome: "Sol & Mar" });
    await waitFor(() => expect(qc.getQueryData<any>(KEY).itens[0].nome).toBe("Sol & Mar"));
    expect(qc.getQueryData<any>(DETAIL).nome).toBe("Sol & Mar");

    answer.reject(new Error("422"));
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(qc.getQueryData<any>(KEY).itens[0].nome).toBe("Sol");
    expect(qc.getQueryData<any>(DETAIL).nome).toBe("Sol");
  });

  it("a removed cliente leaves the list (and the total) on the click", async () => {
    const { qc, wrapper } = setup();
    const KEY = ["igig", "clientes", "", "", "", ""];
    qc.setQueryData(KEY, { itens: [{ id: "c1" }, { id: "c2" }], total: 2 });
    del.mockReturnValue(new Promise(() => {}));
    const { useRemoverCliente } = await import("../useClientes");
    const { result } = renderHook(() => useRemoverCliente(), { wrapper });
    result.current.mutate("c1");
    await waitFor(() => expect(qc.getQueryData<any>(KEY)).toEqual({ itens: [{ id: "c2" }], total: 1 }));
  });

  it("a new cliente is in the default list as soon as the POST answers", async () => {
    const { qc, wrapper } = setup();
    const KEY = ["igig", "clientes", "", "", "", ""];
    qc.setQueryData(KEY, { itens: [], total: 0 });
    post.mockResolvedValue({ id: "c9", nome: "Nova", status: "prospect" });
    const { useCriarCliente } = await import("../useClientes");
    const { result } = renderHook(() => useCriarCliente(), { wrapper });
    result.current.mutate({ nome: "Nova" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any>(KEY)).toEqual({ itens: [{ id: "c9", nome: "Nova", status: "prospect" }], total: 1 });
  });
});

describe("automações", () => {
  it("an edited rule is patched in the list on the click; a new one is committed from the answer", async () => {
    const { qc, wrapper } = setup();
    const KEY = ["igig", "automacoes", "lista", {}];
    qc.setQueryData(KEY, [{ id: "a1", ativo: true }]);
    patch.mockReturnValue(new Promise(() => {}));
    const { useAutomacaoMutations } = await import("../useAutomacoes");
    const { result } = renderHook(() => useAutomacaoMutations(), { wrapper });
    result.current.atualizar.mutate({ id: "a1", patch: { ativo: false } });
    await waitFor(() => expect(qc.getQueryData<any[]>(KEY)![0].ativo).toBe(false));

    post.mockResolvedValue({ data: { id: "a2", pipeline: "comercial", ativo: true } });
    result.current.criar.mutate({ pipeline: "comercial", stage_id: "s", gatilho: "entrada_etapa", acao: { tipo: "notificar", params: { usuario_ids: [] } } });
    await waitFor(() => expect(qc.getQueryData<any[]>(KEY)!.map((a) => a.id)).toEqual(["a1", "a2"]));
  });
});

describe("comercial", () => {
  const col = (etapa: string, cards: any[]) => ({ etapa, total: cards.length, valorTotal: cards.reduce((s, c) => s + (c.valor_estimado ?? 0), 0), cards });
  it("a lost negócio leaves the board on the click and lands in the archive on the answer", async () => {
    const { qc, wrapper } = setup();
    const BOARD = ["igig-comercial", {}];
    const PERDIDOS = ["igig", "comercial", "perdidos"];
    qc.setQueryData(BOARD, [col("e1", [{ id: "n1", valor_estimado: 100 }]), col("e2", [])]);
    qc.setQueryData(PERDIDOS, []);
    const answer = deferred<unknown>();
    post.mockReturnValue(answer.promise);
    const { usePerderNegocio } = await import("../useComercial");
    const { result } = renderHook(() => usePerderNegocio(), { wrapper });

    result.current.mutate({ id: "n1", motivo: "preço" });
    await waitFor(() => expect(qc.getQueryData<any[]>(BOARD)![0]).toMatchObject({ cards: [], total: 0, valorTotal: 0 }));

    answer.resolve({ data: { id: "n1", status: "perdido", etapa_id: "e1" } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any[]>(PERDIDOS)).toEqual([{ id: "n1", status: "perdido", etapa_id: "e1" }]);
  });

  it("a new negócio is on top of the stage the server chose when the POST answers", async () => {
    const { qc, wrapper } = setup();
    const BOARD = ["igig-comercial", {}];
    qc.setQueryData(BOARD, [col("e1", [{ id: "n1", valor_estimado: 100 }])]);
    post.mockResolvedValue({ data: { id: "n2", etapa_id: "e1", valor_estimado: 50 } });
    const { useCriarNegocio } = await import("../useComercial");
    const { result } = renderHook(() => useCriarNegocio(), { wrapper });
    result.current.mutate({ lead: { nome: "Ana" } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any[]>(BOARD)![0]).toMatchObject({ total: 2, valorTotal: 150, cards: [{ id: "n2" }, { id: "n1" }] });
  });
});

describe("contratos", () => {
  it("an encerrado contrato shows as encerrado on the click", async () => {
    const { qc, wrapper } = setup();
    const KEY = ["igig", "contratos", "lista", { cliente_id: "c1" }];
    qc.setQueryData(KEY, [{ id: "k1", status: "ativo" }]);
    post.mockReturnValue(new Promise(() => {}));
    const { useContratoMutations } = await import("../useContratos");
    const { result } = renderHook(() => useContratoMutations(), { wrapper });
    result.current.encerrar.mutate({ id: "k1", motivo: "fim" });
    await waitFor(() => expect(qc.getQueryData<any[]>(KEY)![0]).toMatchObject({ status: "encerrado", motivo_encerramento: "fim" }));
  });
});

describe("custos", () => {
  it("a removed função leaves the list on the click; a new profissional is committed from the answer", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "custos", "funcoes"], [{ id: "f1" }, { id: "f2" }]);
    del.mockReturnValue(new Promise(() => {}));
    const { useRemoverFuncao, useCriarProfissional } = await import("../useCustos");
    const rem = renderHook(() => useRemoverFuncao(), { wrapper });
    rem.result.current.mutate("f1");
    await waitFor(() => expect(qc.getQueryData(["igig", "custos", "funcoes"])).toEqual([{ id: "f2" }]));

    qc.setQueryData(["igig", "custos", "profissionais", false], []);
    qc.setQueryData(["igig", "custos", "profissionais", true], []);
    post.mockResolvedValue({ id: "p1", nome: "Lia", ativo: true, custo_hora_efetivo: 40 });
    const cri = renderHook(() => useCriarProfissional(), { wrapper });
    cri.result.current.mutate({ nome: "Lia" });
    await waitFor(() => expect(cri.result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any[]>(["igig", "custos", "profissionais", false])).toHaveLength(1);
    expect(qc.getQueryData<any[]>(["igig", "custos", "profissionais", true])).toHaveLength(1);
  });
});

describe("distribuição", () => {
  it("a cancelled publicação is cancelada in the pauta list and the queue on the click; a new one is committed on the answer", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "distribuicao", "publicacoes", "pa1"], [{ id: "pub1", status: "agendada" }]);
    qc.setQueryData(["igig", "distribuicao", "fila"], [{ id: "pub1", status: "agendada" }]);
    post.mockReturnValue(new Promise(() => {}));
    const { useCancelarPublicacao } = await import("../useDistribuicao");
    const { result } = renderHook(() => useCancelarPublicacao(), { wrapper });
    result.current.mutate("pub1");
    await waitFor(() => expect(qc.getQueryData<any[]>(["igig", "distribuicao", "publicacoes", "pa1"])![0].status).toBe("cancelada"));
    expect(qc.getQueryData<any[]>(["igig", "distribuicao", "fila"])![0].status).toBe("cancelada");
  });

  it("a scheduled publicação is in its pauta's list when the POST answers", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "distribuicao", "publicacoes", "pa1"], []);
    post.mockResolvedValue({ id: "pub2", pauta_id: "pa1", status: "agendada" });
    const { useAgendarPublicacao } = await import("../useDistribuicao");
    const { result } = renderHook(() => useAgendarPublicacao(), { wrapper });
    result.current.mutate({ pauta_id: "pa1", canal: "instagram", agendada_para: "2026-11-01T10:00:00Z" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(["igig", "distribuicao", "publicacoes", "pa1"])).toEqual([{ id: "pub2", pauta_id: "pa1", status: "agendada" }]);
  });
});

describe("esteira", () => {
  const col = (etapa: string, cards: any[]) => ({ etapa, total: cards.length, valorTotal: 0, cards });
  it("a deleted tarefa leaves the board on the click; a new one is on the board when the POST answers", async () => {
    const { qc, wrapper } = setup();
    const BOARD = ["igig-esteira-board", {}];
    qc.setQueryData(BOARD, [col("e1", [{ id: "t1" }, { id: "t2" }])]);
    del.mockReturnValue(new Promise(() => {}));
    const { useExcluirTarefa, useCriarTarefa } = await import("../useEsteira");
    const exc = renderHook(() => useExcluirTarefa(), { wrapper });
    exc.result.current.mutate({ id: "t1" });
    await waitFor(() => expect(qc.getQueryData<any[]>(BOARD)![0].cards).toEqual([{ id: "t2" }]));

    post.mockResolvedValue({ id: "t3", etapa_id: "e1", titulo: "Nova" });
    const cri = renderHook(() => useCriarTarefa(), { wrapper });
    cri.result.current.mutate({ pauta_id: "pa", titulo: "Nova" });
    await waitFor(() => expect(cri.result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any[]>(BOARD)![0].cards.map((c: any) => c.id)).toEqual(["t3", "t2"]);
  });

  it("the running timer segment is in the apontamentos as soon as the server answers", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "esteira", "apontamentos", "t1"], []);
    post.mockResolvedValue({ id: "ap1", tarefa_id: "t1", encerrado_em: null });
    const { useIniciarTimer } = await import("../useEsteira");
    const { result } = renderHook(() => useIniciarTimer(), { wrapper });
    result.current.mutate("t1");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData(["igig", "esteira", "apontamentos", "t1"])).toEqual([{ id: "ap1", tarefa_id: "t1", encerrado_em: null }]);
  });
});

describe("financeiro", () => {
  it("a paid fatura is paga in the list on the click", async () => {
    const { qc, wrapper } = setup();
    const KEY = ["igig", "financeiro", "faturas", "2026-10", ""];
    qc.setQueryData(KEY, [{ id: "f1", status: "enviada", valor_total: 100 }]);
    post.mockReturnValue(new Promise(() => {}));
    const { useMarcarPaga } = await import("../useFinanceiro");
    const { result } = renderHook(() => useMarcarPaga(), { wrapper });
    result.current.mutate("f1");
    await waitFor(() => expect(qc.getQueryData<any[]>(KEY)![0].status).toBe("paga"));
  });

  it("a new linha is drawn on the click and the fatura's new total is committed from the answer", async () => {
    const { qc, wrapper } = setup();
    const LISTA = ["igig", "financeiro", "faturas", "", ""];
    const ITENS = ["igig", "financeiro", "itens", "f1"];
    qc.setQueryData(LISTA, [{ id: "f1", valor_total: 100 }]);
    qc.setQueryData(ITENS, []);
    const answer = deferred<unknown>();
    post.mockReturnValue(answer.promise);
    const { useAdicionarItem } = await import("../useFinanceiro");
    const { result } = renderHook(() => useAdicionarItem(), { wrapper });
    result.current.mutate({ faturaId: "f1", descricao: "Extra", quantidade: 2, valor_unit: 50 });
    await waitFor(() => expect(qc.getQueryData<any[]>(ITENS)).toHaveLength(1));
    expect(qc.getQueryData<any[]>(ITENS)![0]).toMatchObject({ descricao: "Extra", quantidade: 2, valor_unit: 50 });

    answer.resolve({ id: "f1", valor_total: 200 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any[]>(LISTA)![0].valor_total).toBe(200);
  });
});

describe("integrações", () => {
  it("a disconnected canal shows as desconectado on the click", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "integracoes"], [{ canal: "instagram", conectado: true, origem: "org", conta_externa: "@x" }]);
    del.mockReturnValue(new Promise(() => {}));
    const { useDesconectarCanal } = await import("../useIntegracoes");
    const { result } = renderHook(() => useDesconectarCanal(), { wrapper });
    result.current.mutate("instagram");
    await waitFor(() => expect(qc.getQueryData<any[]>(["igig", "integracoes"])![0]).toMatchObject({ conectado: false, origem: "nenhuma", conta_externa: null }));
  });
});

describe("marca", () => {
  it("a removed marca leaves every list on the click; a new acesso is committed into the cofre on the answer", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "marcas", ""], [{ id: "m1" }, { id: "m2" }]);
    qc.setQueryData(["igig", "marcas", "c1"], [{ id: "m1" }]);
    del.mockReturnValue(new Promise(() => {}));
    const { useRemoverMarca, useCriarAcesso } = await import("../useMarca");
    const rem = renderHook(() => useRemoverMarca(), { wrapper });
    rem.result.current.mutate("m1");
    await waitFor(() => expect(qc.getQueryData(["igig", "marcas", ""])).toEqual([{ id: "m2" }]));
    expect(qc.getQueryData(["igig", "marcas", "c1"])).toEqual([]);

    qc.setQueryData(["igig", "cofre", "c1"], { cofre_configurado: true, itens: [] });
    post.mockResolvedValue({ id: "a1", cliente_id: "c1", rotulo: "IG", tem_senha: true });
    const cri = renderHook(() => useCriarAcesso(), { wrapper });
    cri.result.current.mutate({ cliente_id: "c1", rotulo: "IG", senha: "x" });
    await waitFor(() => expect(cri.result.current.isSuccess).toBe(true));
    expect(qc.getQueryData<any>(["igig", "cofre", "c1"]).itens).toEqual([{ id: "a1", cliente_id: "c1", rotulo: "IG", tem_senha: true }]);
  });
});

describe("orçamentos", () => {
  it("a refused orçamento is recusado in the list and the open detail on the click; a deleted rascunho leaves", async () => {
    const { qc, wrapper } = setup();
    const LISTA = ["igig", "orcamentos", "lista", {}];
    const DETALHE = ["igig", "orcamentos", "detalhe", "o1"];
    qc.setQueryData(LISTA, [{ id: "o1", status: "enviado" }, { id: "o2", status: "rascunho" }]);
    qc.setQueryData(DETALHE, { id: "o1", status: "enviado" });
    post.mockReturnValue(new Promise(() => {}));
    del.mockReturnValue(new Promise(() => {}));
    const { useOrcamentoMutations } = await import("../useOrcamentos");
    const { result } = renderHook(() => useOrcamentoMutations(), { wrapper });
    result.current.recusar.mutate({ id: "o1", motivo: "caro" });
    await waitFor(() => expect(qc.getQueryData<any[]>(LISTA)![0]).toMatchObject({ status: "recusado", motivo_recusa: "caro" }));
    expect(qc.getQueryData<any>(DETALHE).status).toBe("recusado");

    result.current.excluir.mutate("o2");
    await waitFor(() => expect(qc.getQueryData<any[]>(LISTA)!.map((o) => o.id)).toEqual(["o1"]));
  });
});

describe("pautas", () => {
  it("a deleted pauta leaves the list AND the calendar window on the click", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "pautas", "lista", ""], [{ id: "pa1" }, { id: "pa2" }]);
    qc.setQueryData(["igig", "pautas", "calendario", "2026-10-01", "2026-10-31", ""], { inicio: "a", fim: "b", itens: [{ id: "pa1" }] });
    del.mockReturnValue(new Promise(() => {}));
    const { useRemoverPauta } = await import("../usePautas");
    const { result } = renderHook(() => useRemoverPauta(), { wrapper });
    result.current.mutate({ id: "pa1" });
    await waitFor(() => expect(qc.getQueryData(["igig", "pautas", "lista", ""])).toEqual([{ id: "pa2" }]));
    expect(qc.getQueryData<any>(["igig", "pautas", "calendario", "2026-10-01", "2026-10-31", ""]).itens).toEqual([]);
  });
});

describe("produtos e serviços", () => {
  it("an edited produto is patched in every cached list on the click", async () => {
    const { qc, wrapper } = setup();
    qc.setQueryData(["igig", "produtos-servicos", "", ""], [{ id: "p1", nome: "Post", preco_base: 10 }]);
    qc.setQueryData(["igig", "produtos-servicos", "criacao", ""], [{ id: "p1", nome: "Post", preco_base: 10 }]);
    patch.mockReturnValue(new Promise(() => {}));
    const { useProdutoServicoMutations } = await import("../useProdutosServicos");
    const { result } = renderHook(() => useProdutoServicoMutations(), { wrapper });
    result.current.atualizar.mutate({ id: "p1", payload: { preco_base: 20 } });
    await waitFor(() => expect(qc.getQueryData<any[]>(["igig", "produtos-servicos", "", ""])![0].preco_base).toBe(20));
    expect(qc.getQueryData<any[]>(["igig", "produtos-servicos", "criacao", ""])![0].preco_base).toBe(20);
  });
});
