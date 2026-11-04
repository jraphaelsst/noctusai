/**
 * "Uso & Custos": only the HTTP boundary (`api.get`) is mocked. Covers the aggregation, the discrimination (agent ->
 * conversations; session -> subagents), URL-synced filters, and the honest states (skeleton, 403, empty, sem câmbio).
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn() },
}));
vi.mock("../../lib/api", () => ({ api }));

import { AdminUsoCustos } from "./AdminUsoCustos";

const win = { from: "2026-11-01T00:00:00Z", to: "2026-11-08T00:00:00Z", hours: 168 };
const t = { calls: 10, errors: 0, input_tokens: 1000, output_tokens: 500, cost_usd: 20, cost_brl: 100 };
const dt = { requests: 5, input_tokens: 10, output_tokens: 20, thinking_tokens: 0, cache_read_tokens: 0, cache_write_tokens: 0, cost_usd: 10,
  prompt_chars: 1, output_chars: 2, tool_result_chars: 3, tool_calls: 4, cost_usd_per_hour: 0.5 };

const LLM = {
  window: win, freshness: { ai_usage: "2026-11-07T10:00:00Z" }, totals: t, attribution: { calls_with_agent: 8, calls_without_agent: 2 },
  per_org: [],
  per_product: { julia: { ...t, per_agent: [
    { agent_key: "julia", calls: 8, cost_usd: 16, cost_brl: 80, input_tokens: 800, output_tokens: 400, conversations: 3 },
    { agent_key: null, calls: 2, cost_usd: 4, cost_brl: 20, input_tokens: 200, output_tokens: 100, conversations: 1 },
  ] } },
  per_session: [{ conversation_id: "conv-aaaa-bbbb-cccc", product: "julia", agent_key: "julia", org_id: "org-1", calls: 8, cost_usd: 16, cost_brl: 80, first: win.from, last: win.to }],
};
const DEV = {
  window: win, freshness: { dev_telemetry_claude: "2026-11-07T09:00:00Z" }, totals: dt,
  per_session: [{ ...dt, session_id: "sess-1234-5678", project: "noc", host: "mac", subagents: 1, first: win.from, last: win.to }],
  per_agent: [{ ...dt, session_id: "sess-1234-5678", agent_id: "" }, { ...dt, session_id: "sess-1234-5678", agent_id: "agent-xyz-123" }],
  per_model: [{ ...dt, model: "claude-opus" }],
  series: [{ hour: "2026-11-07T09:00:00Z", cost_usd: 1, input_tokens: 1, output_tokens: 1, requests: 1 }],
  filters_available: { hosts: ["mac"], projects: ["noc"], models: ["claude-opus"] },
};
const MACHINE = { window: win, series: [], marks: [], filters_available: { hosts: ["mac"], phases: ["build"] } };
const JOBS = { window: win, jobs: [], per_phase: [], slowdown: [], filters_available: { hosts: [], phases: [], kinds: [] } };

function route(over: Record<string, unknown> = {}) {
  const table: Record<string, unknown> = {
    "/api/admin/llm-usage": LLM, "/api/admin/usage/dev": DEV, "/api/admin/usage/machine": MACHINE,
    "/api/admin/usage/jobs": JOBS, "/api/admin/usage/fx": { usd_brl: 5, date: "2026-11-06" }, ...over,
  };
  api.get.mockImplementation((p: string) => {
    const v = table[p.split("?")[0]];
    return v instanceof Error ? Promise.reject(v) : Promise.resolve({ data: v });
  });
}
const calls = (prefix: string) => api.get.mock.calls.map(([p]) => String(p)).filter((p) => p.startsWith(prefix));

function Where() { const l = useLocation(); return <output data-testid="loc">{l.search}</output>; }
function renderAt(path = "/admin/uso") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}><AdminUsoCustos /><Where /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => route());
afterEach(() => { cleanup(); api.get.mockReset(); });

describe("AdminUsoCustos", () => {
  it("shows skeletons while loading, never zeros", () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    renderAt();
    expect(screen.getAllByRole("status", { hidden: true }).length + document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("R$ 0,00")).not.toBeInTheDocument();
  });

  it("aggregates agents + dev (x PTAX) and shows both parts, labelled equivalente API", async () => {
    renderAt();
    // 100 + 10 usd * 5 = 150
    const total = await screen.findByText(/R\$\s150,00/);
    expect(total).toBeInTheDocument();
    const sec = within(screen.getByTestId("secao-total"));
    expect(sec.getByText(/R\$\s100,00/)).toBeInTheDocument();
    expect(sec.getByText(/R\$\s50,00/)).toBeInTheDocument();
    expect(sec.getAllByText(/equivalente API/).length).toBeGreaterThan(0);
    expect(sec.getByRole("alert")).toHaveTextContent("2 de 10 chamadas");
  });

  it("without PTAX the total is 'sem câmbio', never a guessed rate", async () => {
    route({ "/api/admin/usage/fx": { usd_brl: null, date: null } });
    renderAt();
    expect(await screen.findAllByText("sem câmbio")).not.toHaveLength(0);
    expect(within(screen.getByTestId("secao-total")).queryByText(/R\$\s150,00/)).not.toBeInTheDocument();
  });

  it("discriminates product -> agent (incl. 'sem agente') -> conversations", async () => {
    renderAt();
    const sec = within(await screen.findByTestId("secao-agentes"));
    fireEvent.click(await sec.findByRole("button", { name: "Expandir julia" }));
    expect(sec.getByRole("button", { name: "Expandir sem agente" })).toBeInTheDocument();
    fireEvent.click(sec.getByRole("button", { name: "Expandir julia", expanded: false }));
    expect(await sec.findByText(/conversa conv-aaa/)).toBeInTheDocument();
  });

  it("discriminates dev session -> subagents", async () => {
    renderAt();
    const sec = within(await screen.findByTestId("secao-dev"));
    fireEvent.click(await sec.findByRole("button", { name: /Expandir sessão sess-123/ }));
    expect(sec.getByText("sessão principal")).toBeInTheDocument();
    expect(sec.getByText(/subagente agent-xy/)).toBeInTheDocument();
  });

  it("says so when a source is empty and keeps other sections working", async () => {
    route({ "/api/admin/usage/dev": { ...DEV, totals: { ...dt, requests: 0 }, series: [], per_session: [] } });
    renderAt();
    expect(await within(await screen.findByTestId("secao-dev")).findByText(/Sem dados ainda: o sync começa após o deploy/)).toBeInTheDocument();
    expect(await within(screen.getByTestId("secao-agentes")).findByRole("button", { name: "Expandir julia" })).toBeInTheDocument();
  });

  it("a 403 is said out loud, per section", async () => {
    const e = Object.assign(new Error("[403] forbidden"), { status: 403 });
    route({ "/api/admin/llm-usage": e });
    renderAt();
    const sec = within(await screen.findByTestId("secao-agentes"));
    expect(await sec.findByText("Acesso restrito: apenas admin da plataforma.")).toBeInTheDocument();
    expect(sec.queryByText(/Nenhuma chamada/)).not.toBeInTheDocument();
  });

  it("an error in one section does not take the others down, and is not shown as empty", async () => {
    route({ "/api/admin/usage/jobs": new Error("boom") });
    renderAt();
    const jobs = within(await screen.findByTestId("secao-jobs"));
    expect(await jobs.findByText("Não foi possível carregar.")).toBeInTheDocument();
    expect(jobs.queryByText(/Sem dados ainda/)).not.toBeInTheDocument();
    expect(await within(screen.getByTestId("secao-dev")).findByText(/claude-opus/)).toBeInTheDocument();
  });

  it("reads filters from the URL, sends them to the endpoints, and mirrors changes back", async () => {
    renderAt("/admin/uso?periodo=30d&product=julia&agent=none&host=mac");
    await waitFor(() => expect(calls("/api/admin/llm-usage").length).toBeGreaterThan(0));
    const llm = new URL(calls("/api/admin/llm-usage")[0], "http://x").searchParams;
    expect(llm.get("product")).toBe("julia");
    expect(llm.get("agent_key")).toBe("none");
    expect(new URL(calls("/api/admin/usage/dev")[0], "http://x").searchParams.get("host")).toBe("mac");
    fireEvent.change(screen.getByLabelText("Sessão"), { target: { value: "sess-9" } });
    await waitFor(() => expect(screen.getByTestId("loc").textContent).toContain("session=sess-9"));
    expect(screen.getByTestId("loc").textContent).toContain("periodo=30d");
    await waitFor(() => expect(calls("/api/admin/usage/dev").some((p) => p.includes("session_id=sess-9"))).toBe(true));
  });

  it("custom period without dates asks for them instead of querying", () => {
    renderAt("/admin/uso?periodo=custom");
    expect(screen.getByText(/Escolha as datas/)).toBeInTheDocument();
    expect(calls("/api/admin/llm-usage")).toHaveLength(0);
  });
});
