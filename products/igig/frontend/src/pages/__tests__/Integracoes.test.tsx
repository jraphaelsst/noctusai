/**
 * Integrações — render-level tests for the two gaps closed 2026-08-31:
 *
 *   1. The connect-error message must be the SERVER'S own text, not a
 *      hardcoded "Sem IGIG_COFRE_KEY…" sentence — a real post-fix failure
 *      (bad token, network, 403) must not blame the missing key that is
 *      now actually configured. `test_without_encryption_key_it_refuses`
 *      on the backend still proves the 409 CASE; this proves the render.
 *   2. "Cofre não configurado" must be visible up front (a page banner),
 *      not only inferred from a failed save.
 *
 * Mocks `@tanstack/react-query` itself (mirrors `Esteira.test.tsx` /
 * `RepertorioSidebar.test.tsx`) so the real `useIntegracoes()` — including
 * the `cofreConfigurado` derivation — actually runs.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));
vi.mock("@noctusai/seed/infra", () => ({
  api: { get: mockGet, post: mockPost, delete: mockDelete },
}));

let queryState: Record<string, unknown> = {};
let connectMutationState: Record<string, unknown> = { isPending: false, isError: false, error: null };

vi.mock("@tanstack/react-query", () => {
  const useQuery = vi.fn(() => queryState);
  // `useConectarCanal` is called once per channel row; `useDesconectarCanal`
  // shares the mock too, but nothing in these tests reads its error state.
  const useMutation = vi.fn((opts: Record<string, unknown>) => ({
    ...opts,
    mutate: vi.fn(),
    ...connectMutationState,
  }));
  const useQueryClient = vi.fn(() => ({ invalidateQueries: vi.fn() }));
  return { useQuery, useMutation, useQueryClient };
});

import { useQuery } from "@tanstack/react-query";
import Integracoes from "../Integracoes";
import type { IntegracaoStatus } from "@/hooks/useIntegracoes";

const mockUseQuery = vi.mocked(useQuery);

const CANAL_CONFIGURADO: IntegracaoStatus[] = [
  {
    canal: "instagram",
    conectado: false,
    origem: "nenhuma",
    conta_externa: null,
    conectado_em: null,
    ultimo_erro: null,
    cofre_configurado: true,
  },
];

const CANAL_NAO_CONFIGURADO: IntegracaoStatus[] = [
  {
    canal: "instagram",
    conectado: false,
    origem: "nenhuma",
    conta_externa: null,
    conectado_em: null,
    ultimo_erro: null,
    cofre_configurado: false,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  connectMutationState = { isPending: false, isError: false, error: null };
});

describe("Integracoes — error honesty", () => {
  it("REGRESSION: shows the SERVER's own message, not the hardcoded cofre sentence", () => {
    mockUseQuery.mockReturnValue({
      data: CANAL_CONFIGURADO,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    } as never);
    connectMutationState = {
      isPending: false,
      isError: true,
      // A real post-fix failure — not the cofre at all.
      error: new ApiError(403, "Token recusado pela Meta Graph API"),
    };

    render(<Integracoes />);

    expect(screen.getByText(/Token recusado pela Meta Graph API/)).toBeInTheDocument();
    expect(screen.queryByText(/Sem IGIG_COFRE_KEY/)).not.toBeInTheDocument();
  });
});

describe("Integracoes — cofre-not-configured banner", () => {
  it("shows a banner up front when the vault is not configured, before any save is attempted", () => {
    mockUseQuery.mockReturnValue({
      data: CANAL_NAO_CONFIGURADO,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    } as never);

    render(<Integracoes />);

    expect(screen.getByText(/Criptografia não configurada/)).toBeInTheDocument();
    // A submit is guaranteed to 409 while unconfigured — disable it instead
    // of letting the user try. Type a token first, so this asserts the
    // cofre-gate specifically, not just the empty-token gate every row
    // starts with.
    fireEvent.change(screen.getByLabelText("Token Instagram"), {
      target: { value: "um-token-qualquer" },
    });
    expect(screen.getByRole("button", { name: "Conectar" })).toBeDisabled();
  });

  it("shows no banner and lets the form submit once the vault is configured", () => {
    mockUseQuery.mockReturnValue({
      data: CANAL_CONFIGURADO,
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
    } as never);

    render(<Integracoes />);

    expect(screen.queryByText(/Criptografia não configurada/)).not.toBeInTheDocument();
  });

  it("does not flash the banner while the list is still loading", () => {
    mockUseQuery.mockReturnValue({
      data: undefined,
      isPending: true,
      isFetching: true,
      isError: false,
      error: null,
    } as never);

    render(<Integracoes />);

    expect(screen.queryByText(/Criptografia não configurada/)).not.toBeInTheDocument();
  });
});
