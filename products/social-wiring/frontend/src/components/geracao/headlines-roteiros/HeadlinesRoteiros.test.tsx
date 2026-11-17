/** "Headlines e Roteiros": the row (formato for all four, approval badge hidden while null) and the page states. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

afterEach(() => rtl.cleanup());

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const m = vi.hoisted(() => ({
  lista: vi.fn(),
  estruturas: vi.fn(),
  favoritar: vi.fn(),
  excluirH: vi.fn(),
  excluirR: vi.fn(),
  reprocessar: vi.fn(),
}));
vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }) }));
vi.mock("@/hooks/geracao/useHeadlinesRoteiros", () => ({
  HR_PAGE_SIZE: 20,
  useHeadlinesRoteiros: (f: unknown) => m.lista(f),
}));
vi.mock("@/hooks/geracao/useEstruturas", () => ({ useEstruturas: () => m.estruturas() }));
vi.mock("@/hooks/geracao/useHeadlineMutations", () => ({
  useFavoritarHeadline: () => ({ mutate: m.favoritar, isPending: false }),
  useExcluirHeadlines: () => ({ mutateAsync: m.excluirH, isPending: false }),
}));
vi.mock("@/hooks/geracao/useRoteiros", () => ({
  useExcluirRoteiros: () => ({ mutateAsync: m.excluirR, isPending: false }),
  useReprocessarRoteiro: () => ({ mutate: m.reprocessar, isPending: false }),
  useRoteiro: () => ({ data: undefined }),
}));
vi.mock("@/components/geracao/roteiro/RoteiroAvancadoModal", () => ({ RoteiroAvancadoModal: () => null }));
vi.mock("@/components/geracao/roteiro/EditarRoteiroModal", () => ({ EditarRoteiroModal: () => null }));
vi.mock("@/components/geracao/headlines/EditarHeadlineModal", () => ({ EditarHeadlineModal: () => null }));
vi.mock("@/components/geracao/PostEsteira", () => ({ NoPostBadge: () => null, CriarPostButton: () => null }));

import HeadlinesRoteiros from "@/pages/geracao/HeadlinesRoteiros";
import { itemHR } from "@/test/hrFixtures";

const base = { isRefreshing: false, isError: false, error: null, refetch: vi.fn() };
const comItens = (items: ReturnType<typeof itemHR>[]) => ({ ...base, data: { items, total: items.length }, showSkeleton: false });

function renderPage() {
  rtl.render(
    <MemoryRouter>
      <HeadlinesRoteiros />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.estruturas.mockReturnValue({ data: { items: [], total: 0 } });
  m.lista.mockReturnValue(comItens([itemHR()]));
});

describe("row", () => {
  it.each([
    ["reels", "Reels"],
    ["carrossel", "Carrossel"],
    ["stories", "Stories"],
    ["post", "Post"],
  ] as const)("shows the formato %s", (formato, rotulo) => {
    const item = itemHR();
    item.roteiro = { ...item.roteiro!, formato };
    m.lista.mockReturnValue(comItens([item]));
    renderPage();
    expect(rtl.screen.getByTestId("hr-formato").textContent).toBe(rotulo);
  });

  it("hides the approval badge while aprovacao is null and shows it once set", () => {
    renderPage();
    expect(rtl.screen.queryByTestId("hr-aprovacao")).toBeNull();
    rtl.cleanup();
    const item = itemHR();
    item.roteiro = { ...item.roteiro!, aprovacao: { estado: "pendente" } };
    m.lista.mockReturnValue(comItens([item]));
    renderPage();
    expect(rtl.screen.getByTestId("hr-aprovacao").textContent).toBe("Aguardando aprovação");
  });

  it("links the Estrutura chip and the source conversation", () => {
    renderPage();
    expect(rtl.screen.getByRole("link", { name: /@criador\.exemplo · #101/ }).getAttribute("href")).toBe("/media-creation/biblioteca/estruturas/e1");
    expect(rtl.screen.getByRole("link", { name: /Conversa A/ }).getAttribute("href")).toBe("/media-creation/chat?conversa=c1");
  });

  it("renders a roteiro without headline and offers no favoritar", () => {
    m.lista.mockReturnValue(comItens([itemHR({ headline: null, headline_texto: "Texto livre" })]));
    renderPage();
    expect(rtl.screen.getByText("Texto livre")).toBeTruthy();
    expect(rtl.screen.queryByRole("button", { name: /Favoritar/ })).toBeNull();
  });

  it("offers Criar roteiro when the headline has none", () => {
    m.lista.mockReturnValue(comItens([itemHR({ roteiro: null })]));
    renderPage();
    expect(rtl.screen.getByTestId("hr-sem-roteiro")).toBeTruthy();
    // header button + the row's own
    expect(rtl.screen.getAllByRole("button", { name: "Criar roteiro" })).toHaveLength(2);
  });

  it("reuses the favoritar mutation", async () => {
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: /Favoritar Headline de teste/ }));
    expect(m.favoritar).toHaveBeenCalledWith({ id: "h1", favoritar: true }, expect.any(Object));
  });
});

describe("status tolerance", () => {
  it("renders the perguntas status with its label", () => {
    const item = itemHR();
    item.roteiro = { ...item.roteiro!, status: "perguntas" };
    m.lista.mockReturnValue(comItens([item]));
    renderPage();
    expect(rtl.screen.getByTestId("hr-roteiro").textContent).toContain("Perguntas");
  });

  it("renders an unknown status as a neutral label, not blank", () => {
    const item = itemHR();
    item.roteiro = { ...item.roteiro!, status: "novo_status" as never };
    m.lista.mockReturnValue(comItens([item]));
    renderPage();
    expect(rtl.screen.getByTestId("hr-status-desconhecido").textContent).toBe("Em andamento");
  });
});

describe("states", () => {
  it("shows the skeleton while pending without data", () => {
    m.lista.mockReturnValue({ ...base, data: undefined, showSkeleton: true });
    renderPage();
    expect(rtl.screen.getByTestId("hr-skeleton")).toBeTruthy();
  });

  it("renders the coded refusal, not silence", () => {
    m.lista.mockReturnValue({ ...base, data: undefined, showSkeleton: false, isError: true, error: Object.assign(new Error("x"), { code: "estrutura_inativa", status: 409 }) });
    renderPage();
    expect(rtl.screen.getByRole("alert").textContent).toContain("Esta estrutura não está ativa.");
  });

  it("explains the empty list", () => {
    m.lista.mockReturnValue(comItens([]));
    renderPage();
    expect(rtl.screen.getByTestId("hr-vazio")).toBeTruthy();
  });

  it("confirms before deleting a headline", async () => {
    m.excluirH.mockResolvedValue({ excluidos: 1 });
    renderPage();
    await userEvent.click(rtl.screen.getByRole("button", { name: /Excluir Headline de teste/ }));
    await userEvent.click(await rtl.screen.findByRole("button", { name: "Excluir" }));
    await rtl.waitFor(() => expect(m.excluirH).toHaveBeenCalledWith(["h1"]));
  });
});
