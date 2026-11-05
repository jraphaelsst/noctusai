import React from "react";
import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const view = (over: object) => ({ data: undefined, showSkeleton: false, isRefreshing: false, isError: false, error: null, isPlaceholderData: false, refetch: vi.fn(), ...over });
const mockGrants = vi.fn();
const mockOpcoes = vi.fn();
const create = vi.fn();
const rotate = vi.fn();
const revoke = vi.fn();
const confirm = vi.fn();

vi.mock("@/hooks/useGrants", async (orig) => ({
  ...(await orig<typeof import("@/hooks/useGrants")>()),
  useGrants: () => mockGrants(),
  useGrantOpcoes: () => mockOpcoes(),
  useCreateGrant: () => ({ mutateAsync: create, isPending: false }),
  useRotateGrant: () => ({ mutateAsync: rotate, isPending: false }),
  useRevokeGrant: () => ({ mutateAsync: revoke, isPending: false }),
}));
vi.mock("@noctusai/lib/components", async (orig) => ({ ...(await orig<object>()), useConfirm: () => confirm }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ConexoesPlataforma from "../ConexoesPlataforma";
import { showPrefix } from "@/hooks/useGrants";

const grant = (over: object = {}) => ({
  id: "g1", org_id: "o1", org_nome: "One", agent_id: "a1", agent_key: "julia", product: "social-wiring", status: "ativo",
  channel_token_id: "c1", token_prefix: "noc_ab12", product_token_id: null, expires_at: null, created_at: null,
  revoked_at: null, last_delivered_at: "2026-11-01T10:00:00Z", last_error: null, ...over,
});

beforeEach(() => {
  mockGrants.mockReturnValue(view({ data: { items: [grant()], total: 1 } }));
  mockOpcoes.mockReturnValue(view({ data: { produtos: [{ slug: "social-wiring", label: "Social Wiring", agent_keys: ["julia"] }], orgs: [{ id: "o1", nome: "One", slug: "one" }] } }));
  create.mockResolvedValue(grant());
  confirm.mockResolvedValue(true);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("showPrefix", () => {
  it("shows the stored prefix plus an ellipsis, never a fake tail", () => {
    expect(showPrefix("noc_ab12")).toBe("noc_ab12…");
    expect(showPrefix(null)).toBe("—");
  });
});

describe("ConexoesPlataforma", () => {
  it("lists grants with status, credential prefix, delivery and error", () => {
    mockGrants.mockReturnValue(view({ data: { items: [grant(), grant({ id: "g2", status: "falhou", last_error: "delivery_failed:Timeout" })], total: 2 } }));
    const { container } = render(<ConexoesPlataforma />);
    const q = within(container);
    expect(q.getByText("Ativo")).toBeTruthy();
    expect(q.getByText("Falhou")).toBeTruthy();
    expect(q.getAllByText("noc_ab12…").length).toBe(2);
    expect(q.getByTestId("grant-error-g2").textContent).toContain("delivery_failed");
  });

  it("covers loading, empty, error and forbidden states", () => {
    mockGrants.mockReturnValue(view({ showSkeleton: true }));
    let r = render(<ConexoesPlataforma />);
    expect(within(r.container).getByTestId("grants-skeleton")).toBeTruthy();
    r.unmount();
    mockGrants.mockReturnValue(view({ data: { items: [], total: 0 } }));
    r = render(<ConexoesPlataforma />);
    expect(within(r.container).getByText(/Nenhuma conexão ainda/)).toBeTruthy();
    r.unmount();
    mockGrants.mockReturnValue(view({ isError: true, error: new Error("x") }));
    r = render(<ConexoesPlataforma />);
    expect(within(r.container).getByTestId("studio-error")).toBeTruthy();
    r.unmount();
    mockGrants.mockReturnValue(view({ isError: true, error: new ApiError(403, "platform_admin_required", "x") }));
    r = render(<ConexoesPlataforma />);
    expect(within(r.container).getByTestId("conexoes-forbidden")).toBeTruthy();
  });

  it("keeps the list mounted while refreshing", () => {
    mockGrants.mockReturnValue(view({ data: { items: [grant()], total: 1 }, isRefreshing: true }));
    const { container } = render(<ConexoesPlataforma />);
    expect(within(container).getByTestId("grants-list")).toBeTruthy();
  });

  it("creates in pick agent -> product -> org -> confirm, with no token field", async () => {
    const { baseElement } = render(<ConexoesPlataforma />);
    fireEvent.click(within(baseElement).getByTestId("grant-nova"));
    const q = within(baseElement);
    expect((q.getByTestId("grant-confirmar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(q.getByTestId("grant-agente"), { target: { value: "julia" } });
    fireEvent.change(q.getByTestId("grant-produto"), { target: { value: "social-wiring" } });
    fireEvent.change(q.getByTestId("grant-org"), { target: { value: "o1" } });
    expect(q.getByTestId("grant-resumo").textContent).toContain("Social Wiring");
    expect(baseElement.querySelector("input[type=password], textarea")).toBeNull();
    fireEvent.click(q.getByTestId("grant-confirmar"));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ agent_key: "julia", product: "social-wiring", org_id: "o1" }));
  });

  it("rotate and revoke ask for confirmation first", async () => {
    const { container } = render(<ConexoesPlataforma />);
    const q = within(container);
    confirm.mockResolvedValueOnce(false);
    fireEvent.click(q.getByTestId("grant-rotate-g1"));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(rotate).not.toHaveBeenCalled();
    fireEvent.click(q.getByTestId("grant-revoke-g1"));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("g1"));
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("a revoked grant offers no actions", () => {
    mockGrants.mockReturnValue(view({ data: { items: [grant({ status: "revogado" })], total: 1 } }));
    const { container } = render(<ConexoesPlataforma />);
    expect(within(container).queryByTestId("grant-revoke-g1")).toBeNull();
  });
});
