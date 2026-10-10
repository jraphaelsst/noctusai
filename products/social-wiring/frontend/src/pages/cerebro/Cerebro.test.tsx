/**
 * Cerebro.test.tsx — FE-A: list (Sistema + custom, badges, progress, create),
 * bio card (Instagram prefill only with an account), editor (save, 409 modal,
 * synthesis read-only, import modal validation) and the four states.
 * API hooks are mocked; no network.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const m = {
  marcas: vi.fn(),
  brains: vi.fn(),
  brain: vi.fn(),
  perfil: vi.fn(),
  ig: vi.fn(),
  criar: vi.fn(),
  salvarPerfil: vi.fn(),
  salvarConteudo: vi.fn(),
  renomear: vi.fn(),
  excluir: vi.fn(),
  enviar: vi.fn(),
};

vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => m.marcas() }));
vi.mock("@/hooks/useCerebro", () => ({
  useCerebroBrains: (id: any) => m.brains(id),
  useCerebroBrain: (id: any) => m.brain(id),
  useCerebroPerfil: (id: any) => m.perfil(id),
  useBioInstagram: (id: any) => m.ig(id),
  useCriarBrain: () => ({ mutateAsync: m.criar, isPending: false }),
  useSalvarPerfil: () => ({ mutateAsync: m.salvarPerfil, isPending: false }),
  useSalvarConteudo: () => ({ mutateAsync: m.salvarConteudo, isPending: false }),
  useRenomearBrain: () => ({ mutateAsync: m.renomear, isPending: false }),
  useExcluirBrain: () => ({ mutateAsync: m.excluir, isPending: false }),
  useEnviarArquivo: () => ({ mutateAsync: m.enviar, isPending: false }),
}));

function summary(over: Partial<any> = {}) {
  return {
    id: "b1",
    marca_id: "m1",
    kind: "sistema",
    template_slug: "nucleo-de-influencia",
    name: "Núcleo de Influência",
    status: "vazio",
    content_chars: 0,
    answered: 0,
    total_questions: 15,
    synthesis_status: "idle",
    updated_at: "2026-10-09T10:00:00Z",
    ...over,
  };
}

function detail(over: Partial<any> = {}) {
  return {
    ...summary({ id: "c1", kind: "custom", template_slug: null, name: "Reels Instagram", answered: null, total_questions: null, status: "pronto", content_chars: 5 }),
    content: "Olá!!",
    content_version: 3,
    synthesis_error: null,
    synthesized_at: null,
    template: null,
    answers: [],
    imports: [],
    ...over,
  };
}

const q = (data: any, over: Partial<any> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

async function render(path: string, Comp: "lista" | "editor") {
  const React = (await import("react")).default;
  const rr = await import("react-router-dom");
  const mod =
    Comp === "lista" ? await import("./CerebroLista") : await import("./CerebroEditor");
  const rtl = await import("@testing-library/react");
  const el = React.createElement(
    rr.MemoryRouter,
    { initialEntries: [path] },
    React.createElement(
      rr.Routes,
      null,
      React.createElement(rr.Route, { path: "/media-creation/cerebro", element: React.createElement(mod.default) }),
      React.createElement(rr.Route, { path: "/media-creation/cerebro/:brainId", element: Comp === "lista" ? React.createElement("div", null, "EDITOR-ROTA") : React.createElement(mod.default) }),
    ),
  );
  return { ...rtl.render(el), rtl };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  m.marcas.mockReturnValue({ data: [{ id: "m1", name: "Marca Um" }, { id: "m2", name: "Marca Dois" }], isPending: false, isError: false });
  m.brains.mockReturnValue(
    q([
      summary(),
      summary({ id: "b2", name: "Método do Especialista", answered: 2, total_questions: 7, status: "pronto", content_chars: 40 }),
      summary({ id: "b3", kind: "custom", template_slug: null, name: "Reels Instagram", answered: null, total_questions: null }),
    ]),
  );
  m.perfil.mockReturnValue(q({ marca_id: "m1", bio: "Minha bio", updated_at: null }));
  m.ig.mockReturnValue({ temConta: false, bio: null });
  m.brain.mockReturnValue(q(detail()));
  m.criar.mockResolvedValue(summary({ id: "novo", kind: "custom", name: "Novo" }));
  m.salvarPerfil.mockResolvedValue({});
  m.salvarConteudo.mockResolvedValue({});
  m.enviar.mockResolvedValue({});
});

describe("CerebroLista", () => {
  it("lists Sistema and custom brains with badge, status and progress", async () => {
    const { rtl } = await render("/media-creation/cerebro", "lista");
    expect(rtl.screen.getAllByTestId("cerebro-card")).toHaveLength(3);
    expect(rtl.screen.getAllByText("Sistema")).toHaveLength(2);
    expect(rtl.screen.getAllByText("Vazio")).toHaveLength(2);
    expect(rtl.screen.getByText("2 de 7 respondidas")).toBeTruthy();
    expect(rtl.screen.getByText("0 de 15 respondidas")).toBeTruthy();
    const links = rtl.screen.getAllByText("Acessar Cérebro").map((a) => a.closest("a")?.getAttribute("href"));
    // untouched Sistema -> questionnaire; answered Sistema and custom -> editor
    expect(links).toEqual([
      "/media-creation/cerebro/b1/perguntas",
      "/media-creation/cerebro/b2",
      "/media-creation/cerebro/b3",
    ]);
  });

  it("shows the skeleton, the empty state and the error state", async () => {
    m.brains.mockReturnValue(q(undefined, { showSkeleton: true }));
    let r = await render("/media-creation/cerebro", "lista");
    expect(r.rtl.screen.getByTestId("cerebro-skeleton")).toBeTruthy();
    r.rtl.cleanup();

    m.brains.mockReturnValue(q([]));
    r = await render("/media-creation/cerebro", "lista");
    expect(r.rtl.screen.getByText("Nenhum cérebro encontrado.")).toBeTruthy();
    r.rtl.cleanup();

    const refetch = vi.fn();
    m.brains.mockReturnValue(q(undefined, { isError: true, refetch }));
    r = await render("/media-creation/cerebro", "lista");
    r.rtl.fireEvent.click(r.rtl.screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("keeps cards visible while refreshing (marca switch)", async () => {
    m.brains.mockReturnValue(q([summary()], { isRefreshing: true }));
    const { rtl } = await render("/media-creation/cerebro", "lista");
    expect(rtl.screen.getByText("Núcleo de Influência")).toBeTruthy();
    expect(rtl.screen.getByRole("status").textContent).toContain("Atualizando");
  });

  it("creates a custom brain and navigates to its editor", async () => {
    const { rtl } = await render("/media-creation/cerebro", "lista");
    rtl.fireEvent.click(rtl.screen.getByText("Criar Cérebro"));
    rtl.fireEvent.change(rtl.screen.getByLabelText("Nome do Cérebro:"), { target: { value: "  Novo  " } });
    rtl.fireEvent.click(rtl.screen.getByText("Criar"));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalledWith({ marca_id: "m1", name: "Novo" }));
    await rtl.screen.findByText("EDITOR-ROTA");
  });

  it("switching marca re-queries brains for the new marca", async () => {
    const { rtl } = await render("/media-creation/cerebro", "lista");
    rtl.fireEvent.change(rtl.screen.getByLabelText("Marca"), { target: { value: "m2" } });
    expect(m.brains).toHaveBeenLastCalledWith("m2");
  });
});

describe("BioPerfilCard", () => {
  it("saves the edited bio", async () => {
    const { rtl } = await render("/media-creation/cerebro", "lista");
    const ta = rtl.screen.getByLabelText("Texto da bio") as HTMLTextAreaElement;
    expect(ta.value).toBe("Minha bio");
    rtl.fireEvent.change(ta, { target: { value: "Nova bio" } });
    rtl.fireEvent.click(rtl.screen.getByText("Salvar"));
    await rtl.waitFor(() => expect(m.salvarPerfil).toHaveBeenCalledWith({ marca_id: "m1", bio: "Nova bio" }));
  });

  it("offers the Instagram bio only with a connected account, and only fills the field", async () => {
    let r = await render("/media-creation/cerebro", "lista");
    expect(r.rtl.screen.queryByText("Usar a bio do Instagram")).toBeNull();
    r.rtl.cleanup();

    m.ig.mockReturnValue({ temConta: true, bio: "Bio do IG" });
    r = await render("/media-creation/cerebro", "lista");
    r.rtl.fireEvent.click(r.rtl.screen.getByText("Usar a bio do Instagram"));
    expect((r.rtl.screen.getByLabelText("Texto da bio") as HTMLTextAreaElement).value).toBe("Bio do IG");
    expect(m.salvarPerfil).not.toHaveBeenCalled();
  });
});

describe("CerebroEditor", () => {
  it("applies changes with the loaded content_version", async () => {
    const { rtl } = await render("/media-creation/cerebro/c1", "editor");
    expect(rtl.screen.getByText("5 caracteres")).toBeTruthy();
    const apply = rtl.screen.getByText("Aplicar Alterações") as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    rtl.fireEvent.change(rtl.screen.getByLabelText("Texto do cérebro"), { target: { value: "Olá mundo" } });
    expect(rtl.screen.getByText("Alterações não aplicadas")).toBeTruthy();
    rtl.fireEvent.click(rtl.screen.getByText("Aplicar Alterações"));
    await rtl.waitFor(() =>
      expect(m.salvarConteudo).toHaveBeenCalledWith({ id: "c1", content: "Olá mundo", expected_version: 3 }),
    );
  });

  it("shows the conflict modal on 409 and Recarregar refetches", async () => {
    const refetch = vi.fn();
    m.brain.mockReturnValue(q(detail(), { refetch }));
    m.salvarConteudo.mockRejectedValue(Object.assign(new Error("[409] O conteúdo do cérebro mudou enquanto você editava."), { status: 409 }));
    const { rtl } = await render("/media-creation/cerebro/c1", "editor");
    rtl.fireEvent.change(rtl.screen.getByLabelText("Texto do cérebro"), { target: { value: "x" } });
    rtl.fireEvent.click(rtl.screen.getByText("Aplicar Alterações"));
    await rtl.screen.findByText("O conteúdo mudou (um arquivo ou transcrição foi anexado)");
    expect(rtl.screen.getByText("Copiar meu texto")).toBeTruthy();
    rtl.fireEvent.click(rtl.screen.getByText("Recarregar"));
    expect(refetch).toHaveBeenCalled();
  });

  it("is read-only with a banner while synthesis runs", async () => {
    m.brain.mockReturnValue(q(detail({ synthesis_status: "processing" })));
    const { rtl } = await render("/media-creation/cerebro/c1", "editor");
    expect(rtl.screen.getByText("Gerando cérebro…")).toBeTruthy();
    expect((rtl.screen.getByLabelText("Texto do cérebro") as HTMLTextAreaElement).readOnly).toBe(true);
  });

  it("Sistema: badge + Responder perguntas, no rename/delete; custom: rename/delete", async () => {
    m.brain.mockReturnValue(q(detail({ kind: "sistema", template_slug: "x", name: "Método" })));
    let r = await render("/media-creation/cerebro/c1", "editor");
    expect(r.rtl.screen.getByText("Sistema")).toBeTruthy();
    expect(r.rtl.screen.getByText("Responder perguntas")).toBeTruthy();
    expect(r.rtl.screen.queryByLabelText("Renomear Cérebro")).toBeNull();
    r.rtl.cleanup();

    m.brain.mockReturnValue(q(detail()));
    r = await render("/media-creation/cerebro/c1", "editor");
    expect(r.rtl.screen.queryByText("Responder perguntas")).toBeNull();
    r.rtl.fireEvent.click(r.rtl.screen.getByLabelText("Excluir Cérebro"));
    expect(r.rtl.screen.getByText("Tem certeza? Você realmente deseja deletar este Cérebro?")).toBeTruthy();
    r.rtl.fireEvent.click(r.rtl.screen.getByText("Deletar"));
    await r.rtl.waitFor(() => expect(m.excluir).toHaveBeenCalledWith("c1"));
  });

  it("lists imports with status chips", async () => {
    m.brain.mockReturnValue(
      q(
        detail({
          imports: [
            { id: "i1", kind: "file", filename: "roteiro.pdf", source_url: null, status: "appended", chars_appended: 1200, error_message: null, created_at: "" },
            { id: "i2", kind: "file", filename: "x.docx", source_url: null, status: "error", chars_appended: null, error_message: "Não foi possível ler texto deste arquivo.", created_at: "" },
          ],
        }),
      ),
    );
    const { rtl } = await render("/media-creation/cerebro/c1", "editor");
    expect(rtl.screen.getByText("Anexado")).toBeTruthy();
    expect(rtl.screen.getByText("Não foi possível ler texto deste arquivo.")).toBeTruthy();
  });

  it("shows skeleton / error states without lying", async () => {
    m.brain.mockReturnValue(q(undefined, { showSkeleton: true }));
    let r = await render("/media-creation/cerebro/c1", "editor");
    expect(r.rtl.screen.getByTestId("editor-skeleton")).toBeTruthy();
    r.rtl.cleanup();
    m.brain.mockReturnValue(q(undefined, { isError: true }));
    r = await render("/media-creation/cerebro/c1", "editor");
    expect(r.rtl.screen.getByText("Tentar novamente")).toBeTruthy();
  });
});

describe("ImportarArquivoModal", () => {
  async function abrir() {
    const r = await render("/media-creation/cerebro/c1", "editor");
    r.rtl.fireEvent.click(r.rtl.screen.getByText("Enviar arquivo"));
    return r;
  }
  const pick = (rtl: any, file: File) =>
    rtl.fireEvent.change(rtl.screen.getByTestId("importar-arquivo-input"), { target: { files: [file] } });

  it("requires a file, rejects bad formats and oversize, uploads a valid one", async () => {
    const { rtl } = await abrir();
    rtl.fireEvent.click(rtl.screen.getByText("Enviar"));
    expect(rtl.screen.getByText("Selecione um arquivo antes de enviar.")).toBeTruthy();

    pick(rtl, new File(["x"], "foto.png", { type: "image/png" }));
    expect(rtl.screen.getByText("Formato não suportado. Use PDF, DOCX, TXT, MD ou CSV.")).toBeTruthy();

    const grande = new File(["x"], "g.pdf");
    Object.defineProperty(grande, "size", { value: 21 * 1024 * 1024 });
    pick(rtl, grande);
    expect(rtl.screen.getByText("Arquivo muito grande. Limite: 20 MB.")).toBeTruthy();
    expect(m.enviar).not.toHaveBeenCalled();

    const ok = new File(["conteudo"], "roteiro.md");
    pick(rtl, ok);
    rtl.fireEvent.click(rtl.screen.getByText("Enviar"));
    await rtl.waitFor(() => expect(m.enviar).toHaveBeenCalledWith({ id: "c1", file: ok }));
  });
});
