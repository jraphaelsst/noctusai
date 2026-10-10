/**
 * AssuntosVirais.test.tsx — both sub-tabs, add / approve / reject, bulk,
 * Esvaziar with confirm, and the sources modal. API hooks are mocked.
 */
import React from "react";
import * as rtl from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { AssuntosVirais } from "./AssuntosVirais";

// Upper bound only (see Pesquisa.test.tsx): assertions resolve as soon as true.
rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const m = {
  lista: vi.fn(),
  counts: vi.fn(),
  fontes: vi.fn(),
  adicionar: vi.fn(),
  aprovar: vi.fn(),
  rejeitar: vi.fn(),
  excluir: vi.fn(),
  massa: vi.fn(),
  esvaziar: vi.fn(),
};

vi.mock("@/hooks/useAssuntosVirais", () => ({
  useAssuntosVirais: (...a: any[]) => m.lista(...a),
  useAssuntosCounts: (id: any) => m.counts(id),
  useAssuntoFontes: (id: any) => m.fontes(id),
  useAdicionarAssuntos: () => ({ mutateAsync: m.adicionar, isPending: false }),
  useAprovarAssunto: () => ({ mutateAsync: m.aprovar, isPending: false }),
  useRejeitarAssunto: () => ({ mutateAsync: m.rejeitar, isPending: false }),
  useExcluirAssunto: () => ({ mutateAsync: m.excluir, isPending: false }),
  useAssuntosEmMassa: () => ({ mutateAsync: m.massa, isPending: false }),
  useEsvaziarAssuntos: () => ({ mutateAsync: m.esvaziar, isPending: false }),
}));

const topic = (over: Partial<any> = {}) => ({
  id: "t1",
  marca_id: "m1",
  topic: "reforma de banheiro",
  status: "approved",
  origin: "extraction",
  total_plays: 1_500_000,
  fontes_count: 2,
  created_at: "2026-10-09T10:00:00Z",
  ...over,
});

