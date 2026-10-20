/** Perguntas + Conhecimento became read-only notices (julia-v2 Q1/Q6): same routes, link to agents, no content, no writes. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import JuliaConhecimento from "./Conhecimento";
import JuliaPerguntas from "./Perguntas";

const ROT = { linhas: [], destino_handoff_padrao: { tipo: "dono_da_organizacao", user_id: null }, agents_url: "https://agents.example.test" };

function setup(Page: () => JSX.Element, rot: unknown = { data: ROT }) {
  api.get.mockImplementation(() => (rot instanceof Error ? Promise.reject(rot) : Promise.resolve(rot)));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><Page /></QueryClientProvider>);
}
beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe.each([
  ["Conhecimento", JuliaConhecimento],
  ["Perguntas", JuliaPerguntas],
])("Julia › %s (moved to agents)", (nome, Page) => {
  it("shows a skeleton, then the notice with the link to agents", async () => {
    setup(Page);
    expect(screen.getByTestId("movido-skeleton")).toBeTruthy();
    expect((await screen.findByTestId("movido-para-agentes")).textContent).toContain("Agora é configurado no app de agentes.");
    expect(screen.getByRole("heading").textContent).toContain(nome);
    const a = (await screen.findByTestId("configurar-julia-link")) as HTMLAnchorElement;
    expect(a.href).toBe("https://agents.example.test/studio/julia");
  });

  it("is read-only: no editor, no write, and only the routing read is made", async () => {
    setup(Page);
    await screen.findByTestId("configurar-julia-link");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
    expect(api.get.mock.calls.map((c) => c[0])).toEqual(["/api/julia/roteamento"]);
    expect(api.put).not.toHaveBeenCalled();
  });

  it("agents URL unresolvable -> says so", async () => {
    setup(Page, { data: { ...ROT, agents_url: null } });
    expect(await screen.findByTestId("configurar-julia-indisponivel")).toBeTruthy();
  });

  it("error state with retry when the lookup fails", async () => {
    setup(Page, new Error("boom"));
    expect(await screen.findByTestId("movido-erro")).toBeTruthy();
    expect(screen.getByText("Tentar de novo")).toBeTruthy();
  });
});
