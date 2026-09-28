/**
 * Role routing — ninho-vazio CONTRACT.md §Frontend: "a `membro` must never
 * see staff nav or pages"; any staff path redirects to `/portal`; staff keep
 * the current nav. The role comes from `GET /api/eu`.
 */
import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));

vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api,
    supabase: { auth: { signOut: vi.fn() } },
    appConfig: {},
    useAuthStore: () => ({ user: null }),
    NotificationBell: () => null,
    default: { api, appConfig: {}, NotificationBell: () => null },
  };
});

vi.mock("@noctusai/seed", () => ({
  createProductLayout: vi.fn(() => ({ children }: { children: React.ReactNode }) => <div>{children}</div>),
}));

import { createRoleLayout, isMemberPath } from "@/layouts/RoleLayout";
import { MEMBER_NAV_GROUPS, MEMBER_NAV_FALLBACK } from "@/layouts/MemberLayout";

function StaffLayout({ children }: { children: React.ReactNode }) {
  return (
    <div data-testid="staff-layout">
      <nav>
        <a href="/membros">Membros</a>
        <a href="/financeiro">Financeiro</a>
      </nav>
      {children}
    </div>
  );
}
function MembroLayout({ children }: { children: React.ReactNode }) {
  return <div data-testid="membro-layout">{children}</div>;
}
const RoleLayout = createRoleLayout({ Staff: StaffLayout, Membro: MembroLayout });

function Where() {
  const { pathname } = useLocation();
  return <span data-testid="path">{pathname}</span>;
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <RoleLayout>
          <Routes>
            <Route path="/" element={<p>Dashboard da equipe</p>} />
            <Route path="/membros" element={<p>Página Membros (equipe)</p>} />
            <Route path="/portal" element={<p>Minha conta</p>} />
            <Route path="*" element={<p>outra</p>} />
          </Routes>
        </RoleLayout>
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const EU_MEMBRO = {
  papel: "membro",
  nome: "Ana",
  email: "ana@x.com",
  membro: { id: "m1", status: "ativo", plano_id: null, plano_nome: "Gratuito", nivel_grupoterapia: "nenhum" },
};
const EU_ADMIN = { papel: "admin", nome: "Mônica", email: "m@x.com", membro: null };

beforeEach(() => vi.clearAllMocks());

describe("RoleLayout — membro", () => {
  it("redirects a staff path to /portal and never renders the staff layout, nav or page", async () => {
    mockGet.mockResolvedValue(EU_MEMBRO);
    renderAt("/membros");
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/portal"));
    expect(screen.getByTestId("membro-layout")).toBeInTheDocument();
    expect(screen.getByText("Minha conta")).toBeInTheDocument();
    expect(screen.queryByTestId("staff-layout")).not.toBeInTheDocument();
    expect(screen.queryByText("Página Membros (equipe)")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Financeiro" })).not.toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/eu");
  });

  it("redirects the staff root `/` to /portal too", async () => {
    mockGet.mockResolvedValue(EU_MEMBRO);
    renderAt("/");
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent("/portal"));
    expect(screen.queryByText("Dashboard da equipe")).not.toBeInTheDocument();
  });

  it("member nav only links into the portal", () => {
    const hrefs = [...MEMBER_NAV_GROUPS, ...MEMBER_NAV_FALLBACK].flatMap((g) => g.items.map((i) => i.href));
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of hrefs) expect(isMemberPath(href)).toBe(true);
    const routes = MEMBER_NAV_GROUPS.flatMap((g) => g.items.map((i) => i.route));
    expect(routes).toEqual(["portal", "portal-grupoterapia"]);
  });
});

describe("RoleLayout — staff", () => {
  it("renders the staff layout unchanged on a staff path", async () => {
    mockGet.mockResolvedValue(EU_ADMIN);
    renderAt("/membros");
    expect(await screen.findByTestId("staff-layout")).toBeInTheDocument();
    expect(screen.getByText("Página Membros (equipe)")).toBeInTheDocument();
    expect(screen.queryByTestId("membro-layout")).not.toBeInTheDocument();
  });

  it("sends staff away from the member portal", async () => {
    mockGet.mockResolvedValue(EU_ADMIN);
    renderAt("/portal");
    await waitFor(() => expect(screen.getByTestId("path")).toHaveTextContent(/^\/$/));
    expect(screen.getByText("Dashboard da equipe")).toBeInTheDocument();
  });
});

describe("RoleLayout — fail closed", () => {
  it("renders neither layout when /api/eu fails", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(500, "Erro interno."));
    renderAt("/membros");
    expect(await screen.findByText("Não conseguimos carregar sua conta.")).toBeInTheDocument();
    expect(screen.getByText("Erro interno.")).toBeInTheDocument();
    expect(screen.queryByTestId("staff-layout")).not.toBeInTheDocument();
    expect(screen.queryByTestId("membro-layout")).not.toBeInTheDocument();
  });
});