function listaState(items: any[], over: Partial<any> = {}) {
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

const fontesState = (over: Partial<any> = {}) => ({
  data: [],
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});

function renderTab() {
  return rtl.render(
    <MemoryRouter>
      <AssuntosVirais marcaId="m1" />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  m.counts.mockReturnValue({ data: { approved: 1, pending: 3 } });
  m.lista.mockImplementation((_id: string, status: string) =>
    status === "pending"
      ? listaState([
          topic({ id: "p1", topic: "obra parada", status: "pending" }),
        ])
      : listaState([
          topic(),
          topic({
            id: "t2",
            topic: "meu assunto",
            origin: "manual",
            total_plays: null,
          }),
        ]),
  );
  m.fontes.mockReturnValue(fontesState());
  for (const k of ["aprovar", "rejeitar", "excluir"] as const)
    m[k].mockResolvedValue({});
  m.adicionar.mockResolvedValue({ saved: 1, skipped: 0, items: [] });
  m.massa.mockResolvedValue({ affected: 2 });
  m.esvaziar.mockResolvedValue({ deleted: 2 });
});

describe("AssuntosVirais — Aprovado", () => {
  it("shows the info card CTA, pills with K/M views or Manual, and the Pendente count", () => {
    renderTab();
    const cta = rtl.screen.getByRole("link", {
      name: /Extrair Assuntos Virais/,
    });
    expect(cta.getAttribute("href")).toBe(
      "/media-creation/pesquisa/extrair?tipo=assuntos_virais",
    );
    expect(rtl.screen.getByText("reforma de banheiro")).toBeTruthy();
    expect(rtl.screen.getByText("1,5M Views")).toBeTruthy();
    expect(rtl.screen.getByText("Manual")).toBeTruthy();
    expect(
      rtl.screen.getByRole("button", { name: "Pendente (3)" }),
    ).toBeTruthy();
  });

  it("adds a topic on Enter; empty input toasts instead of posting", async () => {
    renderTab();
    const input = rtl.screen.getByPlaceholderText(
      "Digite um novo assunto viral...",
    );
    const form = input.closest("form") as HTMLFormElement;
    rtl.fireEvent.submit(form);
    expect(toast.error).toHaveBeenCalledWith("Digite um tópico válido!");
    expect(m.adicionar).not.toHaveBeenCalled();
    rtl.fireEvent.change(input, { target: { value: "  novo tema " } });
    rtl.fireEvent.submit(form);
    await rtl.waitFor(() =>
      expect(m.adicionar).toHaveBeenCalledWith({
        marca_id: "m1",
        topics: ["novo tema"],
      }),
    );
  });

  it("× confirms before deleting one topic", async () => {
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "Remover: reforma de banheiro" }),
    );
    expect(m.excluir).not.toHaveBeenCalled();
    const dialog = await rtl.screen.findByRole("alertdialog");
    expect(
      rtl
        .within(dialog)
        .getByText("Você realmente deseja remover este tópico viral?"),
    ).toBeTruthy();
    rtl.fireEvent.click(
      rtl.within(dialog).getByRole("button", { name: "Excluir" }),
    );
    await rtl.waitFor(() => expect(m.excluir).toHaveBeenCalledWith("t1"));
  });

  it("Selecionar todos + Excluir selecionados bulk-deletes after confirm", async () => {
    renderTab();
    rtl.fireEvent.click(rtl.screen.getByLabelText("Selecionar todos"));
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "Excluir selecionados (2)" }),
    );
    const dialog = await rtl.screen.findByRole("alertdialog");
    rtl.fireEvent.click(
      rtl.within(dialog).getByRole("button", { name: "Excluir" }),
    );
    await rtl.waitFor(() =>
      expect(m.massa).toHaveBeenCalledWith({
        marca_id: "m1",
        action: "delete",
        ids: ["t1", "t2"],
      }),
    );
  });

  it("Esvaziar confirms with the approved copy then empties that status", async () => {
    renderTab();
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Esvaziar" }));
    const dialog = await rtl.screen.findByRole("alertdialog");
    expect(
      rtl
        .within(dialog)
        .getByText(
          "Você realmente deseja esvaziar TODOS os assuntos virais aprovados? Esta ação não pode ser desfeita.",
        ),
    ).toBeTruthy();
    rtl.fireEvent.click(
      rtl.within(dialog).getByRole("button", { name: "Esvaziar" }),
    );
    await rtl.waitFor(() =>
      expect(m.esvaziar).toHaveBeenCalledWith({
        marca_id: "m1",
        status: "approved",
      }),
    );
  });

  it("pill click opens the sources modal with the viral posts", async () => {
    m.fontes.mockImplementation((id: string | null) =>
      fontesState({
        data: id
          ? [
              {
                source_kind: "instagram_media",
                account_id: "a1",
                source_id: "s1",
                url: "https://instagram.com/p/x",
                thumbnail_url: null,
                published_at: "2026-09-01T00:00:00Z",
                plays: 2500,
                likes: null,
                comments: 12,
                excerpt: "o trecho viral",
              },
            ]
          : [],
      }),
    );
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "reforma de banheiro" }),
    );
    const dlg = await rtl.screen.findByRole("dialog");
    expect(
      rtl.within(dlg).getByText("Assuntos Virais — «reforma de banheiro»"),
    ).toBeTruthy();
    expect(
      rtl.within(dlg).getByText(/2,5K Views · — Likes · 12 Comentários/),
    ).toBeTruthy();
    expect(rtl.within(dlg).getByText("o trecho viral")).toBeTruthy();
    expect(rtl.within(dlg).getByRole("link").getAttribute("href")).toBe(
      "https://instagram.com/p/x",
    );
  });

  it("modal states: loading, empty, error with retry", async () => {
    m.fontes.mockReturnValue(
      fontesState({ data: undefined, showSkeleton: true }),
    );
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "reforma de banheiro" }),
    );
    expect(
      await rtl.screen.findByText("Buscando dados dos virais..."),
    ).toBeTruthy();
    m.fontes.mockReturnValue(fontesState());
    rtl.cleanup();
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "reforma de banheiro" }),
    );
    expect(
      await rtl.screen.findByText(
        "Nenhum dado viral encontrado para este tópico.",
      ),
    ).toBeTruthy();
    const refetch = vi.fn();
    m.fontes.mockReturnValue(
      fontesState({ data: undefined, isError: true, refetch }),
    );
    rtl.cleanup();
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "reforma de banheiro" }),
    );
    rtl.fireEvent.click(
      await rtl.screen.findByRole("button", { name: "Tentar novamente" }),
    );
    expect(refetch).toHaveBeenCalled();
  });
});

