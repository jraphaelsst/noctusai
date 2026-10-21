/** StudioAgent shell — the tier decides which tabs render (CONTRACT §0.4), from the server's definition_scope. */
import { cleanup, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { KEY, agentDetail } from "../tabs/__tests__/juliaFixtures";
import { renderWith } from "../tabs/__tests__/harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
const mockOrgAdmin = vi.fn(() => true);
const mockPlatform = vi.fn(() => false);
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockOrgAdmin() }));
vi.mock("@/hooks/useIsPlatformAdmin", () => ({ useIsPlatformAdmin: () => mockPlatform() }));
// Tab bodies are covered by their own tests; the shell test only needs a landing stub.
vi.mock("../tabs/OverviewTab", () => ({ default: () => <div data-testid="stub-overview" /> }));
vi.mock("../tabs/InstanciaOverviewTab", () => ({ default: () => <div data-testid="stub-instancia-overview" /> }));

import StudioAgent from "../StudioAgent";

const mount = () =>
  renderWith(
    <Routes>
      <Route path="/studio/:key" element={<StudioAgent />} />
    </Routes>,
    `/studio/${KEY}`,
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  mockOrgAdmin.mockReturnValue(true);
  mockPlatform.mockReturnValue(false);
});

const tabIds = () => screen.getAllByRole("tab").map((el) => el.getAttribute("data-testid"));

describe("StudioAgent tiers", () => {
  it("platform admin on the definition sees Prompt, Ferramentas, Qualificação and the rest", async () => {
    mockPlatform.mockReturnValue(true);
    installFetch([{ method: "GET", path: `/api/studio/agents/${KEY}`, body: agentDetail({ definition_scope: "plataforma" }) }]);
    mount();
    expect(await screen.findByTestId("studio-agent-escopo")).toBeTruthy();
    const ids = tabIds();
    for (const t of ["prompt", "ferramentas", "qualificacao", "textos", "decisoes", "biblioteca", "especificacoes", "conformidade", "conversas", "compilado"]) {
      expect(ids).toContain(`studio-tab-${t}`);
    }
    // The overview tab mounts after the tab list (a separate render pass) — wait for it, don't race it (CI a447ae5d3).
    expect(await screen.findByTestId("stub-overview")).toBeTruthy();
  });

  it("org admin on the instance sees the specs form, controls, conversations — not Prompt/Ferramentas/Qualificação", async () => {
    installFetch([{ method: "GET", path: `/api/studio/agents/${KEY}`, body: agentDetail({ definition_scope: "instancia", tem_rascunho: false, versoes: [] }) }]);
    mount();
    await screen.findByTestId("studio-tab-especificacoes-org");
    expect(tabIds()).toEqual(["studio-tab-visao-geral", "studio-tab-especificacoes-org", "studio-tab-controles", "studio-tab-conversas"]);
    expect(screen.queryByTestId("studio-tab-prompt")).toBeNull();
    expect(screen.queryByTestId("studio-tab-ferramentas")).toBeNull();
    expect(screen.queryByTestId("studio-tab-qualificacao")).toBeNull();
    expect(await screen.findByTestId("stub-instancia-overview")).toBeTruthy();
  });

  it("org member gets no Studio content tabs", async () => {
    mockOrgAdmin.mockReturnValue(false);
    installFetch([{ method: "GET", path: `/api/studio/agents/${KEY}`, body: agentDetail({ definition_scope: "instancia", tem_rascunho: false, versoes: [] }) }]);
    mount();
    expect(await screen.findByTestId("studio-sem-acesso")).toBeTruthy();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });

  it("a legacy agent keeps its pre-v2 tabs", async () => {
    installFetch([{ method: "GET", path: `/api/studio/agents/${KEY}`, body: agentDetail({ definition_scope: "org", conteudo_modo: "legado" }) }]);
    mount();
    await screen.findByTestId("studio-tab-prompt");
    expect(screen.queryByTestId("studio-tab-textos")).toBeNull();
    expect(screen.queryByTestId("studio-agent-escopo")).toBeNull();
  });
});
