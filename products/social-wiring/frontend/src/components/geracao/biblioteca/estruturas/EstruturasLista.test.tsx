/** The Estruturas list: admin-only controls, honest states, URL-driven filters, paging. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const m = vi.hoisted(() => ({ lista: vi.fn() }));
vi.mock("@/hooks/geracao/useEstruturas", () => ({
  ESTRUTURAS_POR_PAGINA: 20,
  useEstruturas: (...a: unknown[]) => m.lista(...a),
}));

import { resumo } from "@/test/estruturasFixtures";
import { EstruturasLista } from "./EstruturasLista";
import { FILTROS_ESTRUTURAS_VAZIOS, type FiltrosEstruturas } from "./filtros";

const estado = (items: ReturnType<typeof resumo>[], over: Record<string, unknown> = {}) => ({
  data: { items, total: items.length },
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  error: null,
  failureCount: 0,
  isFetching: false,
  refetch: vi.fn(),
  ...over,
});

function renderLista(over: { filtros?: FiltrosEstruturas; isAdmin?: boolean; perfilId?: string } = {}) {
  const onFiltros = vi.fn();
  rtl.render(
    <MemoryRouter>
      <EstruturasLista filtros={over.filtros ?? FILTROS_ESTRUTURAS_VAZIOS} onFiltros={onFiltros} isAdmin={over.isAdmin ?? false} marcaId="m1" perfilId={over.perfilId} />
    </MemoryRouter>,
  );
  return { onFiltros };
}

beforeEach(() => {
  vi.clearAllMocks();
  m.lista.mockReturnValue(estado([resumo(), resumo({ id: "e2", codigo: 102, formula_headline: "Segunda fórmula" })]));
});

describe("member view", () => {
  it("renders cards linking to the detail and NO admin controls", () => {
    renderLista();
    expect(rtl.screen.getByRole("link", { name: /Como \[autoridade teórica\]/ }).getAttribute("href")).toBe("/media-creation/biblioteca/estruturas/e1");
    expect(rtl.screen.getByText("Estruturas (2)")).toBeTruthy();
    expect(rtl.screen.queryByRole("button", { name: "Pendentes de revisão" })).toBeNull();
    expect(rtl.screen.queryByLabelText("Situação")).toBeNull();
  });

  it("never asks the server for admin filters", () => {
    renderLista({ filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, status: "rascunho", pendentes: true } });
    const f = m.lista.mock.calls[0]![0];
    expect(f.status).toBeUndefined();
    expect(f.somentePendentesRevisao).toBe(false);
    expect(f.revisaoPorDesuso).toBe(false);
  });

  it("offers no 24-month filter to members", () => {
    renderLista();
    expect(rtl.screen.queryByRole("button", { name: "Sem uso há 24 meses" })).toBeNull();
  });

  it("shows no admin badge even if a row somehow carried a status (only the server's fields render)", () => {
    renderLista();
    expect(rtl.screen.queryByText("Pendente de revisão")).toBeNull();
    expect(rtl.screen.queryByText("Rascunho")).toBeNull();
  });
});

describe("admin view", () => {
  it("offers Situação + Pendentes de revisão and shows the admin badges the server sent", async () => {
    m.lista.mockReturnValue(estado([resumo({ status: "rascunho", pendente_revisao: true })]));
    const { onFiltros } = renderLista({ isAdmin: true });
    expect(rtl.screen.getByText("Pendente de revisão")).toBeTruthy();
    expect(rtl.screen.getByText("Rascunho")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Pendentes de revisão" }));
    expect(onFiltros).toHaveBeenCalledWith({ ...FILTROS_ESTRUTURAS_VAZIOS, pendentes: true, pagina: 1 });
    await userEvent.selectOptions(rtl.screen.getByLabelText("Situação"), "rascunho");
    expect(onFiltros).toHaveBeenLastCalledWith({ ...FILTROS_ESTRUTURAS_VAZIOS, status: "rascunho", pagina: 1 });
  });

  it("sends the admin filters to the query", () => {
    renderLista({ isAdmin: true, filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, status: "rascunho", pendentes: true } });
    const f = m.lista.mock.calls[0]![0];
    expect(f.status).toBe("rascunho");
    expect(f.somentePendentesRevisao).toBe(true);
  });
});

describe("admin 24-month filter", () => {
  it("toggles desuso and sends it to the query", async () => {
    const { onFiltros } = renderLista({ isAdmin: true });
    await userEvent.click(rtl.screen.getByRole("button", { name: "Sem uso há 24 meses" }));
    expect(onFiltros).toHaveBeenCalledWith({ ...FILTROS_ESTRUTURAS_VAZIOS, desuso: true, pagina: 1 });
    rtl.cleanup();
    renderLista({ isAdmin: true, filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, desuso: true } });
    expect(m.lista.mock.calls.at(-1)![0].revisaoPorDesuso).toBe(true);
  });
});

describe("filters + paging", () => {
  it("formato / objetivo chips toggle (aria-pressed) and reset to page 1", async () => {
    const { onFiltros } = renderLista({ filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, formatos: ["reels"], pagina: 4 } });
    expect(rtl.screen.getByRole("button", { name: "Reels" }).getAttribute("aria-pressed")).toBe("true");
    await userEvent.click(rtl.screen.getByRole("button", { name: "Carrossel" }));
    expect(onFiltros).toHaveBeenCalledWith({ ...FILTROS_ESTRUTURAS_VAZIOS, formatos: ["reels", "carrossel"], pagina: 1 });
    await userEvent.click(rtl.screen.getByRole("button", { name: "Venda" }));
    expect(onFiltros).toHaveBeenLastCalledWith(expect.objectContaining({ objetivos: ["venda"], pagina: 1 }));
  });

  it("the search is debounced into the filters and restarts on page 1", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { onFiltros } = renderLista({ filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, pagina: 3 } });
      await userEvent.type(rtl.screen.getByLabelText("Buscar estruturas"), "gancho");
      expect(onFiltros).not.toHaveBeenCalled();
      await rtl.act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(onFiltros).toHaveBeenCalledWith({ ...FILTROS_ESTRUTURAS_VAZIOS, busca: "gancho", pagina: 1 });
    } finally {
      vi.useRealTimers();
    }
  });

  it("pages with Anterior / Próxima using the server total", async () => {
    m.lista.mockReturnValue(estado([resumo()], { data: { items: [resumo()], total: 45 } }));
    const { onFiltros } = renderLista({ filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, pagina: 2 } });
    expect(rtl.screen.getByText("Página 2 de 3")).toBeTruthy();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Próxima" }));
    expect(onFiltros).toHaveBeenCalledWith(expect.objectContaining({ pagina: 3 }));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Anterior" }));
    expect(onFiltros).toHaveBeenLastCalledWith(expect.objectContaining({ pagina: 1 }));
    // the query asks for the right window
    expect(m.lista.mock.calls[0]![0]).toMatchObject({ limit: 20, offset: 20 });
  });
});

describe("states", () => {
  it("skeleton while the first load runs", () => {
    m.lista.mockReturnValue({ ...estado([]), data: undefined, showSkeleton: true });
    renderLista();
    expect(rtl.screen.getByLabelText("Carregando estruturas")).toBeTruthy();
    expect(rtl.screen.queryByText("Nenhuma estrutura encontrada")).toBeNull();
  });

  it("error with no data is a retryable block, never an empty state", async () => {
    const refetch = vi.fn();
    m.lista.mockReturnValue({ ...estado([]), data: undefined, isError: true, error: new Error("x"), refetch });
    renderLista();
    expect(rtl.screen.queryByText("Nenhuma estrutura encontrada")).toBeNull();
    await userEvent.click(rtl.screen.getByRole("button", { name: /Tentar novamente/ }));
    expect(refetch).toHaveBeenCalled();
  });

  it("empty says why: nothing yet vs nothing matches the filters; profile page says so", () => {
    m.lista.mockReturnValue(estado([]));
    renderLista();
    expect(rtl.screen.getByText(/ainda não tem estruturas publicadas/)).toBeTruthy();
    rtl.cleanup();
    renderLista({ filtros: { ...FILTROS_ESTRUTURAS_VAZIOS, formatos: ["post"] } });
    expect(rtl.screen.getByText(/corresponde aos filtros atuais/)).toBeTruthy();
    rtl.cleanup();
    renderLista({ perfilId: "p1" });
    expect(rtl.screen.getByText(/Este perfil ainda não tem estruturas/)).toBeTruthy();
  });

  it("keeps showing rows (dimmed) while a refetch runs — never a flash of empty", () => {
    m.lista.mockReturnValue(estado([resumo()], { isRefreshing: true }));
    renderLista();
    expect(rtl.screen.getByTestId("estrutura-card-e1")).toBeTruthy();
  });
});