describe("AssuntosVirais — Pendente", () => {
  async function irParaPendente() {
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "Pendente (3)" }),
    );
    await rtl.screen.findByText("obra parada");
  }

  it("Aprovar and Rejeitar act without confirm", async () => {
    await irParaPendente();
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Aprovar" }));
    await rtl.waitFor(() => expect(m.aprovar).toHaveBeenCalledWith("p1"));
    rtl.fireEvent.click(rtl.screen.getByRole("button", { name: "Rejeitar" }));
    await rtl.waitFor(() => expect(m.rejeitar).toHaveBeenCalledWith("p1"));
    expect(rtl.screen.queryByRole("alertdialog")).toBeNull();
  });

  it("bulk Aprovar selecionados; Excluir selecionados rejects", async () => {
    await irParaPendente();
    rtl.fireEvent.click(
      rtl.screen.getByLabelText("Selecionar assunto: obra parada"),
    );
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "Aprovar selecionados (1)" }),
    );
    await rtl.waitFor(() =>
      expect(m.massa).toHaveBeenCalledWith({
        marca_id: "m1",
        action: "approve",
        ids: ["p1"],
      }),
    );
    rtl.fireEvent.click(
      rtl.screen.getByLabelText("Selecionar assunto: obra parada"),
    );
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "Excluir selecionados (1)" }),
    );
    const dialog = await rtl.screen.findByRole("alertdialog");
    rtl.fireEvent.click(
      rtl.within(dialog).getByRole("button", { name: "Excluir" }),
    );
    await rtl.waitFor(() =>
      expect(m.massa).toHaveBeenCalledWith({
        marca_id: "m1",
        action: "reject",
        ids: ["p1"],
      }),
    );
  });

  it("empty state", async () => {
    m.lista.mockImplementation((_i: string, status: string) =>
      status === "pending" ? listaState([]) : listaState([topic()]),
    );
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: "Pendente (3)" }),
    );
    expect(await rtl.screen.findByText("Nenhum item pendente")).toBeTruthy();
  });
});

describe("AssuntosVirais — loading states", () => {
  it("skeleton while showSkeleton; list stays while refreshing", async () => {
    m.lista.mockReturnValue(listaState([], { showSkeleton: true }));
    renderTab();
    expect(rtl.screen.getByTestId("assuntos-skeleton")).toBeTruthy();
    rtl.cleanup();
    m.lista.mockReturnValue(listaState([topic()], { isRefreshing: true }));
    renderTab();
    expect(rtl.screen.getByText("reforma de banheiro")).toBeTruthy();
    expect(rtl.screen.getByText("Atualizando…")).toBeTruthy();
    expect(rtl.screen.queryByTestId("assuntos-skeleton")).toBeNull();
  });

  it("error state retries", async () => {
    const refetch = vi.fn();
    m.lista.mockReturnValue(
      listaState([], { isError: true, data: undefined, refetch }),
    );
    renderTab();
    rtl.fireEvent.click(
      rtl.screen.getByRole("button", { name: /Tentar novamente/ }),
    );
    expect(refetch).toHaveBeenCalled();
  });
});
