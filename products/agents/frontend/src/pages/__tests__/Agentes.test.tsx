/**
 * Agentes.tsx — the unified listing (agents-unified CONTRACT §4.1/§7). Stubs the painel + toggle hooks so this
 * asserts ONLY the page: one card per agent, origin/state from DATA, the switch only when `pode_alternar`, and the
 * loading / empty / error states. Synthetic fixtures only.
 */
import React from "react";
import { render, screen, cleanup, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentePainel } from "@/api/agentes/types";
import Agentes from "@/pages/Agentes";

const mockUsePainel = vi.fn();
const mockTier = vi.fn();
const mockIsAdmin = vi.fn();
const mutateAsync = vi.fn();

vi.mock("@/hooks/useAgentesPainel", () => ({
  useAgentesPainel: () => mockUsePainel(),
  useAgenteModelo: () => ({ data: { tier: mockTier() } }),
}));
vi.mock("@/hooks/useAgents", () => ({ useToggleAgent: () => ({ mutateAsync, isPending: false }) }));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockIsAdmin() }));
vi.mock("@/components/studio/ContentTokenCard", () => ({ ContentTokenCard: () => <div data-testid="content-token" /> }));
vi.mock("@/components/studio/ImportBundleDialog", () => ({ ImportBundleDialog: () => <div data-testid="dlg-importar" /> }));
vi.mock("@/components/studio/ExcluirAgenteDialog", () => ({
  ExcluirAgenteDialog: ({ agentKey }: { agentKey: string }) => <div data-testid={`dlg-excluir-${agentKey}`} />,
}));

function agente(over: Partial<AgentePainel>): AgentePainel {
  return {
    key: "x", nome: "X", descricao: null, papel: null, capacidades: [], origem: "org", tipo: "studio",
    runtime: "claude_sdk", owner_product: null, usa_canais: false, ativo: true, estado_externo: null, aviso: null,
    secoes: ["visao-geral"], pode_alternar: false, ...over,
  };
}

const BIA = agente({ key: "bia", nome: "Bia", origem: "legado", papel: "academia", descricao: "Agente da academia.", pode_alternar: true });
const JULIA = agente({ key: "julia", nome: "Julia", origem: "instancia", papel: "sdr", capacidades: ["Qualifica leads"] });
const ONE_CHAT = agente({
  key: "one-chat", nome: "One Chat", origem: "legado", runtime: "external", ativo: false,
  aviso: "One Chat ainda não configurado.",
});

function estado(over: Record<string, unknown>) {
  return { data: undefined, showSkeleton: false, isRefreshing: false, isError: false, refetch: vi.fn(), ...over };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTier.mockReturnValue("membro");
  mockIsAdmin.mockReturnValue(false);
  mutateAsync.mockResolvedValue({});
  mockUsePainel.mockReturnValue(estado({ data: [BIA, JULIA, ONE_CHAT] }));
});
afterEach(() => cleanup());

async function renderPage() {
  render(React.createElement(MemoryRouter, null, React.createElement(Agentes)));
}

describe("Agentes — one card per agent", () => {
  it("renders every agent of the painel, each opening /agentes/:key", async () => {
    await renderPage();
    for (const a of [BIA, JULIA, ONE_CHAT]) {
      expect(screen.getByTestId(`agente-card-${a.key}`)).toBeTruthy();
      expect(screen.getByTestId(`agente-abrir-${a.key}`).getAttribute("href")).toBe(`/agentes/${a.key}`);
    }
  });

  it("labels the origin from data", async () => {
    await renderPage();
    expect(screen.getByTestId("agente-origem-bia").textContent).toBe("Agente legado");
    expect(screen.getByTestId("agente-origem-julia").textContent).toBe("Agente da plataforma");
  });

  it("offers the switch only when the server says pode_alternar", async () => {
    await renderPage();
    fireEvent.click(screen.getByTestId("agente-toggle-bia"));
    expect(mutateAsync).toHaveBeenCalledWith({ key: "bia", ativo: false });
    expect(screen.queryByTestId("agente-toggle-julia")).toBeNull();
    expect(screen.getByTestId("agente-status-julia").textContent).toBe("Ligado");
  });

  it("shows an external agent's warning instead of a description", async () => {
    await renderPage();
    expect(screen.getByTestId("agente-aviso-one-chat").textContent).toBe("One Chat ainda não configurado.");
    expect(within(screen.getByTestId("agente-card-julia")).getByText("Qualifica leads")).toBeTruthy();
  });

  it("filters by papel", async () => {
    await renderPage();
    fireEvent.click(screen.getByTestId("agentes-filtro-sdr"));
    expect(screen.queryByTestId("agente-card-bia")).toBeNull();
    expect(screen.getByTestId("agente-card-julia")).toBeTruthy();
  });
});

describe("Agentes — states", () => {
  it("skeleton while there is no data yet", async () => {
    mockUsePainel.mockReturnValue(estado({ showSkeleton: true }));
    await renderPage();
    expect(screen.getByTestId("agentes-skeleton")).toBeTruthy();
  });

  it("empty state", async () => {
    mockUsePainel.mockReturnValue(estado({ data: [] }));
    await renderPage();
    expect(screen.getByTestId("agentes-empty")).toBeTruthy();
  });

  it("error state with retry", async () => {
    const refetch = vi.fn();
    mockUsePainel.mockReturnValue(estado({ isError: true, refetch }));
    await renderPage();
    expect(screen.getByTestId("agentes-error")).toBeTruthy();
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("keeps the cards on screen during a background refetch", async () => {
    mockUsePainel.mockReturnValue(estado({ data: [BIA], isRefreshing: true }));
    await renderPage();
    expect(screen.getByTestId("agente-card-bia")).toBeTruthy();
    expect(screen.getByTestId("agentes-refreshing")).toBeTruthy();
  });
});

describe("Agentes — the former /studio console actions", () => {
  it("a platform admin gets the wizard, the skills library, the delete and the content token", async () => {
    mockTier.mockReturnValue("plataforma");
    mockIsAdmin.mockReturnValue(true);
    await renderPage();
    expect(screen.getByTestId("agentes-novo").getAttribute("href")).toBe("/agentes/novo");
    expect(screen.getByTestId("agentes-biblioteca-skills")).toBeTruthy();
    expect(screen.getByTestId("content-token")).toBeTruthy();
    // a legacy / external agent has no delete; a platform agent does, behind the typed-key confirm
    expect(screen.queryByTestId("agente-excluir-bia")).toBeNull();
    expect(screen.queryByTestId("agente-excluir-one-chat")).toBeNull();
    fireEvent.click(screen.getByTestId("agente-excluir-julia"));
    expect(screen.getByTestId("dlg-excluir-julia")).toBeTruthy();
    fireEvent.click(screen.getByTestId("agentes-importar-pacote"));
    expect(screen.getByTestId("dlg-importar")).toBeTruthy();
  });

  it("an org admin can import a bundle but not create, delete or mint tokens", async () => {
    mockIsAdmin.mockReturnValue(true);
    await renderPage();
    expect(screen.getByTestId("agentes-importar-pacote")).toBeTruthy();
    expect(screen.queryByTestId("agentes-novo")).toBeNull();
    expect(screen.queryByTestId("agente-excluir-julia")).toBeNull();
    expect(screen.queryByTestId("content-token")).toBeNull();
  });

  it("a member sees no console action", async () => {
    await renderPage();
    expect(screen.queryByTestId("agentes-importar-pacote")).toBeNull();
    expect(screen.queryByTestId("agentes-novo")).toBeNull();
  });
});
