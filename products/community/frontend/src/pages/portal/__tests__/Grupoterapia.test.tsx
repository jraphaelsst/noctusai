/**
 * Portal grupoterapia — CONTRACT.md §Grupoterapia (member): `bloqueado` →
 * upgrade card and NO room link; `ouvir` → "Assistir"; `falar` → reserve /
 * cancel seat. Care line on every grupoterapia screen.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn(), mockDelete: vi.fn() }));
vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: mockDelete },
}));

import PortalGrupoterapia from "@/pages/portal/Grupoterapia";
import { renderPortal } from "./_harness";

const base = {
  descricao: null,
  inicio: "2026-10-05T22:00:00Z",
  duracao_minutos: 90,
  status: "agendada",
  vagas_fala: 5,
  vagas_restantes: 3,
  minha_reserva: false,
};

beforeEach(() => vi.clearAllMocks());

describe("PortalGrupoterapia", () => {
  it("bloqueado: shows the upgrade path and no room link", async () => {
    mockGet.mockResolvedValue({
      nivel: "nenhum",
      items: [{ ...base, id: "s1", titulo: "Perder um lugar", acesso: "bloqueado", link_sala: null }],
    });
    renderPortal(<PortalGrupoterapia />);
    const card = await screen.findByTestId("sessao-s1");
    expect(within(card).getByTestId("sessao-bloqueada")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Ver planos" })).toHaveAttribute("href", "/portal");
    expect(within(card).queryByRole("link", { name: /Assistir|Entrar na sala/ })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("CVV 188");
  });

  it("ouvir: renders the Assistir link to the room", async () => {
    mockGet.mockResolvedValue({
      nivel: "ouvir",
      items: [{ ...base, id: "s2", titulo: "Travessia", acesso: "ouvir", link_sala: "https://sala.exemplo/abc" }],
    });
    renderPortal(<PortalGrupoterapia />);
    const link = await screen.findByRole("link", { name: "Assistir" });
    expect(link).toHaveAttribute("href", "https://sala.exemplo/abc");
    expect(screen.queryByRole("button", { name: /vez de fala/ })).not.toBeInTheDocument();
  });

  it("falar: reserves a speaking seat and shows vagas restantes", async () => {
    mockGet.mockResolvedValue({
      nivel: "falar",
      items: [{ ...base, id: "s3", titulo: "Reencontro", acesso: "falar", link_sala: "https://sala.exemplo/x" }],
    });
    mockPost.mockResolvedValue({ status: "confirmada" });
    renderPortal(<PortalGrupoterapia />);
    expect(await screen.findByText("3 vagas de fala disponíveis.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reservar minha vez de fala" }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/portal/grupoterapia/s3/reserva", {}));
    expect(screen.getByRole("link", { name: "Entrar na sala" })).toHaveAttribute("href", "https://sala.exemplo/x");
  });

  it("falar: shows the 409 lotada text verbatim", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockResolvedValue({
      nivel: "falar",
      items: [{ ...base, id: "s4", titulo: "Reencontro", acesso: "falar", link_sala: null }],
    });
    mockPost.mockRejectedValue(new ApiError(409, "Não há mais vagas de fala nesta sessão."));
    renderPortal(<PortalGrupoterapia />);
    fireEvent.click(await screen.findByRole("button", { name: "Reservar minha vez de fala" }));
    expect(await screen.findByText("Não há mais vagas de fala nesta sessão.")).toBeInTheDocument();
  });

  it("falar with a reservation: cancels it", async () => {
    mockGet.mockResolvedValue({
      nivel: "falar",
      items: [{ ...base, id: "s5", titulo: "Reencontro", acesso: "falar", link_sala: null, minha_reserva: true }],
    });
    mockDelete.mockResolvedValue(undefined);
    renderPortal(<PortalGrupoterapia />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar minha vez de fala" }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/portal/grupoterapia/s5/reserva"));
  });

  it("empty state + care line", async () => {
    mockGet.mockResolvedValue({ nivel: "ouvir", items: [] });
    renderPortal(<PortalGrupoterapia />);
    expect(await screen.findByText(/Nenhum encontro agendado/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("CVV 188");
  });
});
