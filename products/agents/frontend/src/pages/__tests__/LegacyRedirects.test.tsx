/** Old routes -> the unified agent page (agents-unified CONTRACT §7), query + hash kept. The academia URLs follow
 * the server's answer (Renata cutover), never a key hard-coded in the client. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { get: mockGet } }));

import {
  RedirectAcademiaChat,
  RedirectAcademiaPersona,
  RedirectAgentePersona,
  RedirectCatalogo,
  RedirectLeadImobStudioToJulia,
  RedirectStudio,
  RedirectStudioAgent,
} from "../LegacyRedirects";

function Where() {
  const { pathname, search, hash } = useLocation();
  return <div data-testid="where">{pathname + search + hash}</div>;
}

function at(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/bia" element={<RedirectAcademiaChat />} />
          <Route path="/julia" element={<RedirectAcademiaChat />} />
          <Route path="/agentes/catalogo" element={<RedirectCatalogo />} />
          <Route path="/agentes/julia/persona" element={<RedirectAcademiaPersona />} />
          <Route path="/agentes/bia/persona" element={<RedirectAcademiaPersona />} />
          <Route path="/agentes/bia/conversar" element={<RedirectAcademiaChat />} />
          <Route path="/agentes/:key/persona" element={<RedirectAgentePersona />} />
          <Route path="/studio" element={<RedirectStudio />} />
          <Route path="/studio/lead-imob" element={<RedirectLeadImobStudioToJulia />} />
          <Route path="/studio/:key" element={<RedirectStudioAgent />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const where = async () => (await screen.findByTestId("where")).textContent;

beforeEach(() => {
  mockGet.mockReset();
});

describe("old agent shells redirect to /agentes/:key", () => {
  it("/studio/:key -> /agentes/:key, keeping the deep-link query and hash", async () => {
    at("/studio/isaia?tab=prompt&secao=abc#x");
    expect(await where()).toBe("/agentes/isaia?tab=prompt&secao=abc#x");
  });
  it("/agentes/:key/persona -> ?tab=persona", async () => {
    at("/agentes/isaia/persona");
    expect(await where()).toBe("/agentes/isaia?tab=persona");
  });
  it("/agentes/catalogo -> /agentes", async () => {
    at("/agentes/catalogo");
    expect(await where()).toBe("/agentes");
  });
  it("/studio (the former console) -> /agentes, where its actions now live", async () => {
    at("/studio");
    expect(await where()).toBe("/agentes");
  });
  it("/studio/lead-imob -> /agentes/julia, keeping the query and hash", async () => {
    at("/studio/lead-imob?tab=canais#x");
    expect(await where()).toBe("/agentes/julia?tab=canais#x");
  });
});

describe("the academia URLs follow the server", () => {
  it("/bia -> the agent the server names (after the cutover: the Studio agent)", async () => {
    mockGet.mockResolvedValue({ key: "renata", origem: "academia" });
    at("/bia");
    expect(await where()).toBe("/agentes/renata?tab=conversar");
    expect(mockGet).toHaveBeenCalledWith("/api/agents/painel/destino-chat");
  });
  it("/julia and /agentes/bia/conversar -> the same chat section", async () => {
    mockGet.mockResolvedValue({ key: "bia", origem: "legado" });
    at("/julia");
    expect(await where()).toBe("/agentes/bia?tab=conversar");
  });
  it("/agentes/bia/persona and /agentes/julia/persona -> that agent's persona section", async () => {
    mockGet.mockResolvedValue({ key: "renata", origem: "academia" });
    at("/agentes/bia/persona?x=1");
    expect(await where()).toBe("/agentes/renata?x=1&tab=persona");
  });
  it("shows a status (never a guessed destination) while the server answers", () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    at("/bia");
    expect(screen.getByRole("status").textContent).toContain("Abrindo o agente");
    expect(screen.queryByTestId("where")).toBeNull();
  });
  it("an org without an in-app chat agent lands on the listing", async () => {
    mockGet.mockRejectedValue(new Error("404"));
    at("/bia");
    expect(await where()).toBe("/agentes");
  });
});
