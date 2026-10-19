/**
 * Agentes.tsx page tests — contract §E.2 admin-only toggle gating.
 *
 * Stubs `@/hooks/useAgents` and `@/hooks/useIsAdmin` so this test asserts
 * ONLY the page's role-based rendering (toggle vs. read-only badge), not
 * the hooks themselves (covered by `useAgents.test.ts`).
 */
import React from "react";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUseAgents = vi.fn();
const mockUseToggleAgent = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/useAgents", () => ({
  useAgents: () => mockUseAgents(),
  useToggleAgent: () => mockUseToggleAgent(),
}));

vi.mock("@/hooks/useIsAdmin", () => ({
  useIsAdmin: () => mockUseIsAdmin(),
}));

const BIA = {
  key: "bia",
  nome: "Bia",
  runtime: "claude_sdk",
  owner_product: null,
  ativo: true,
  estado_externo: null,
  aviso: null,
};

const ONE_CHAT = {
  key: "one-chat",
  nome: "One Chat",
  runtime: "external",
  owner_product: "social-wiring",
  ativo: false,
  estado_externo: null,
  aviso: "One Chat ainda não configurado (nenhuma conexão vinculada).",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAgents.mockReturnValue({ data: [BIA, ONE_CHAT], showSkeleton: false, isError: false });
  mockUseToggleAgent.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

afterEach(() => cleanup());

async function renderPage() {
  const Agentes = (await import("@/pages/Agentes")).default;
  render(
    React.createElement(MemoryRouter, null, React.createElement(Agentes)),
  );
}

describe("Agentes — admin sees an interactive toggle", () => {
  it("renders a toggle switch and the persona link for bia", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderPage();

    expect(screen.getByTestId("agent-toggle-bia")).toBeTruthy();
    expect(screen.getByTestId("agent-toggle-one-chat")).toBeTruthy();
    expect(screen.getByTestId("agent-persona-link")).toBeTruthy();
    expect(screen.queryByTestId("agent-status-bia")).toBeNull();
  });

  it("shows the aviso when one-chat's estado_externo is null", async () => {
    mockUseIsAdmin.mockReturnValue(true);
    await renderPage();
    expect(screen.getByTestId("agent-aviso-one-chat").textContent).toBe(
      "One Chat ainda não configurado (nenhuma conexão vinculada).",
    );
  });
});

describe("Agentes — member sees read-only state", () => {
  it("renders a status badge instead of a toggle, and no persona link", async () => {
    mockUseIsAdmin.mockReturnValue(false);
    await renderPage();

    expect(screen.getByTestId("agent-status-bia")).toBeTruthy();
    expect(screen.getByTestId("agent-status-one-chat")).toBeTruthy();
    expect(screen.queryByTestId("agent-toggle-bia")).toBeNull();
    expect(screen.queryByTestId("agent-toggle-one-chat")).toBeNull();
    expect(screen.queryByTestId("agent-persona-link")).toBeNull();
  });
});
