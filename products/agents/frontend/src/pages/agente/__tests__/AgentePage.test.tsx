/**
 * AgentePage — the ONE dynamic agent page (agents-unified CONTRACT §7). Stubs the painel/modelo hooks and every
 * section renderer so this asserts ONLY the page: the nav is `painel.secoes` titled by the model, `?tab=` picks
 * the section (deep links survive), the renderer is chosen by the agent's ORIGIN (data, never a key), and the
 * loading / 404 / no-section states. Synthetic fixtures only.
 */
import React from "react";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";
import type { AgenteModelo, AgentePainel } from "@/api/agentes/types";
import AgentePage from "@/pages/agente/AgentePage";

const mockPainel = vi.fn();
const mockModelo = vi.fn();
const mockInterno = vi.fn();

vi.mock("@/hooks/useAgentesPainel", () => ({
  useAgentePainel: (key: string) => mockPainel(key),
  useAgenteModelo: () => mockModelo(),
  useAgenteInterno: (key: string, enabled: boolean) => mockInterno(key, enabled),
}));
vi.mock("@/hooks/useAgents", () => ({ useToggleAgent: () => ({ mutateAsync: vi.fn(), isPending: false }) }));

const stub = (nome: string) => ({
  default: ({ agentKey }: { agentKey: string }) => <div data-testid="renderer">{`${nome}:${agentKey}`}</div>,
});
vi.mock("@/pages/agente/secoes/VisaoGeralSecao", () => stub("visao-geral"));
vi.mock("@/pages/agente/secoes/ConversarLegadoSecao", () => stub("conversar-legado"));
vi.mock("@/pages/agente/secoes/PersonaSecao", () => stub("persona"));
vi.mock("@/pages/studio/tabs/ChatTab", () => stub("chat-studio"));
vi.mock("@/pages/studio/tabs/PromptTab", () => stub("prompt"));
vi.mock("@/pages/studio/tabs/CompiledTab", () => stub("compilado-org"));
vi.mock("@/pages/studio/tabs/CompiladoJuliaTab", () => stub("compilado-plataforma"));

const MODELO: AgenteModelo = {
  versao: 1, tier: "plataforma", conteudo_modo: "linhas", origens: ["legado", "plataforma", "instancia", "org"],
  areas: [], assistente: null,
  secoes: [
    { id: "visao-geral", titulo: "Visão geral", grupo: "painel", tier: "membro", origens: [], area: null, exige: [] },
    { id: "conversar", titulo: "Conversar", grupo: "painel", tier: "membro", origens: [], area: null, exige: [] },
    { id: "persona", titulo: "Persona", grupo: "organizacao", tier: "org_admin", origens: [], area: null, exige: [] },
    { id: "prompt", titulo: "Prompt", grupo: "conteudo", tier: "plataforma", origens: [], area: "secoes", exige: [] },
    { id: "compilado", titulo: "Compilado", grupo: "conteudo", tier: "plataforma", origens: [], area: null, exige: [] },
  ],
};

function agente(over: Partial<AgentePainel>): AgentePainel {
  return {
    key: "x", nome: "X", descricao: null, papel: null, capacidades: [], origem: "org", tipo: "studio",
    runtime: "claude_sdk", owner_product: null, usa_canais: false, ativo: true, estado_externo: null, aviso: null,
    secoes: ["visao-geral"], pode_alternar: false, ...over,
  };
}
const BIA = agente({ key: "bia", nome: "Bia", origem: "legado", secoes: ["visao-geral", "conversar", "persona"] });
const ISAIA = agente({ key: "isaia", nome: "IsaIA", origem: "org", secoes: ["visao-geral", "conversar", "prompt", "compilado"] });
const JULIA = agente({ key: "julia", nome: "Julia", origem: "instancia", secoes: ["visao-geral", "compilado"] });

