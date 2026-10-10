/**
 * Dashboard.test.tsx — greeting + KPIs (no "Diagnóstico"), Histórico order -> hook arg,
 * sugeridas actions open the modals prefilled, honest empty/error/loading states.
 * Hook + modals mocked; no network.
 */
import React from "react";
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

const m = vi.hoisted(() => ({ dash: vi.fn() }));

vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({ data: [{ id: "m1", name: "Marca 1" }], isPending: false }),
}));
vi.mock("@/hooks/geracao/useDashboardCriacao", async (orig) => ({
  ...(await orig<typeof import("@/hooks/geracao/useDashboardCriacao")>()),
  useDashboardCriacao: (marcaId: string | null, ordem: string) => m.dash(marcaId, ordem),
}));
vi.mock("@/components/geracao/roteiro/RoteiroAvancadoModal", () => ({
  RoteiroAvancadoModal: (p: { open: boolean; marcaId: string | null; headlineInicial?: { id?: string; texto: string } }) =>
    p.open ? <div data-testid="modal-roteiro">{`${p.marcaId}|${p.headlineInicial?.id}|${p.headlineInicial?.texto}`}</div> : null,
}));
vi.mock("@/components/geracao/headlines/EditarHeadlineModal", () => ({
  EditarHeadlineModal: (p: { open: boolean; headline: { id: string } | null }) =>
    p.open ? <div data-testid="modal-editar">{p.headline?.id}</div> : null,
}));

const headline = (n: number, over: Record<string, unknown> = {}) => ({
  id: `h${n}`,
  marca_id: "m1",
  lote_id: null,
  texto: `Headline ${n}`,
  texto_original: null,
  angulo: null,
  viral: { id: `v${n}`, permalink: `https://instagram.com/p/${n}`, views: 3_100_000, likes: null, score_viral: null },
  template_metodo: null,
  itens_usados: [],
  favorita: false,
  modo: "automatico",
  roteiro_id: null,
  created_at: "2026-10-01T10:00:00Z",
  ...over,
});
const payload = (over: Record<string, unknown> = {}) => ({
  saudacao_nome: "Gilson",
  kpis: { headlines_geradas: 12, roteiros_gerados: 2, itens_pendentes: 5 },
  historico: [{ tipo: "perfil", texto: "atualizou o perfil.", ator: "Gilson", em: "2026-10-01T10:00:00Z" }],
  sugeridas: [headline(1), headline(2, { viral: null })],
  ...over,
});
const q = (data: unknown, over: Record<string, unknown> = {}) => ({
  data,
  showSkeleton: false,
  isRefreshing: false,
  isError: false,
  refetch: vi.fn(),
  ...over,
});
const renderPage = () =>
  rtl.render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  m.dash.mockReturnValue(q(payload()));
});

describe("Dashboard", () => {
  it("greets by name and shows the three KPIs without Diagnóstico; pendentes links to Minha Pesquisa", () => {
    renderPage();
    expect(rtl.screen.getByText("Olá, Gilson!")).toBeTruthy();
    expect(rtl.screen.getByTestId("kpi-Headlines geradas").textContent).toBe("12");
    expect(rtl.screen.getByTestId("kpi-Roteiros gerados").textContent).toBe("2");
    expect(rtl.screen.getByTestId("kpi-Itens pendentes").textContent).toBe("5");
    expect(rtl.screen.queryByText(/Diagnóstico/)).toBeNull();
    expect(
      rtl.screen.getByRole("link", { name: /Itens pendentes/ }).getAttribute("href"),
    ).toBe("/media-creation/pesquisa?status=pending");
  });

  it("renders the Histórico and passes the chosen order to the hook", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(rtl.screen.getByText("Linha do tempo do seu uso.")).toBeTruthy();
    expect(rtl.screen.getByText("atualizou o perfil.")).toBeTruthy();
    expect(m.dash).toHaveBeenLastCalledWith("m1", "data_desc");
    await user.selectOptions(rtl.screen.getByLabelText("Filtrar histórico"), "tipo");
    expect(m.dash).toHaveBeenLastCalledWith("m1", "tipo");
  });

  it("Criar roteiro opens RoteiroAvancadoModal prefilled with the headline", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(rtl.screen.getByLabelText("Ações da headline h1"));
    await user.click(await rtl.screen.findByText("Criar roteiro"));
    expect((await rtl.screen.findByTestId("modal-roteiro")).textContent).toBe("m1|h1|Headline 1");
  });

  it("Editar opens EditarHeadlineModal; Abrir link points at the viral permalink and is absent without a viral", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(rtl.screen.getByLabelText("Ações da headline h1"));
    const link = await rtl.screen.findByText("Abrir link");
    expect(link.closest("a")?.getAttribute("href")).toBe("https://instagram.com/p/1");
    await user.click(await rtl.screen.findByText("Editar"));
    expect((await rtl.screen.findByTestId("modal-editar")).textContent).toBe("h1");
    rtl.cleanup();

    renderPage();
    await user.click(rtl.screen.getByLabelText("Ações da headline h2"));
    await rtl.screen.findByText("Criar roteiro");
    expect(rtl.screen.queryByText("Abrir link")).toBeNull();
  });

  it("shows the honest empty state when there are no sugeridas", () => {
    m.dash.mockReturnValue(q(payload({ sugeridas: [], historico: [] })));
    renderPage();
    expect(
      rtl.screen.getByText(/Nenhuma headline sugerida ainda — elas aparecem aqui todos os dias/),
    ).toBeTruthy();
    expect(rtl.screen.getByText("Nenhuma atividade registrada ainda.")).toBeTruthy();
  });

  it("shows a skeleton only while there is no data", () => {
    m.dash.mockReturnValue(q(undefined, { showSkeleton: true }));
    renderPage();
    expect(rtl.screen.getByTestId("dashboard-skeleton")).toBeTruthy();
    expect(rtl.screen.queryByText("Headlines geradas")).toBeNull();
  });

  it("keeps the data on screen while refreshing (no skeleton, busy flag)", () => {
    m.dash.mockReturnValue(q(payload(), { isRefreshing: true }));
    const { container } = renderPage();
    expect(rtl.screen.queryByTestId("dashboard-skeleton")).toBeNull();
    expect(rtl.screen.getByText("Headline 1")).toBeTruthy();
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
  });

  it("shows the error state with Tentar novamente", async () => {
    const refetch = vi.fn();
    m.dash.mockReturnValue(q(undefined, { isError: true, refetch }));
    renderPage();
    expect(rtl.screen.getByRole("alert").textContent).toContain("Não foi possível carregar o dashboard.");
    await userEvent.setup().click(rtl.screen.getByRole("button", { name: "Tentar novamente" }));
    expect(refetch).toHaveBeenCalled();
  });
});
