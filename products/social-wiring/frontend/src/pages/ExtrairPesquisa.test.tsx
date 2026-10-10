/**
 * ExtrairPesquisa.test.tsx — Extrair Pesquisa page against a mocked API
 * (real React Query + real hooks): source tabs, grid metrics ("—" for null),
 * selection cap, "Selecionar os N mais recentes", submit → polling → result
 * links, 409/429/503 toasts, non-analysable card disabled, active-job resume.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet, mockPost, toastMock } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => ({ api: { get: mockGet, post: mockPost } }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca Um" }], isPending: false, isError: false }),
}));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  vi.useRealTimers();
});

const FONTES = [
  { kind: "instagram_media", account_id: "a1", label: "casa_um", total_posts: 3, last_synced_at: null },
  { kind: "mc_post", account_id: null, label: "Posts criados", total_posts: 1, last_synced_at: null },
];

function post(over: Partial<any> = {}) {
  return {
    kind: "instagram_media",
    account_id: "a1",
    id: "p1",
    url: "https://example.test/p1",
    thumbnail_url: null,
    published_at: "2026-10-01T10:00:00Z",
    texto: "Texto do post um com bastante conteúdo",
    analisavel: true,
    plays: 1500,
    likes: null,
    comments: 12,
    extra: {},
    extraido: { pesquisa: null, assuntos_virais: null },
    ...over,
  };
}

const POSTS = [
  post(),
  post({ id: "p2", texto: "Segundo post de teste com texto", plays: null }),
  post({ id: "p3", texto: "curto", analisavel: false }),
];

function job(over: Partial<any> = {}) {
  return {
    id: "j1",
    marca_id: "m1",
    tipos: ["pesquisa"],
    status: "queued",
    step: null,
    progress: 0,
    total_tarefas: 2,
    tarefas_processadas: 0,
    tarefas_com_erro: 0,
    itens_salvos: 0,
    itens_ignorados: 0,
    itens_descartados: 0,
    assuntos_salvos: 0,
    assuntos_ignorados: 0,
    ja_extraidos_pulados: 0,
    erro: null,
    created_at: "2026-10-09T10:00:00Z",
    started_at: null,
    finished_at: null,
    ...over,
  };
}

let limites: any;
let jobGet: ReturnType<typeof vi.fn<() => any>>;

function wire() {
  mockGet.mockImplementation(async (url: string) => {
    const w = (data: unknown) => ({ success: true, data });
    if (url.includes("/fontes/posts")) return w({ posts: POSTS, next_cursor: null });
    if (url.includes("/fontes")) return w(FONTES);
    if (url.includes("/extracoes/limites")) return w(limites);
    if (/\/extracoes\/j1$/.test(url)) return w(jobGet());
    if (url.includes("/extracoes")) return w([]);
    throw new Error(`unmocked GET ${url}`);
  });
}

async function renderPage() {
  const React = (await import("react")).default;
  const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
  const { MemoryRouter } = await import("react-router-dom");
  const { default: Page } = await import("./ExtrairPesquisa");
  const rtl = await import("@testing-library/react");
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = rtl.render(
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(MemoryRouter, null, React.createElement(Page)),
    ),
  );
  return { rtl, ...ui };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  limites = {
    worker_ativo: true,
    max_posts_por_job: 2,
    extracoes_restantes_hoje: 5,
    tarefas_restantes_hoje_org: 50,
    extracao_ativa_id: null,
  };
  jobGet = vi.fn(() => job());
  wire();
});

describe("ExtrairPesquisa", () => {
  it("renders source tabs with counts and the grid with compact metrics and em-dash for null", async () => {
    const { rtl } = await renderPage();
    expect(await rtl.screen.findByRole("tab", { name: /@casa_um \(3\)/ })).toBeTruthy();
    expect(rtl.screen.getByRole("tab", { name: /Posts criados \(1\)/ })).toBeTruthy();
    const cards = await rtl.screen.findAllByTestId("post-card");
    expect(cards).toHaveLength(3);
    expect(cards[0].textContent).toContain("Views 1.5K");
    expect(cards[0].textContent).toContain("Likes —");
    expect(cards[1].textContent).toContain("Views —");
  });

  it("disables a non-analysable card", async () => {
    const { rtl } = await renderPage();
    const cards = await rtl.screen.findAllByTestId("post-card");
    expect(cards[2].getAttribute("title")).toBe("Sem texto para analisar");
    const box = cards[2].querySelector("button[role=checkbox]") as HTMLButtonElement;
    expect(box.disabled).toBe(true);
  });

  it("respects the max selection and selects the N most recent", async () => {
    const { rtl } = await renderPage();
    await rtl.screen.findAllByTestId("post-card");
    expect(await rtl.screen.findByText("0 de 2 selecionados")).toBeTruthy();
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Selecionar os 2 mais recentes" }));
    });
    expect(rtl.screen.getByText("2 de 2 selecionados")).toBeTruthy();
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Limpar" }));
    });
    expect(rtl.screen.getByText("0 de 2 selecionados")).toBeTruthy();
  });

  it("submits, polls the job until completed and shows the result links", async () => {
    mockPost.mockResolvedValue({ success: true, data: job() });
    const { rtl } = await renderPage();
    await rtl.screen.findAllByTestId("post-card");
    await rtl.screen.findByText("0 de 2 selecionados");
    vi.useFakeTimers({ toFake: ["setInterval", "setTimeout", "clearInterval", "clearTimeout"] });
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Selecionar os 2 mais recentes" }));
    });
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Extrair (2)" }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/api/media-creation/pesquisa/extracoes",
      expect.objectContaining({ marca_id: "m1", tipos: ["pesquisa"], reextrair: false }),
    );
    expect(rtl.screen.getByRole("button", { name: "Cancelar" })).toBeTruthy();

    jobGet.mockReturnValue(job({ status: "running", progress: 50, step: "Analisando posts" }));
    await rtl.act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(rtl.screen.getByText("Analisando posts")).toBeTruthy();
    expect(rtl.screen.getByText("50%")).toBeTruthy();

    jobGet.mockReturnValue(job({ status: "completed", progress: 100, itens_salvos: 4, itens_ignorados: 1, assuntos_salvos: 2 }));
    await rtl.act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await rtl.act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(rtl.screen.getByText("Extração concluída!")).toBeTruthy();
    expect(rtl.screen.getByText(/4 item\(ns\) novo\(s\) · 1 já existente\(s\) · 2 assunto\(s\)/)).toBeTruthy();
    expect(rtl.screen.getByRole("link", { name: "Ver pendentes em Minha Pesquisa" }).getAttribute("href")).toBe(
      "/media-creation/pesquisa?status=pending",
    );
    expect(rtl.screen.getByRole("link", { name: "Ver assuntos virais" }).getAttribute("href")).toBe(
      "/media-creation/pesquisa?tab=assuntos-virais",
    );
    expect(toastMock.success).toHaveBeenCalledWith("Extração concluída!");

    // Terminal ⇒ polling stops.
    const calls = jobGet.mock.calls.length;
    await rtl.act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(jobGet.mock.calls.length).toBe(calls);
  });

  it.each([
    [409, "Já existe uma extração em andamento"],
    [429, "Limite diário de extrações atingido"],
    [503, "Extração indisponível no momento"],
  ])("shows the %s detail as a toast and refetches limits", async (_status, detail) => {
    mockPost.mockRejectedValue(new Error(detail));
    const { rtl } = await renderPage();
    await rtl.screen.findAllByTestId("post-card");
    await rtl.screen.findByText("0 de 2 selecionados");
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Selecionar os 2 mais recentes" }));
    });
    const before = mockGet.mock.calls.filter(([u]) => String(u).includes("/extracoes/limites")).length;
    await rtl.act(async () => {
      rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Extrair (2)" }));
    });
    await rtl.waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(detail));
    await rtl.waitFor(() =>
      expect(mockGet.mock.calls.filter(([u]) => String(u).includes("/extracoes/limites")).length).toBeGreaterThan(before),
    );
  });

  it("resumes an active job on mount via limites.extracao_ativa_id and blocks a new submit", async () => {
    limites.extracao_ativa_id = "j1";
    jobGet.mockReturnValue(job({ status: "running", progress: 30, step: "Retomado" }));
    const { rtl } = await renderPage();
    expect(await rtl.screen.findByText("Retomado")).toBeTruthy();
    expect(rtl.screen.getByRole("button", { name: "Cancelar" })).toBeTruthy();
    expect(await rtl.screen.findByText("Já existe uma extração em andamento")).toBeTruthy();
  });
});
