/**
 * Equipe is the canonical seed TeamPage organ (the page is a one-component
 * wrapper). This pins the wiring: roster read from /api/team with pt-BR role
 * labels, and the honest "removal is a Core action" note for managers.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api, user } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  user: { current: { id: "u1", user_metadata: { org_role: "admin" } as Record<string, unknown> } },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: (sel: (s: { user: unknown }) => unknown) => sel({ user: user.current }) }));

import Equipe from "../Equipe";

const MEMBROS = [
  { id: "u1", nome: "Ana Owner", email: "ana@agencia.com", role: "owner", org_role: "owner", created_at: "2026-01-10T10:00:00Z" },
  { id: "u2", nome: "Beto Membro", email: "beto@agencia.com", role: "member", org_role: "member", created_at: "2026-02-01T10:00:00Z" },
];

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
    if (path === "/api/team/invitations") return { data: [] };
    if (path === "/api/team/policy") return { staff_roles: [], invitable_roles: ["member"], labels: {} };
    throw new Error(`GET inesperado ${path}`);
  });
});
afterEach(cleanup);

describe("Equipe (TeamPage organ)", () => {
  it("lists the roster with pt-BR role labels", async () => {
    renderPage();
    expect(await screen.findByText("Ana Owner")).toBeInTheDocument();
    expect(screen.getByText("Você")).toBeInTheDocument();
    expect(screen.getByText("Proprietário")).toBeInTheDocument();
    expect(screen.getByText("Membro")).toBeInTheDocument();
  });

  it("points managers to NoctusAI Core for removal (no Remover action)", async () => {
    renderPage();
    expect(await screen.findByTestId("team-remove-core-note")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remover/i })).toBeNull();
  });
});
