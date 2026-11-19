/** CotaCriacaoDialog: parses dollars, blocks invalid input, saves the cap, loading/error states honest. */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ cota: vi.fn(), mutate: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/hooks/geracao/useCriacao", () => ({
  COTA_PADRAO_USD: 15,
  useCotaCriacao: () => m.cota(),
  useAtualizarCota: () => ({ mutate: m.mutate, isPending: false }),
}));

import { CotaCriacaoDialog, parseLimiteUsd } from "./CotaCriacaoDialog";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const ok = { data: { limite_usd_mes: 15, gasto_usd_mes: 3, padrao_usd_mes: 15 }, showSkeleton: false, isError: false, refetch: vi.fn() };

describe("parseLimiteUsd", () => {
  it("aceita vírgula e ponto, recusa vazio, negativo e texto", () => {
    expect(parseLimiteUsd("15")).toBe(15);
    expect(parseLimiteUsd("15,50")).toBe(15.5);
    expect(parseLimiteUsd("")).toBeNull();
    expect(parseLimiteUsd("-1")).toBeNull();
    expect(parseLimiteUsd("abc")).toBeNull();
  });
});

describe("CotaCriacaoDialog", () => {
  it("mostra o limite atual e salva o novo valor", () => {
    m.cota.mockReturnValue(ok);
    render(<CotaCriacaoDialog open onClose={vi.fn()} />);
    const campo = screen.getByLabelText("Limite mensal em dólares");
    expect(campo).toHaveValue("15");
    fireEvent.change(campo, { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(m.mutate.mock.calls[0][0]).toEqual({ limite_usd_mes: 30 });
  });

  it("valor inválido bloqueia o Salvar e explica", () => {
    m.cota.mockReturnValue(ok);
    render(<CotaCriacaoDialog open onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Limite mensal em dólares"), { target: { value: "dez" } });
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
    expect(screen.getByText(/Use um valor em dólares/)).toBeInTheDocument();
  });

  it("erro de leitura mostra mensagem e bloqueia o Salvar", () => {
    m.cota.mockReturnValue({ data: undefined, showSkeleton: false, isError: true, refetch: vi.fn() });
    render(<CotaCriacaoDialog open onClose={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível carregar o limite mensal.");
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
  });
});
