/**
 * CofreAcessos — the Cofre de Acessos, moved from the old Central da Marca
 * page into the Clientes card's Marcas tab (Slice F). These are the page's
 * render-level tests (gaps closed 2026-08-31), MIGRATED with it:
 *
 *   1. The create-acesso error message must be the SERVER'S own text, not
 *      a hardcoded "Se o cofre não estiver configurado…" sentence.
 *   2. "Cofre não configurado" must be visible up front, before any save.
 *   3. Edit / reveal / remove per entry; edit wired to useAtualizarAcesso.
 *
 * `@/hooks/useMarca` is mocked directly — the component drives only its
 * vault hooks, and each gets its own shape.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";

const mockUseAcessos = vi.fn();
const mockCriarAcesso = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockAtualizarAcesso = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockRemoverAcesso = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockRevelarSenha = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };

vi.mock("@/hooks/useMarca", () => ({
  useAcessos: () => mockUseAcessos(),
  useCriarAcesso: () => mockCriarAcesso,
  useAtualizarAcesso: () => mockAtualizarAcesso,
  useRemoverAcesso: () => mockRemoverAcesso,
  useRevelarSenha: () => mockRevelarSenha,
}));

import { CofreAcessos } from "../CofreAcessos";

function renderCofre() {
  render(<CofreAcessos clienteId="c1" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCriarAcesso.isError = false;
  mockCriarAcesso.error = null;
  mockRevelarSenha.isError = false;
  mockRevelarSenha.error = null;
});

describe("CofreAcessos — Cofre error honesty", () => {
  it("REGRESSION: shows the SERVER's own message, not the hardcoded cofre sentence", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: false,
      cofreConfigurado: true,
    });
    mockCriarAcesso.isError = true;
    // A real post-fix failure — not the cofre at all.
    mockCriarAcesso.error = new ApiError(404, "Cliente não encontrado");

    renderCofre();

    expect(screen.getByText(/Cliente não encontrado/)).toBeInTheDocument();
    expect(screen.queryByText(/Se o cofre não estiver configurado/)).not.toBeInTheDocument();
  });
});

describe("CofreAcessos — cofre-not-configured banner", () => {
  it("shows a banner up front when the vault is not configured, even with zero entries", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: false,
      cofreConfigurado: false,
    });

    renderCofre();

    expect(screen.getByText(/Cofre não configurado/)).toBeInTheDocument();
  });

  it("shows no banner once the vault is configured", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: false,
      cofreConfigurado: true,
    });

    renderCofre();

    expect(screen.queryByText(/Cofre não configurado/)).not.toBeInTheDocument();
  });

  it("does not flash the banner while the vault is still loading", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: true,
      cofreConfigurado: null,
    });

    renderCofre();

    expect(screen.queryByText(/Cofre não configurado/)).not.toBeInTheDocument();
  });
});

describe("CofreAcessos — Cofre CRUD", () => {
  it("offers edit, reveal and remove for an existing entry", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [
        { id: "a1", cliente_id: "c1", rotulo: "Meta Business", plataforma: null, url: null,
          usuario: "operador", observacoes: null, tem_senha: true },
      ],
      loading: false,
      cofreConfigurado: true,
    });

    renderCofre();

    expect(screen.getByRole("button", { name: "Editar Meta Business" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remover Meta Business" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revelar" })).toBeInTheDocument();
  });

  it("editing switches the row into an inline form wired to useAtualizarAcesso", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [
        { id: "a1", cliente_id: "c1", rotulo: "Meta Business", plataforma: null, url: null,
          usuario: "operador", observacoes: null, tem_senha: true },
      ],
      loading: false,
      cofreConfigurado: true,
    });

    renderCofre();
    fireEvent.click(screen.getByRole("button", { name: "Editar Meta Business" }));

    const rotuloInput = screen.getByLabelText("Rótulo de Meta Business") as HTMLInputElement;
    expect(rotuloInput.value).toBe("Meta Business");
    fireEvent.change(rotuloInput, { target: { value: "Meta Business — novo" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(mockAtualizarAcesso.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: "a1", rotulo: "Meta Business — novo" }),
      expect.anything(),
    );
  });
});
