/**
 * Equipe page — the rewrite off the seed pattern (achado #18): TanStack
 * Query, correct pt-BR accents, the TWO admin gates (canManageTeam for
 * Convidar vs. useIsOrgAdmin for Ações/Convites — plat achado #4), and a
 * shown (never swallowed) invitations-fetch error.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api, user } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  user: { current: { id: "u1", user_metadata: { org_role: "admin" } as Record<string, unknown> } },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: user.current }) }));

import Equipe from "../Equipe";

const MEMBROS = [
  { id: "u1", nome: "Ana Owner", email: "ana@agencia.com", role: "owner", org_role: "owner", created_at: "2026-01-10T10:00:00Z" },
  { id: "u2", nome: "Beto Membro", email: "beto@agencia.com", role: "member", org_role: "member", created_at: "2026-02-01T10:00:00Z" },
];
const CONVITE = { id: "c1", email: "novo@agencia.com", role: "manager", status: "pending", created_at: "2026-09-01T10:00:00Z", expires_at: "2026-09-08T10:00:00Z" };

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Equipe />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  user.current = { id: "u1", user_metadata: { org_role: "admin" } };
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/team") return { data: MEMBROS };
    if (path === "/api/team/invitations") return { data: [CONVITE] };
    throw new Error(`GET inesperado ${path}`);
  });
  api.post.mockResolvedValue({ data: { ...CONVITE, id: "c2" } });
  api.delete.mockResolvedValue({ ok: true });
});
afterEach(cleanup);

describe("Equipe — lista + acentuação (achado #18)", () => {
  it("lists members with correctly-accented labels and pt-BR role labels", async () => {
    renderPage();
    expect(await screen.findByText("Ana Owner")).toBeInTheDocument();
    expect(screen.getByText("Você")).toBeInTheDocument();
    expect(screen.getByText("Proprietário")).toBeInTheDocument();
    expect(screen.getByText("Membro")).toBeInTheDocument();
    expect(screen.getByText(/na organização/)).toBeInTheDocument();
  });

  it("shows the server's error instead of a silent empty state", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/team") throw new Error("banco indisponível");
      if (path === "/api/team/invitations") return { data: [] };
      throw new Error(`GET inesperado ${path}`);
    });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("banco indisponível");
  });
});

describe("Equipe — o convite pode ser aberto por manager, não só admin (plat achado #4)", () => {
  it("an org admin sees Convidar AND Ações/Convites pendentes", async () => {
    user.current = { id: "u1", user_metadata: { org_role: "admin" } };
    renderPage();
    await screen.findByText("Ana Owner");
    expect(screen.getByTestId("equipe-convidar")).toBeInTheDocument();
    expect(screen.getByText("Convites pendentes")).toBeInTheDocument();
    expect(screen.getAllByText("Ações").length).toBeGreaterThan(0);
  });

  it("a manager sees Convidar but NOT Ações/Convites pendentes (canManageTeam ≠ useIsOrgAdmin)", async () => {
    user.current = { id: "u2", user_metadata: { org_role: "manager" } };
    renderPage();
    await screen.findByText("Ana Owner");
    expect(screen.getByTestId("equipe-convidar")).toBeInTheDocument();
    expect(screen.queryByText("Convites pendentes")).not.toBeInTheDocument();
    expect(screen.queryByText("Ações")).not.toBeInTheDocument();
    // The seed never even calls GET /invitations for a non-admin caller.
    expect(api.get).not.toHaveBeenCalledWith("/api/team/invitations");
  });

  it("a plain member sees neither Convidar nor Ações", async () => {
    user.current = { id: "u2", user_metadata: { org_role: "member" } };
    renderPage();
    await screen.findByText("Ana Owner");
    expect(screen.queryByTestId("equipe-convidar")).not.toBeInTheDocument();
    expect(screen.queryByText("Ações")).not.toBeInTheDocument();
  });
});

describe("Equipe — convidar", () => {
  it("submits the chosen role", async () => {
    renderPage();
    await screen.findByText("Ana Owner");
    fireEvent.click(screen.getByTestId("equipe-convidar"));
    const sheet = await screen.findByTestId("convidar-sheet");
    fireEvent.change(within(sheet).getByLabelText(/E-mail/), { target: { value: "novo@agencia.com" } });
    fireEvent.change(within(sheet).getByLabelText("Papel"), { target: { value: "manager" } });
    fireEvent.click(within(sheet).getByRole("button", { name: "Enviar convite" }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/team/invite", { email: "novo@agencia.com", role: "manager" }),
    );
  });

  it("offers every seed-accepted role except owner, in pt-BR", async () => {
    renderPage();
    await screen.findByText("Ana Owner");
    fireEvent.click(screen.getByTestId("equipe-convidar"));
    const sheet = await screen.findByTestId("convidar-sheet");
    const select = within(sheet).getByLabelText("Papel") as HTMLSelectElement;
    const rotulos = Array.from(select.options).map((o) => o.textContent);
    expect(rotulos).toEqual([
      "Administrador", "Gerente", "Membro", "Visualizador", "Desenvolvedor", "Teste", "Corretor",
    ]);
  });
});

describe("Equipe — remover membro", () => {
  it("confirms before removing, and cannot target the owner or oneself", async () => {
    renderPage();
    await screen.findByText("Ana Owner");
    // Owner row has no remove button at all (own row rule + owner rule).
    const linhaOwner = screen.getByText("Ana Owner").closest("tr")!;
    expect(within(linhaOwner).queryByRole("button", { name: /Remover/ })).not.toBeInTheDocument();

    const linhaBeto = screen.getByText("Beto Membro").closest("tr")!;
    fireEvent.click(within(linhaBeto).getByRole("button", { name: /Remover/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar remoção" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/team/u2"));
  });
});

describe("Equipe — convites pendentes", () => {
  it("shows a fetch error instead of a silent empty list", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/team") return { data: MEMBROS };
      if (path === "/api/team/invitations") throw new Error("Sem permissao");
      throw new Error(`GET inesperado ${path}`);
    });
    renderPage();
    await screen.findByText("Convites pendentes");
    expect(await screen.findByText("Sem permissao")).toBeInTheDocument();
  });

  it("cancels a pending invite", async () => {
    renderPage();
    await screen.findByText("novo@agencia.com");
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/team/invitations/c1"));
  });
});
