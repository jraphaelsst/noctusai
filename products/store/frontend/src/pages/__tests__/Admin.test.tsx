import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";
import { apiMock, renderWithProviders } from "@/test-utils";

vi.mock("@noctusai/seed/infra", () => ({ api: apiMock }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import Admin, { validateSettings } from "../Admin";

const DATA = {
  product_name: "Contrato Blindado", price_cents: 4700,
  items: [{ label: "Item A", anchor_cents: 9700 }, { label: "Item B", anchor_cents: 4700 }],
  guarantee_days: 7, author: { name: "Gilson", role: "corretor", bio: "bio", has_photo: false },
  checkout_enabled: true,
};

function route(settings: unknown) {
  apiMock.get.mockImplementation((url: string) => {
    if (url === "/api/admin/settings") return settings instanceof Error ? Promise.reject(settings) : Promise.resolve(settings);
    if (url === "/api/admin/produto/arquivo") return Promise.resolve({ exists: true, size: 2097152, updated_at: "2026-10-01T10:00:00Z" });
    return Promise.reject(new Error(url));
  });
}
beforeEach(() => vi.clearAllMocks());

describe("Admin (Página de vendas)", () => {
  it("403 renders 'Sem acesso' and never the form", async () => {
    route(new ApiError(403, "forbidden"));
    renderWithProviders(<Admin />);
    expect(await screen.findByText("Sem acesso")).toBeInTheDocument();
    expect(screen.queryByText("Salvar")).toBeNull();
    expect(screen.queryByLabelText("Preço")).toBeNull();
  });

  it("shows live total, saves with expected_version and the BRL-masked price in cents", async () => {
    route({ version: 3, data: DATA });
    apiMock.put.mockResolvedValue({ version: 4 });
    renderWithProviders(<Admin />);
    expect(await screen.findByText(/Total: R\$ 144,00/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Preço"), { target: { value: "5990" } });
    expect(screen.getByLabelText("Preço")).toHaveValue("59,90");
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(apiMock.put).toHaveBeenCalled());
    const [url, body] = apiMock.put.mock.calls[0];
    expect(url).toBe("/api/admin/settings");
    expect(body.expected_version).toBe(3);
    expect(body.data.price_cents).toBe(5990);
  });

  it("reorders and removes items", async () => {
    route({ version: 1, data: DATA });
    renderWithProviders(<Admin />);
    await screen.findByLabelText("Item 1");
    fireEvent.click(screen.getAllByRole("button", { name: "Descer" })[0]);
    expect(screen.getByLabelText("Item 1")).toHaveValue("Item B");
    fireEvent.click(screen.getAllByRole("button", { name: "Remover" })[0]);
    expect(screen.queryByLabelText("Item 2")).toBeNull();
  });

  it("409 shows the 'alguém salvou antes' prompt", async () => {
    route({ version: 3, data: DATA });
    apiMock.put.mockRejectedValue(new ApiError(409, "stale"));
    renderWithProviders(<Admin />);
    await screen.findByLabelText("Preço");
    fireEvent.change(screen.getByLabelText("Preço"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText(/Alguém salvou antes de você/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recarregar" })).toBeInTheDocument();
  });

  it("validateSettings mirrors the contract limits", () => {
    expect(validateSettings(DATA)).toEqual([]);
    expect(validateSettings({ ...DATA, price_cents: 50 }).length).toBe(1);
    expect(validateSettings({ ...DATA, guarantee_days: 31 }).length).toBe(1);
    expect(validateSettings({ ...DATA, author: { ...DATA.author, bio: "x".repeat(601) } }).length).toBe(1);
    expect(validateSettings({ ...DATA, items: [] }).length).toBe(1);
  });
});
