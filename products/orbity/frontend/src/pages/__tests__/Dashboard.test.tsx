import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import "@testing-library/jest-dom";

const { mockKpis } = vi.hoisted(() => ({ mockKpis: vi.fn() }));

vi.mock("@noctusai/seed/infra", () => {
  const noop = () => {};
  const api = { get: noop, post: noop, patch: noop, delete: noop };
  return {
    api, supabase: {}, appConfig: {},
    useAuthStore: () => ({ user: null }),
    AuthProvider: ({ children }: { children?: unknown }) => children,
    NotificationBell: () => null,
    useNotificacoes: () => ({ data: [] }),
    useContagemNaoLidas: () => ({ data: 0 }),
    useMarcarComoLida: () => ({ mutate: noop }),
    useMarcarTodasComoLidas: () => ({ mutate: noop }),
    default: { api },
  };
});
vi.mock("@/hooks/useDashboard", () => ({ useDashboardKpis: () => mockKpis() }));

import Dashboard from "../Dashboard";

const ok = (data: unknown) => ({ data, isPending: false, isError: false, refetch: vi.fn() });
const pending = () => ({ data: undefined, isPending: true, isError: false, refetch: vi.fn() });
const failed = () => ({ data: undefined, isPending: false, isError: true, refetch: vi.fn() });

const base = () => ({
  month: "2026-06",
  clients: ok(7),
  funil: ok([{ stage: {}, leads: [{ value: 100, won_at: null }, { value: 50, won_at: null }] }]),
  tasks: ok({ items: [{ status: "todo", due_date: null }, { status: "doing", due_date: "2000-01-01" }] }),
  cashFlow: ok({ net: 1234.5 }),
  agenda: ok({ items: [] }),
});

const renderIt = () => render(<MemoryRouter><Dashboard /></MemoryRouter>);

describe("Dashboard KPIs", () => {
  it("shows real values and the Rotinas card", () => {
    mockKpis.mockReturnValue(base());
    renderIt();
    expect(screen.getByText("Clientes ativos")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText(/Pipeline:/)).toBeInTheDocument();
    expect(screen.getByText(/1 atrasadas/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Rotinas/ })).toHaveAttribute("href", "/rotinas");
  });
  it("a failing KPI shows an error hint + retry, never a fabricated 0", () => {
    mockKpis.mockReturnValue({ ...base(), clients: failed() });
    renderIt();
    expect(screen.getByText("Falha ao carregar")).toBeInTheDocument();
    expect(screen.getByText(/tentar novamente/i)).toBeInTheDocument();
  });
  it("loading KPI renders skeleton (no value)", () => {
    mockKpis.mockReturnValue({ ...base(), cashFlow: pending() });
    renderIt();
    expect(screen.queryByText(/1\.234/)).not.toBeInTheDocument();
  });
});
