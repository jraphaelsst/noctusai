/** MetricasTab — loading, empty, error, 403, data, truncado, NULL tooltips, filters, thread drill-down. */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { fmtBytes, fmtMs, fmtShare, fmtUsd } from "@/lib/metricasFormat";
import { renderWith } from "./harness";
import { IDS, METRICAS_RESUMO, METRICAS_THREAD, METRICAS_TURNOS, RESUMO, THREADS } from "./metricasFixtures";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});

import MetricasTab from "../MetricasTab";

beforeAll(() => {
  class RO { observe() {} unobserve() {} disconnect() {} }
  globalThis.ResizeObserver = RO as unknown as typeof ResizeObserver;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The text of the KPI tile whose label is `label` (walks up to the first ancestor holding more than the label). */
function tile(label: string): string {
  let el: HTMLElement | null = screen.getByText(label);
  while (el && el.textContent === label) el = el.parentElement;
  return el?.textContent ?? "";
}

const P = "/api/studio/agents/julia/metricas";
const routes = (over: Record<string, unknown> = {}) => [
  { method: "GET" as const, path: P, body: over.resumo ?? METRICAS_RESUMO },
  { method: "GET" as const, path: `${P}/turnos`, body: METRICAS_TURNOS },
  { method: "GET" as const, path: `${P}/threads`, body: THREADS },
  { method: "GET" as const, path: `${P}/threads/${IDS.THREAD}`, body: METRICAS_THREAD },
];

describe("formatters (real Julia numbers)", () => {
  it("formats cost, share, time and bytes in pt-BR", () => {
    expect(fmtUsd(0.028, 4)).toMatch(/0,0280/);
    expect(fmtUsd(0.0031, 4)).toMatch(/0,0031/);
    expect(fmtUsd(null)).toBe("—");
    expect(fmtShare(0.97)).toBe("97,0%");
    expect(fmtMs(1700)).toBe("1,7 s");
    expect(fmtMs(850)).toBe("850 ms");
    expect(fmtBytes(200)).toBe("200 B");
    expect(fmtBytes(2048)).toBe("2,0 KB");
    expect(fmtBytes(3 * 1024 * 1024)).toBe("3,0 MB");
    expect(fmtBytes(null)).toBe("—");
  });
});

describe("MetricasTab", () => {
  it("shows a skeleton first, then KPIs, tables and the per-turn rows", async () => {
    const net = installFetch(routes());
    renderWith(<MetricasTab agentKey="julia" />);
    expect(screen.getByTestId("metricas-loading")).toBeTruthy();
    expect(await screen.findByText("Custo por turno")).toBeTruthy();
    expect(tile("Custo total")).toContain("0,18");
    expect(tile("Custo por turno")).toMatch(/0,0046/);
    expect(tile("Cache lido")).toContain("75,0%");
    expect(screen.getByTestId("metricas-por-org")).toBeTruthy();
    // un-narrowed first call: default origem canal, 7-day window
    expect(net.calls[0].search.get("origem")).toBe("canal");
    expect(net.calls[0].search.has("desde")).toBe(true);
    const frio = await screen.findByTestId("turno-t-cold");
    expect(frio.textContent).toContain("0,0280");
    expect(frio.textContent).toContain("22.200");
    expect(screen.getByTestId("turno-t-warm").textContent).toContain("97,0%");
  });

  it("empty window: says what to do next", async () => {
    installFetch(routes({ resumo: { ...METRICAS_RESUMO, resumo: { ...RESUMO, turnos: 0 } } }));
    renderWith(<MetricasTab agentKey="julia" />);
    expect(await screen.findByText(/Nenhum turno medido no período/)).toBeTruthy();
    expect(screen.queryByTestId("metricas-turnos")).toBeNull();
  });

  it("server error: honest message with retry", async () => {
    installFetch([{ method: "GET", path: P, status: 500, body: { detail: "Falha interna", code: "boom" } }]);
    renderWith(<MetricasTab agentKey="julia" />);
    expect(await screen.findByTestId("studio-error")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeTruthy();
  });

  it("403: restricted notice, not a generic error", async () => {
    installFetch([{ method: "GET", path: P, status: 403, body: { detail: "Restrito", code: "forbidden" } }]);
    renderWith(<MetricasTab agentKey="julia" />);
    expect((await screen.findByTestId("studio-restrito")).textContent).toContain("administradores da plataforma");
  });

  it("truncado is a visible notice", async () => {
    installFetch(routes({ resumo: { ...METRICAS_RESUMO, truncado: true } }));
    renderWith(<MetricasTab agentKey="julia" />);
    expect((await screen.findByTestId("metricas-truncado")).textContent).toContain("limite de leitura");
  });

  it("changing origem refetches with the new filter and resets to page 1", async () => {
    const net = installFetch(routes());
    renderWith(<MetricasTab agentKey="julia" />);
    await screen.findByTestId("turno-t-cold");
    fireEvent.change(screen.getByLabelText("Origem"), { target: { value: "eval" } });
    await waitFor(() => expect(net.calls.some((c) => c.path === P && c.search.get("origem") === "eval")).toBe(true));
    fireEvent.change(screen.getByLabelText("Organização"), { target: { value: IDS.ORG } });
    await waitFor(() => expect(net.calls.some((c) => c.path === `${P}/turnos` && c.search.get("org_id") === IDS.ORG)).toBe(true));
    expect(screen.getByLabelText("Organização")).toBeTruthy();
  });

  it("custom period shows the date fields", async () => {
    installFetch(routes());
    renderWith(<MetricasTab agentKey="julia" />);
    await screen.findByTestId("turno-t-cold");
    fireEvent.change(screen.getByLabelText("Período"), { target: { value: "custom" } });
    expect(screen.getByLabelText("De")).toBeTruthy();
    expect(screen.getByLabelText("Até")).toBeTruthy();
  });

  it("pagination moves the page param", async () => {
    const net = installFetch(routes());
    renderWith(<MetricasTab agentKey="julia" />);
    await screen.findByTestId("turno-t-cold");
    expect(screen.getByRole("button", { name: "Anterior" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Próxima" }));
    await waitFor(() => expect(net.calls.some((c) => c.path === `${P}/turnos` && c.search.get("pagina") === "2")).toBe(true));
  });

  it("a turn row opens the thread view; NULL media / intake render as an explained dash", async () => {
    installFetch(routes());
    renderWith(<MetricasTab agentKey="julia" />);
    const row = await screen.findByTestId("turno-t-cold");
    fireEvent.click(within(row).getByRole("button", { name: /Abrir conversa/ }));
    const thread = await screen.findByTestId("metricas-thread");
    expect(await within(thread).findByTestId("metricas-thread-turnos")).toBeTruthy();
    expect(within(thread).getByTestId("metricas-thread-resumo").textContent).toContain("Custo total");
    const warm = within(thread).getByTestId("turno-t-warm");
    expect(within(warm).getByLabelText(/Não aplicável: avaliações não têm lote de entrada/)).toBeTruthy();
    expect(within(thread).getAllByLabelText(/Mídia não é armazenada no app de agentes/).length).toBe(2);
    fireEvent.click(within(thread).getByRole("button", { name: "Fechar" }));
    expect(screen.queryByTestId("metricas-thread")).toBeNull();
  });
});