function q(over: Record<string, unknown>) {
  return { data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

function Where() {
  const { search } = useLocation();
  return <div data-testid="search">{search}</div>;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockModelo.mockReturnValue(q({ data: MODELO }));
  mockInterno.mockReturnValue(q({}));
});
afterEach(() => cleanup());

async function at(url: string, painel: AgentePainel | Record<string, unknown>) {
  mockPainel.mockReturnValue("key" in painel && "secoes" in painel ? q({ data: painel }) : q(painel));
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/agentes/:key" element={<><AgentePage /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AgentePage — sections come from the painel, titled by the model", () => {
  it("renders the header and one tab per painel section", async () => {
    await at("/agentes/bia", BIA);
    expect(screen.getByTestId("agente-nome").textContent).toBe("Bia");
    expect(mockPainel).toHaveBeenCalledWith("bia");
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Visão geral", "Conversar", "Persona"]);
    expect(await screen.findByText("visao-geral:bia")).toBeTruthy();
  });

  it("?tab= opens that section (deep links survive)", async () => {
    await at("/agentes/bia?tab=persona", BIA);
    expect(await screen.findByText("persona:bia")).toBeTruthy();
  });

  it("an unknown or forbidden ?tab= falls back to the first section", async () => {
    await at("/agentes/bia?tab=prompt", BIA);
    expect(await screen.findByText("visao-geral:bia")).toBeTruthy();
  });

  it("clicking a tab switches the section and drops the other deep-link params", async () => {
    await at("/agentes/isaia?tab=prompt&secao=abc", ISAIA);
    expect(await screen.findByText("prompt:isaia")).toBeTruthy();
    fireEvent.click(screen.getByTestId("agente-secao-compilado"));
    expect(await screen.findByText("compilado-org:isaia")).toBeTruthy();
    expect(screen.getByTestId("search").textContent).toBe("?tab=compilado");
  });
});

describe("AgentePage — renderer chosen by origin, never by key", () => {
  it("conversar: legacy agent -> legacy chat; org agent -> Studio chat", async () => {
    await at("/agentes/bia?tab=conversar", BIA);
    expect(await screen.findByText("conversar-legado:bia")).toBeTruthy();
    cleanup();
    await at("/agentes/isaia?tab=conversar", ISAIA);
    expect(await screen.findByText("chat-studio:isaia")).toBeTruthy();
  });

  it("compilado: platform instance -> line-mode compiled view", async () => {
    await at("/agentes/julia?tab=compilado", JULIA);
    expect(await screen.findByText("compilado-plataforma:julia")).toBeTruthy();
  });

  it("asks for internals only when the server opened an internal section", async () => {
    await at("/agentes/isaia", ISAIA);
    expect(mockInterno).toHaveBeenCalledWith("isaia", true);
    cleanup();
    mockInterno.mockClear();
    await at("/agentes/bia", BIA);
    expect(mockInterno).toHaveBeenCalledWith("bia", false);
  });
});

describe("AgentePage — states", () => {
  it("skeleton while the painel has no data yet", async () => {
    await at("/agentes/bia", { showSkeleton: true });
    expect(screen.getByTestId("agente-skeleton")).toBeTruthy();
  });

  it("404 -> 'Agente não encontrado' with retry", async () => {
    await at("/agentes/nope", { isError: true, error: new ApiError(404, "Agente não encontrado.", { detail: "x" }) });
    expect(screen.getByTestId("studio-error").textContent).toContain("Agente não encontrado nesta organização.");
  });

  it("no section for this caller -> restricted notice", async () => {
    await at("/agentes/x", agente({ secoes: [] }));
    expect(screen.getByTestId("agente-sem-secoes")).toBeTruthy();
  });

  it("a section the app does not know yet -> explicit notice, never a blank panel", async () => {
    await at("/agentes/x", agente({ secoes: ["nova-secao"] }));
    expect(screen.getByTestId("agente-secao-desconhecida")).toBeTruthy();
  });
});
