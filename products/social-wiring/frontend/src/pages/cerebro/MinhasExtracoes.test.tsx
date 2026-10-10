/**
 * MinhasExtracoes.test.tsx — FE-C: table, search/"Carregar mais", Nova Extração
 * (incl. inline new núcleo), Ver (edit/Salvar/Aplicar with per-target state),
 * Excluir, four states. API hooks mocked; no network.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: unknown) => v }));

const m = {
  marcas: vi.fn(),
  lista: vi.fn(),
  detalhe: vi.fn(),
  brains: vi.fn(),
  criarExtracao: vi.fn(),
  criarBrain: vi.fn(),
  atualizar: vi.fn(),
  aplicar: vi.fn(),
  excluir: vi.fn(),
};

vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => m.marcas() }));
vi.mock("@/hooks/useCerebro", () => ({
  CEREBRO_KEY: ["sw", "cerebro"],
  POLL_MS: 3000,
  useCerebroBrains: (id: any) => m.brains(id),
  useCriarBrain: () => ({ mutateAsync: m.criarBrain, isPending: false }),
}));
vi.mock("@/hooks/useExtracoes", () => ({
  PAGE_SIZE: 20,
  useExtracoes: (...a: any[]) => m.lista(...a),
  useExtracao: (id: any) => m.detalhe(id),
  useCriarExtracao: () => ({ mutateAsync: m.criarExtracao, isPending: false }),
  useAtualizarExtracao: () => ({ mutateAsync: m.atualizar, isPending: false }),
  useAplicarExtracao: () => ({ mutateAsync: m.aplicar, isPending: false }),
  useExcluirExtracao: () => ({ mutateAsync: m.excluir, isPending: false }),
}));

const q = (data: any, over: Partial<any> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

function ext(over: Partial<any> = {}) {
  return {
    id: "aaaaaaaa-1111",
    marca_id: "m1",
    name: "Pesquisa 1",
    source_kind: "text",
    source_url: null,
    status: "ready",
    error_message: null,
    targets: [
      { brain_id: "b1", brain_name: "Núcleo", applied_at: "2026-10-09T10:00:00Z" },
      { brain_id: "b2", brain_name: "Reels", applied_at: null },
    ],
    created_at: "2026-10-09T10:00:00Z",
    ...over,
  };
}

async function render() {
  const React = (await import("react")).default;
  const rr = await import("react-router-dom");
  const mod = await import("./MinhasExtracoes");
  const rtl = await import("@testing-library/react");
  const ue = (await import("@testing-library/user-event")).default;
  const el = React.createElement(
    rr.MemoryRouter,
    { initialEntries: ["/media-creation/cerebro/extracoes"] },
    React.createElement(mod.default),
  );
  return { ...rtl.render(el), rtl, user: ue.setup() };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  m.marcas.mockReturnValue({ data: [{ id: "m1", name: "Marca Um" }], isPending: false, isError: false });
  m.lista.mockReturnValue(q({ items: [ext(), ext({ id: "bbbbbbbb-2222", name: "Falhou", status: "error" })], total: 2 }));
  m.detalhe.mockReturnValue(q(undefined));
  m.brains.mockReturnValue(
    q([
      { id: "b1", name: "Núcleo" },
      { id: "b2", name: "Reels" },
    ]),
  );
  m.criarExtracao.mockResolvedValue({});
  m.criarBrain.mockResolvedValue({ id: "b3", name: "Novo" });
  m.atualizar.mockResolvedValue({});
  m.aplicar.mockResolvedValue({ applied: ["b2"], skipped: [] });
  m.excluir.mockResolvedValue(undefined);
});

describe("MinhasExtracoes", () => {
  it("renders the table with status labels", async () => {
    const { rtl } = await render();
    expect(rtl.screen.getAllByTestId("extracao-linha")).toHaveLength(2);
    expect(rtl.screen.getByText("Pronta")).toBeTruthy();
    expect(rtl.screen.getByText("Falha")).toBeTruthy();
    expect(rtl.screen.getAllByText("Núcleo, Reels")).toHaveLength(2);
    expect(rtl.screen.queryByText("Carregar mais")).toBeNull();
  });

  it("shows empty, skeleton and error states", async () => {
    m.lista.mockReturnValue(q({ items: [], total: 0 }));
    let r = await render();
    expect(r.rtl.screen.getByText("Nenhuma extração encontrada.")).toBeTruthy();
    r.unmount();
    m.lista.mockReturnValue(q(undefined, { showSkeleton: true }));
    r = await render();
    expect(r.rtl.screen.getByTestId("extracoes-skeleton")).toBeTruthy();
    r.unmount();
    const refetch = vi.fn();
    m.lista.mockReturnValue(q(undefined, { isError: true, refetch }));
    r = await render();
    await r.user.click(r.rtl.screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("keeps rows on screen while refreshing (no skeleton)", async () => {
    m.lista.mockReturnValue(q({ items: [ext()], total: 1 }, { isRefreshing: true }));
    const { rtl } = await render();
    expect(rtl.screen.getByText("Pesquisa 1")).toBeTruthy();
    expect(rtl.screen.getByText("Atualizando…")).toBeTruthy();
    expect(rtl.screen.queryByTestId("extracoes-skeleton")).toBeNull();
  });

  it("search and Carregar mais feed the list hook", async () => {
    m.lista.mockReturnValue(q({ items: [ext()], total: 5 }));
    const { rtl, user } = await render();
    await user.type(rtl.screen.getByPlaceholderText("Pesquisar..."), "abc");
    expect(m.lista).toHaveBeenLastCalledWith("m1", "abc", 20);
    await user.click(rtl.screen.getByText("Carregar mais"));
    expect(m.lista).toHaveBeenLastCalledWith("m1", "abc", 40);
  });

  it("creates an extraction from pasted text (no Url toggle)", async () => {
    const { rtl, user } = await render();
    await user.click(rtl.screen.getByText("Nova Extração"));
    expect(rtl.screen.queryByText(/Url/)).toBeNull();
    await user.click(rtl.screen.getByText("Criar Transcrição"));
    expect(rtl.screen.getByRole("alert").textContent).toContain("nome");
    await user.type(rtl.screen.getByLabelText("Nome:"), "Pesquisa 2");
    await user.click(rtl.screen.getByLabelText("Reels"));
    await user.type(rtl.screen.getByPlaceholderText("Cole aqui sua transcrição..."), "texto");
    await user.click(rtl.screen.getByText("Criar Transcrição"));
    expect(m.criarExtracao).toHaveBeenCalledWith({
      marca_id: "m1",
      name: "Pesquisa 2",
      brain_ids: ["b2"],
      text: "texto",
    });
  });

  it("creates a new núcleo inline and selects it", async () => {
    const { rtl, user } = await render();
    await user.click(rtl.screen.getByText("Nova Extração"));
    await user.click(rtl.screen.getByText("Clique aqui para criar um novo núcleo"));
    await user.type(rtl.screen.getByLabelText("Nome do novo núcleo"), "Novo");
    await user.click(rtl.screen.getByText("Criar núcleo"));
    expect(m.criarBrain).toHaveBeenCalledWith({ marca_id: "m1", name: "Novo" });
  });

  it("Ver: edits and saves the transcript, applies with per-target state", async () => {
    m.detalhe.mockReturnValue(q({ ...ext(), transcript: "original" }));
    const { rtl, user } = await render();
    await user.click(rtl.screen.getAllByText("Ver")[0]);
    expect(rtl.screen.getByText("Núcleo · Aplicado")).toBeTruthy();
    expect(rtl.screen.getByText("Reels · Pendente")).toBeTruthy();
    const apply = rtl.screen.getByText("Aplicar aos cérebros") as HTMLButtonElement;
    expect(apply.disabled).toBe(false);
    const salvar = rtl.screen.getByText("Salvar") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    await user.type(rtl.screen.getByLabelText("Transcrição"), " editado");
    expect(salvar.disabled).toBe(false);
    expect(apply.disabled).toBe(true); // unsaved edit must be saved before applying
    await user.click(salvar);
    expect(m.atualizar).toHaveBeenCalledWith({ id: "aaaaaaaa-1111", transcript: "original editado" });
  });

  it("Ver: apply posts and a non-ready extraction is read-only", async () => {
    m.detalhe.mockReturnValue(q({ ...ext(), transcript: "t" }));
    let r = await render();
    await r.user.click(r.rtl.screen.getAllByText("Ver")[0]);
    await r.user.click(r.rtl.screen.getByText("Aplicar aos cérebros"));
    expect(m.aplicar).toHaveBeenCalledWith({ id: "aaaaaaaa-1111" });
    r.unmount();
    m.detalhe.mockReturnValue(q({ ...ext({ status: "error", error_message: "Falhou feio" }), transcript: null }));
    r = await render();
    await r.user.click(r.rtl.screen.getAllByText("Ver")[0]);
    expect(r.rtl.screen.getByText("Falhou feio")).toBeTruthy();
    expect(r.rtl.screen.queryByText("Aplicar aos cérebros")).toBeNull();
    expect((r.rtl.screen.getByLabelText("Transcrição") as HTMLTextAreaElement).readOnly).toBe(true);
  });

  it("Excluir asks for confirmation then deletes", async () => {
    const { rtl, user } = await render();
    await user.click(rtl.screen.getAllByText("Excluir")[0]);
    expect(m.excluir).not.toHaveBeenCalled();
    const botoes = rtl.screen.getAllByText("Excluir");
    await user.click(botoes[botoes.length - 1]);
    expect(m.excluir).toHaveBeenCalledWith("aaaaaaaa-1111");
  });
});
