/** ImovelHistoricoCard — seed Timeline thread, pending approvals with Aprovar / Manter Vista, load more, states. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const m = vi.hoisted(() => ({ query: vi.fn(), mutate: vi.fn(), admin: { value: true }, mut: { isPending: false, isError: false, error: null as unknown } }));

vi.mock("@/hooks/useImovelHistorico", () => ({
  useImovelHistorico: m.query,
  useResolverAprovacao: () => ({ mutate: m.mutate, ...m.mut }),
}));
vi.mock("@noctusai/lib", () => ({ isOrgAdmin: () => m.admin.value }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useEffectiveSSOContext: () => ({}) }));

const ITENS = [
  { id: "h1", kind: "aprovacao", ocorrido_em: "2026-11-04T10:00:00Z", ator: { tipo: "julia", nome: "Julia" },
    payload: { campo: "valor_venda", rotulo: "valor de venda", de: 500000, para: 520000, acao: "aprovacao_pendente", status: "pendente", divergencia_id: "d1", conversa: { id: "c1", url: "/julia/conversas/c1" } } },
  { id: "h2", kind: "vista", ocorrido_em: "2026-11-03T10:00:00Z", ator: { tipo: "vista", nome: "Vista" },
    payload: { campo: "dormitorios", rotulo: "dormitórios", de: 2, para: 3, acao: "campo_atualizado" } },
  { id: "h3", kind: "vista_envio", ocorrido_em: "2026-11-02T10:00:00Z", ator: { tipo: "julia", nome: "Julia" },
    payload: { campo: "valor_venda", rotulo: "valor de venda", de: 1, para: 2, acao: "envio_vista_falhou", detalhe: "sem permissão" } },
  { id: "h4", kind: "nota", ocorrido_em: "2026-11-01T10:00:00Z", ator: { tipo: "usuario", nome: "Ana" }, payload: { corpo: "Chave com o porteiro" } },
];

function q(over: Record<string, unknown> = {}) {
  return { items: ITENS, showSkeleton: false, isRefreshing: false, isError: false, hasNextPage: false, isFetchingNextPage: false,
    fetchNextPage: vi.fn(), refetch: vi.fn(), data: { pages: [] }, ...over };
}

async function render() {
  const { render: r } = await import("@testing-library/react");
  const { ImovelHistoricoCard } = await import("./ImovelHistoricoCard");
  return r(<ImovelHistoricoCard codigo="AP1" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.admin.value = true;
  Object.assign(m.mut, { isPending: false, isError: false, error: null });
  m.query.mockReturnValue(q());
});

describe("ImovelHistoricoCard", () => {
  it("renderiza cada tipo: campo do Vista, envio que falhou, nota", async () => {
    const { container } = await render();
    const t = container.textContent ?? "";
    expect(t).toContain("Vista atualizou — dormitórios: 2 → 3");
    expect(t).toContain("Falha ao enviar ao Vista");
    expect(t).toContain("sem permissão");
    expect(t).toContain("Chave com o porteiro");
    expect(t).toContain("Aprovação pendente");
    expect(t).toContain("R$");
  });

  it("aprovação pendente: Aprovar e Manter Vista chamam o resolvedor, com link da conversa", async () => {
    const { getByTestId } = await render();
    const { fireEvent } = await import("@testing-library/react");
    expect(getByTestId("aprovacao-h1-conversa").getAttribute("href")).toBe("/julia/conversas/c1");
    fireEvent.click(getByTestId("aprovacao-h1-aprovar"));
    expect(m.mutate).toHaveBeenCalledWith({ historicoId: "h1", divergenciaId: "d1", escolha: "aprovar" });
    fireEvent.click(getByTestId("aprovacao-h1-manter-vista"));
    expect(m.mutate).toHaveBeenCalledWith({ historicoId: "h1", divergenciaId: "d1", escolha: "recusar" });
  });

  it("quem não é admin vê a aprovação sem botões", async () => {
    m.admin.value = false;
    const { queryByTestId } = await render();
    expect(queryByTestId("aprovacao-h1-aprovar")).toBeNull();
    expect(queryByTestId("aprovacao-h1")).toBeTruthy();
  });

  it("recusa do servidor aparece no item, nunca em silêncio", async () => {
    Object.assign(m.mut, { isError: true, error: new Error("409") });
    const { getByTestId } = await render();
    expect(getByTestId("aprovacao-h1-erro")).toBeTruthy();
  });

  it("carregar mais", async () => {
    const fetchNextPage = vi.fn();
    m.query.mockReturnValue(q({ hasNextPage: true, fetchNextPage }));
    const { getByText } = await render();
    (await import("@testing-library/react")).fireEvent.click(getByText("Carregar mais"));
    expect(fetchNextPage).toHaveBeenCalled();
  });

  it("carregando, vazio e erro", async () => {
    m.query.mockReturnValue(q({ items: [], showSkeleton: true }));
    expect((await render()).getByTestId("timeline-loading")).toBeTruthy();
    (await import("@testing-library/react")).cleanup();
    m.query.mockReturnValue(q({ items: [] }));
    expect((await render()).getByTestId("timeline-empty")).toBeTruthy();
    (await import("@testing-library/react")).cleanup();
    m.query.mockReturnValue(q({ items: [], isError: true, error: new Error("x"), data: undefined, failureCount: 3 }));
    const r = await render();
    expect(r.getByTestId("imovel-historico-erro")).toBeTruthy();
    expect(r.queryByTestId("timeline-empty")).toBeNull();
  });
});
