/**
 * Marca (Central da Marca / Cofre de Acessos) — render-level tests for the
 * two gaps closed 2026-08-31, mirroring `Integracoes.test.tsx`:
 *
 *   1. The create-acesso error message must be the SERVER'S own text, not
 *      the hardcoded "Se o cofre não estiver configurado…" sentence.
 *   2. "Cofre não configurado" must be visible up front, before any save.
 *
 * `@/hooks/useMarca` and `@/hooks/useClientes` are mocked directly (rather
 * than mocking `@tanstack/react-query` itself, the pattern
 * `RepertorioSidebar.test.tsx` uses) — Marca.tsx drives FOUR different
 * query hooks (clientes, marcas, acessos, plus RepertorioSidebar's own
 * repertório), so a single shared `queryState` can't give each one its own
 * shape. `RepertorioSidebar` itself is stubbed out — it is exercised by
 * its own colocated test.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";

vi.mock("@/components/RepertorioSidebar", () => ({
  RepertorioSidebar: () => null,
}));

const mockUseClientes = vi.fn();
vi.mock("@/hooks/useClientes", () => ({
  useClientes: () => mockUseClientes(),
}));

const mockUseMarcas = vi.fn();
const mockUseAcessos = vi.fn();
const mockCriarAcesso = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockAtualizarAcesso = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockRemoverAcesso = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockRevelarSenha = { mutate: vi.fn(), isPending: false, isError: false, error: null as unknown };
const mockCriarMarca = { mutate: vi.fn(), isPending: false };
const mockAtualizarMarca = { mutate: vi.fn(), isPending: false };

vi.mock("@/hooks/useMarca", () => ({
  useMarcas: () => mockUseMarcas(),
  useAcessos: () => mockUseAcessos(),
  useCriarAcesso: () => mockCriarAcesso,
  useAtualizarAcesso: () => mockAtualizarAcesso,
  useRemoverAcesso: () => mockRemoverAcesso,
  useRevelarSenha: () => mockRevelarSenha,
  useCriarMarca: () => mockCriarMarca,
  useAtualizarMarca: () => mockAtualizarMarca,
}));

import Marca from "../Marca";

const CLIENTE = { id: "c1", nome: "Padaria Sol" };

function selecionarCliente() {
  fireEvent.change(screen.getByLabelText("Cliente"), { target: { value: "c1" } });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseClientes.mockReturnValue({ clientes: [CLIENTE], loading: false });
  mockUseMarcas.mockReturnValue({ marcas: [], loading: false });
  mockCriarAcesso.isError = false;
  mockCriarAcesso.error = null;
  mockRevelarSenha.isError = false;
  mockRevelarSenha.error = null;
});

describe("Marca — Cofre error honesty", () => {
  it("REGRESSION: shows the SERVER's own message, not the hardcoded cofre sentence", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: false,
      cofreConfigurado: true,
    });
    mockCriarAcesso.isError = true;
    // A real post-fix failure — not the cofre at all.
    mockCriarAcesso.error = new ApiError(404, "Cliente não encontrado");

    render(<Marca />);
    selecionarCliente();

    expect(screen.getByText(/Cliente não encontrado/)).toBeInTheDocument();
    expect(screen.queryByText(/Se o cofre não estiver configurado/)).not.toBeInTheDocument();
  });
});

describe("Marca — cofre-not-configured banner", () => {
  it("shows a banner up front when the vault is not configured, even with zero entries", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: false,
      cofreConfigurado: false,
    });

    render(<Marca />);
    selecionarCliente();

    expect(screen.getByText(/Cofre não configurado/)).toBeInTheDocument();
  });

  it("shows no banner once the vault is configured", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: false,
      cofreConfigurado: true,
    });

    render(<Marca />);
    selecionarCliente();

    expect(screen.queryByText(/Cofre não configurado/)).not.toBeInTheDocument();
  });

  it("does not flash the banner while the vault is still loading", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [],
      loading: true,
      cofreConfigurado: null,
    });

    render(<Marca />);
    selecionarCliente();

    expect(screen.queryByText(/Cofre não configurado/)).not.toBeInTheDocument();
  });
});

describe("Marca — Cofre CRUD", () => {
  it("offers edit, reveal and remove for an existing entry", () => {
    mockUseAcessos.mockReturnValue({
      acessos: [
        { id: "a1", cliente_id: "c1", rotulo: "Meta Business", plataforma: null, url: null,
          usuario: "operador", observacoes: null, tem_senha: true },
      ],
      loading: false,
      cofreConfigurado: true,
    });

    render(<Marca />);
    selecionarCliente();

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

    render(<Marca />);
    selecionarCliente();
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
