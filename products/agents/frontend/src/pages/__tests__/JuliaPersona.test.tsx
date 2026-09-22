/**
 * JuliaPersona.tsx page tests — contract §E.2 (`GET`/`PUT
 * /api/agents/julia/persona`).
 *
 * Stubs `@/hooks/usePersona` and `@/hooks/useIsAdmin` so this test asserts
 * ONLY the page's state rendering (create-mode vs. edit-mode vs. error),
 * not the hooks themselves (covered by `usePersona.test.ts`).
 *
 * Prod defect this covers: Julia's `agents.agent_personas` row can be
 * empty (never created), and the `GET` correctly 404s — the page must
 * treat that as "no persona yet", not as an error, and let the admin
 * create the first version (the existing `PUT` already creates versão 1
 * when none exists).
 */
import React from "react";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockUsePersona = vi.fn();
const mockUseUpdatePersona = vi.fn();
const mockUseIsAdmin = vi.fn();

vi.mock("@/hooks/usePersona", () => ({
  usePersona: () => mockUsePersona(),
  useUpdatePersona: () => mockUseUpdatePersona(),
  PERSONA_MODELS: ["claude-opus-5", "claude-sonnet-5"],
  PERSONA_EFFORTS: ["low", "medium", "high", "xhigh", "max"],
}));

vi.mock("@/hooks/useIsAdmin", () => ({
  useIsAdmin: () => mockUseIsAdmin(),
}));

const PERSONA = {
  versao: 3,
  nome: "Julia",
  papel: "Assistente de conhecimento",
  tom: "acolhedor",
  system_prompt_append: null,
  model: "claude-sonnet-5",
  effort: "medium",
  idioma: "pt-BR",
  org_display_name: null,
  project_display_name: null,
  ativa: true,
  created_by: "u1",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

let mutateAsync: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  mockUseIsAdmin.mockReturnValue(true);
  mutateAsync = vi.fn().mockResolvedValue(PERSONA);
  mockUseUpdatePersona.mockReturnValue({ mutateAsync, isPending: false });
});

afterEach(() => cleanup());

async function renderPage() {
  const JuliaPersona = (await import("@/pages/JuliaPersona")).default;
  render(React.createElement(MemoryRouter, null, React.createElement(JuliaPersona)));
}

describe("JuliaPersona — no persona yet (404, contract §E.2 not_found)", () => {
  it("renders the form in create mode: no version badge, 'Criar persona' button", async () => {
    mockUsePersona.mockReturnValue({
      data: undefined,
      showSkeleton: false,
      isRefreshing: false,
      isError: false,
      isNotFound: true,
    });
    await renderPage();

    expect(screen.queryByTestId("persona-version")).toBeNull();
    expect(screen.getByTestId("persona-create-notice")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Criar persona" })).toBeTruthy();
    // Defaults: nome pre-filled, papel/tom/system_prompt_append left blank.
    expect(screen.getByLabelText("Nome *")).toHaveProperty("value", "Julia");
    expect(screen.getByLabelText("Papel *")).toHaveProperty("value", "");
  });

  it("submits a valid PUT payload from create mode", async () => {
    mockUsePersona.mockReturnValue({
      data: undefined,
      showSkeleton: false,
      isRefreshing: false,
      isError: false,
      isNotFound: true,
    });
    await renderPage();

    fireEvent.change(screen.getByLabelText("Papel *"), {
      target: { value: "Assistente da Academia de Reciclagem" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Criar persona" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const payload = mutateAsync.mock.calls[0][0];
    expect(payload).toMatchObject({
      nome: "Julia",
      papel: "Assistente da Academia de Reciclagem",
      model: "claude-sonnet-5",
      effort: "medium",
      idioma: "pt-BR",
    });
    // The backend's CHECK constraints (`MODELS`/`EFFORTS`,
    // `app/stores/personas.py`) only allow the values above — never an
    // invented default.
    expect(["claude-opus-5", "claude-sonnet-5"]).toContain(payload.model);
    expect(["low", "medium", "high", "xhigh", "max"]).toContain(payload.effort);
  });
});

describe("JuliaPersona — genuine failure (5xx/network)", () => {
  it("renders the error card, not the form", async () => {
    mockUsePersona.mockReturnValue({
      data: undefined,
      showSkeleton: false,
      isRefreshing: false,
      isError: true,
      isNotFound: false,
    });
    await renderPage();

    expect(screen.getByText("Erro ao carregar a persona.")).toBeTruthy();
    expect(screen.queryByTestId("persona-create-notice")).toBeNull();
    expect(screen.queryByRole("button", { name: "Criar persona" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Salvar" })).toBeNull();
  });
});

describe("JuliaPersona — existing persona", () => {
  it("renders current behaviour: version badge, 'Salvar' button, no create notice", async () => {
    mockUsePersona.mockReturnValue({
      data: PERSONA,
      showSkeleton: false,
      isRefreshing: false,
      isError: false,
      isNotFound: false,
    });
    await renderPage();

    expect(screen.getByTestId("persona-version").textContent).toBe("Versão 3");
    expect(screen.queryByTestId("persona-create-notice")).toBeNull();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeTruthy();
    expect(screen.getByLabelText("Nome *")).toHaveProperty("value", "Julia");
    expect(screen.getByLabelText("Papel *")).toHaveProperty("value", "Assistente de conhecimento");
  });
});
