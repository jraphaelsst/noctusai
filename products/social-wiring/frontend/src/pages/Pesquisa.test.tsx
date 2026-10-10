/**
 * Pesquisa.test.tsx — Minha Pesquisa page: list from mocked API, the four
 * states, no-lying-loading (refreshing keeps the list), approve/reject/delete,
 * bulk bar + Ações (typed brand name for "Zerar"), and both add-modal modes.
 */
import React from "react";
import { cleanup, configure } from "@testing-library/react";
import * as rtl from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Pesquisa from "./Pesquisa";

// Deterministic under machine load: every await is a findBy*/waitFor, never a
// fixed delay, and the page/deps are imported statically (module load happens
// at collection time, not inside the 5s test budget). The generous
// asyncUtilTimeout is only an upper bound — assertions resolve as soon as true.
configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });

afterEach(() => {
  cleanup();
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const m = {
  marcas: vi.fn(),
  variaveis: vi.fn(),
  itens: vi.fn(),
  counts: vi.fn(),
  aprovar: vi.fn(),
  rejeitar: vi.fn(),
  excluir: vi.fn(),
  massa: vi.fn(),
  zerar: vi.fn(),
  adicionar: vi.fn(),
  classificar: vi.fn(),
};

vi.mock("@/components/pesquisa/AssuntosVirais", () => ({
  AssuntosVirais: ({ marcaId }: { marcaId: string }) => (
    <div data-testid="assuntos-stub">{marcaId}</div>
  ),
}));
vi.mock("@/hooks/useMarcas", () => ({ useMarcas: () => m.marcas() }));
vi.mock("@/hooks/usePesquisa", () => ({
  usePesquisaVariaveis: () => m.variaveis(),
  usePesquisaItens: (f: any) => m.itens(f),
  usePesquisaCounts: (id: any) => m.counts(id),
  useAprovarItem: () => ({ mutateAsync: m.aprovar, isPending: false }),
  useRejeitarItem: () => ({ mutateAsync: m.rejeitar, isPending: false }),
  useExcluirItem: () => ({ mutateAsync: m.excluir, isPending: false }),
  useAcaoEmMassa: () => ({ mutateAsync: m.massa, isPending: false }),
  useZerarPesquisa: () => ({ mutateAsync: m.zerar, isPending: false }),
  useAdicionarItens: () => ({ mutateAsync: m.adicionar, isPending: false }),
  useClassificarItens: () => ({ mutateAsync: m.classificar, isPending: false }),
}));

const VARS = [
  {
    slug: "DORES",
    label: "Dores do meu público",
    grupo: "publico",
    description: "",
    classifiable: true,
    sort_order: 1,
  },
  {
    slug: "HISTORIA",
    label: "Minha história",
    grupo: "especialista",
    description: "",
    classifiable: true,
    sort_order: 2,
  },
];

function item(over: Partial<any> = {}) {
  return {
    id: "i1",
    marca_id: "m1",
    variable_slug: "DORES",
    content: "Medo de errar na obra",
    status: "approved",
    origin: "manual",
    plays: 1234567,
    source_ref: null,
    created_at: "2026-10-09T10:00:00Z",
    ...over,
  };
}

function itensState(over: Partial<any> = {}) {
  const items = over.items ?? [item()];
  return {
    items,
    total: items.length,
    data: { pages: [] },
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    refetch: vi.fn(),
    ...over,
  };
}

function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="loc">{loc.search}</span>;
}

async function renderPage(url = "/media-creation/pesquisa") {
  return {
    ...rtl.render(
      <MemoryRouter initialEntries={[url]}>
        <Pesquisa />
        <LocationProbe />
      </MemoryRouter>,
    ),
    rtl,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  m.marcas.mockReturnValue({
    data: [
      { id: "m1", name: "Marca Um" },
      { id: "m2", name: "Marca Dois" },
    ],
    isPending: false,
    isError: false,
  });
  m.variaveis.mockReturnValue({ data: VARS });
  m.counts.mockReturnValue({
    data: { approved: 3, pending: 2, by_variable: {} },
  });
  m.itens.mockReturnValue(itensState());
  for (const k of ["aprovar", "rejeitar", "excluir", "zerar"] as const)
    m[k].mockResolvedValue({});
  m.massa.mockResolvedValue({ affected: 1 });
  m.adicionar.mockResolvedValue({ saved: 2, skipped: 1, items: [] });
  m.classificar.mockResolvedValue({
    saved: 2,
    skipped: 0,
    classified: { DORES: ["a", "b"] },
    unclassified: ["lixo"],
  });
});

describe("Pesquisa — states", () => {
  it("renders the row with label · grupo · manual · formatted views and counts", async () => {
    const { rtl } = await renderPage();
    expect(rtl.screen.getByText("Medo de errar na obra")).toBeTruthy();
    expect(
      rtl.screen.getByText(
        /Dores do meu público · Meu Público · manual · 1\.234\.567 views/,
      ),
    ).toBeTruthy();
    expect(rtl.screen.getByText("Aprovados (3)")).toBeTruthy();
    expect(rtl.screen.getByText("Pendentes (2)")).toBeTruthy();
  });

  it("shows the skeleton, not the list, while showSkeleton", async () => {
    m.itens.mockReturnValue(itensState({ items: [], showSkeleton: true }));
    const { rtl } = await renderPage();
    expect(rtl.screen.getByTestId("pesquisa-skeleton")).toBeTruthy();
    expect(rtl.screen.queryByText("Nenhum item encontrado.")).toBeNull();
  });

  it("keeps the list visible while refreshing", async () => {
    m.itens.mockReturnValue(itensState({ isRefreshing: true }));
    const { rtl } = await renderPage();
    expect(rtl.screen.getByText("Medo de errar na obra")).toBeTruthy();
    expect(rtl.screen.getByText("Atualizando…")).toBeTruthy();
    expect(rtl.screen.queryByTestId("pesquisa-skeleton")).toBeNull();
  });

  it("shows the empty state", async () => {
    m.itens.mockReturnValue(itensState({ items: [] }));
    const { rtl } = await renderPage();
    expect(rtl.screen.getByText("Nenhum item encontrado.")).toBeTruthy();
  });

  it("shows the error state with retry", async () => {
    const refetch = vi.fn();
    m.itens.mockReturnValue(
      itensState({ items: [], isError: true, data: undefined, refetch }),
    );
    const { rtl } = await renderPage();
    rtl.fireEvent.click(rtl.screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("queries with the brand/status/sort filters and remembers the brand", async () => {
    const { rtl } = await renderPage();
    expect(m.itens).toHaveBeenLastCalledWith(
      expect.objectContaining({
        marcaId: "m1",
        status: "approved",
        sort: "recent",
        pageSize: 50,
      }),
    );
    rtl.fireEvent.change(rtl.screen.getByLabelText("Marca"), {
      target: { value: "m2" },
    });
    expect(window.localStorage.getItem("sw.pesquisa.marca")).toBe("m2");
    rtl.fireEvent.click(rtl.screen.getByText("Pendentes (2)"));
    expect(m.itens).toHaveBeenLastCalledWith(
      expect.objectContaining({ marcaId: "m2", status: "pending" }),
    );
  });

  it("Agrupar raises the page size to 200 and hides Carregar mais", async () => {
    m.itens.mockReturnValue(itensState({ hasNextPage: true }));
    const { rtl } = await renderPage();
    expect(rtl.screen.getByText("Carregar mais")).toBeTruthy();
    rtl.fireEvent.click(rtl.screen.getByLabelText("Agrupar"));
    expect(m.itens).toHaveBeenLastCalledWith(
      expect.objectContaining({ pageSize: 200 }),
    );
    expect(rtl.screen.queryByText("Carregar mais")).toBeNull();
  });
});

describe("Pesquisa — tabs, extraction and deep links", () => {
  it("tab switch syncs ?tab and swaps the content", async () => {
    const { rtl } = await renderPage();
    expect(rtl.screen.queryByTestId("assuntos-stub")).toBeNull();
    rtl.fireEvent.mouseDown(
      rtl.screen.getByRole("tab", { name: "Assuntos virais" }),
    );
    expect((await rtl.screen.findByTestId("assuntos-stub")).textContent).toBe(
      "m1",
    );
    expect(rtl.screen.getByTestId("loc").textContent).toContain(
      "tab=assuntos-virais",
    );
    expect(rtl.screen.queryByText("Medo de errar na obra")).toBeNull();
    rtl.fireEvent.mouseDown(
      rtl.screen.getByRole("tab", { name: "Itens de pesquisa" }),
    );
    expect(await rtl.screen.findByText("Medo de errar na obra")).toBeTruthy();
    expect(rtl.screen.getByTestId("loc").textContent).toContain("tab=itens");
  });

  it("opens on ?tab=assuntos-virais", async () => {
    const { rtl } = await renderPage(
      "/media-creation/pesquisa?tab=assuntos-virais",
    );
    expect(await rtl.screen.findByTestId("assuntos-stub")).toBeTruthy();
  });

  it("header links to Extrair Pesquisa", async () => {
    const { rtl } = await renderPage();
    const link = rtl.screen.getByRole("link", { name: /Extrair Pesquisa/ });
    expect(link.getAttribute("href")).toBe("/media-creation/pesquisa/extrair");
  });

  it("an extraction row shows '· extração' and Ver post from source_ref.url", async () => {
    m.itens.mockReturnValue(
      itensState({
        items: [
          item({
            origin: "extraction",
            status: "pending",
            source_ref: {
              kind: "instagram_media",
              url: "https://instagram.com/p/abc",
              excerpt: "trecho do post",
            },
          }),
        ],
      }),
    );
    const { rtl } = await renderPage();
    expect(rtl.screen.getByText(/· extração/)).toBeTruthy();
    const link = rtl.screen.getByRole("link", { name: "Ver post" });
    expect(link.getAttribute("href")).toBe("https://instagram.com/p/abc");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("a row without source_ref has no Ver post link", async () => {
    const { rtl } = await renderPage();
    expect(rtl.screen.queryByRole("link", { name: "Ver post" })).toBeNull();
  });

  it("honours ?status=pending on load", async () => {
    await renderPage("/media-creation/pesquisa?status=pending");
    expect(m.itens).toHaveBeenCalledWith(
      expect.objectContaining({ status: "pending" }),
    );
  });
});

describe("Pesquisa — row actions", () => {
  it("pending: Aprovar and Rejeitar call the mutations", async () => {
    m.itens.mockReturnValue(
      itensState({
        items: [item({ status: "pending", origin: "ai_classified" })],
      }),
    );
    const { rtl } = await renderPage();
    rtl.fireEvent.click(rtl.screen.getByText("Aprovar"));
    await rtl.waitFor(() => expect(m.aprovar).toHaveBeenCalledWith("i1"));
    rtl.fireEvent.click(rtl.screen.getByText("Rejeitar"));
    await rtl.waitFor(() => expect(m.rejeitar).toHaveBeenCalledWith("i1"));
  });

  it("approved: Excluir asks for confirmation first", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Excluir" }));
    expect(m.excluir).not.toHaveBeenCalled();
    const dialog = await rtl.screen.findByRole("alertdialog");
    rtl.fireEvent.click(
      rtl.within(dialog).getByRole("button", { name: "Excluir" }),
    );
    await rtl.waitFor(() => expect(m.excluir).toHaveBeenCalledWith("i1"));
  });
});

describe("Pesquisa — bulk", () => {
  it("selecting shows the bar; Ações > Excluir selecionados confirms then bulk-deletes", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(
      rtl.screen.getByLabelText("Selecionar: Medo de errar na obra"),
    );
    expect(rtl.screen.getByText("1 selecionado")).toBeTruthy();
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Ações" }));
    rtl.fireEvent.click(
      await rtl.screen.findByRole("button", { name: "Excluir selecionados" }),
    );
    const dialog = await rtl.screen.findByRole("alertdialog");
    rtl.fireEvent.click(
      rtl.within(dialog).getByRole("button", { name: "Excluir" }),
    );
    await rtl.waitFor(() =>
      expect(m.massa).toHaveBeenCalledWith({
        marca_id: "m1",
        action: "delete",
        ids: ["i1"],
      }),
    );
  });

  it("Aprovar in Ações only exists on the pending filter, and bulk-approves", async () => {
    m.itens.mockReturnValue(
      itensState({ items: [item({ status: "pending" })] }),
    );
    const { rtl } = await renderPage();
    rtl.fireEvent.click(rtl.screen.getByText("Pendentes (2)"));
    rtl.fireEvent.click(
      rtl.screen.getByLabelText("Selecionar: Medo de errar na obra"),
    );
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Ações" }));
    const dlg = await rtl.screen.findByRole("dialog");
    rtl.fireEvent.click(
      rtl.within(dlg).getByRole("button", { name: "Aprovar" }),
    );
    await rtl.waitFor(() =>
      expect(m.massa).toHaveBeenCalledWith({
        marca_id: "m1",
        action: "approve",
        ids: ["i1"],
      }),
    );
  });

  it("Aprovar is absent from Ações on the approved filter", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(
      rtl.screen.getByLabelText("Selecionar: Medo de errar na obra"),
    );
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Ações" }));
    const dlg = await rtl.screen.findByRole("dialog");
    expect(
      rtl.within(dlg).queryByRole("button", { name: "Aprovar" }),
    ).toBeNull();
  });

  it("Zerar requires typing the brand name", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(
      rtl.screen.getByLabelText("Selecionar: Medo de errar na obra"),
    );
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Ações" }));
    rtl.fireEvent.click(
      await rtl.screen.findByRole("button", {
        name: "Zerar toda a pesquisa da marca",
      }),
    );
    const dialog = await rtl.screen.findByRole("alertdialog");
    const confirmar = rtl
      .within(dialog)
      .getByRole("button", { name: "Zerar pesquisa" }) as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    rtl.fireEvent.change(rtl.within(dialog).getByRole("textbox"), {
      target: { value: "Marca Um" },
    });
    expect(confirmar.disabled).toBe(false);
    rtl.fireEvent.click(confirmar);
    await rtl.waitFor(() => expect(m.zerar).toHaveBeenCalledWith("m1"));
  });
});

describe("Pesquisa — add modal", () => {
  it("manual mode: chosen variable posts the trimmed non-empty lines", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: /Adicionar itens/ }),
    );
    const dlg = await rtl.screen.findByRole("dialog");
    rtl.fireEvent.change(
      rtl.within(dlg).getByLabelText("Variável de destino"),
      { target: { value: "HISTORIA" } },
    );
    rtl.fireEvent.change(
      rtl.within(dlg).getByLabelText("Itens (um por linha)"),
      {
        target: { value: " um \n\n dois " },
      },
    );
    expect(rtl.within(dlg).getByText("2 item(ns)")).toBeTruthy();
    rtl.fireEvent.click(
      rtl.within(dlg).getByRole("button", { name: "Salvar" }),
    );
    await rtl.waitFor(() =>
      expect(m.adicionar).toHaveBeenCalledWith({
        marca_id: "m1",
        variable_slug: "HISTORIA",
        lines: ["um", "dois"],
      }),
    );
    expect(
      await rtl.within(dlg).findByTestId("pesquisa-resultado"),
    ).toBeTruthy();
  });

  it("AI mode (no variable): classifies and shows the result view with unclassified lines", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: /Adicionar itens/ }),
    );
    const dlg = await rtl.screen.findByRole("dialog");
    rtl.fireEvent.change(
      rtl.within(dlg).getByLabelText("Itens (um por linha)"),
      {
        target: { value: "a\nb\nlixo" },
      },
    );
    rtl.fireEvent.keyDown(
      rtl.within(dlg).getByLabelText("Itens (um por linha)"),
      {
        key: "Enter",
        ctrlKey: true,
      },
    );
    await rtl.waitFor(() =>
      expect(m.classificar).toHaveBeenCalledWith({
        marca_id: "m1",
        text: "a\nb\nlixo",
      }),
    );
    const res = await rtl.within(dlg).findByTestId("pesquisa-resultado");
    expect(rtl.within(res).getByText(/Não classificados \(1\)/)).toBeTruthy();
    expect(rtl.within(res).getByText("lixo")).toBeTruthy();
    expect(
      rtl.within(dlg).getByRole("button", { name: "Inserir mais" }),
    ).toBeTruthy();
    expect(
      rtl.within(dlg).getByRole("button", { name: "Fechar" }),
    ).toBeTruthy();
  });

  it("blocks saving when an item exceeds 500 characters", async () => {
    const { rtl } = await renderPage();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: /Adicionar itens/ }),
    );
    const dlg = await rtl.screen.findByRole("dialog");
    rtl.fireEvent.change(
      rtl.within(dlg).getByLabelText("Itens (um por linha)"),
      {
        target: { value: "x".repeat(501) },
      },
    );
    expect(
      (
        rtl.within(dlg).getByRole("button", {
          name: "Classificar e salvar",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(rtl.within(dlg).getByRole("alert")).toBeTruthy();
  });
});
