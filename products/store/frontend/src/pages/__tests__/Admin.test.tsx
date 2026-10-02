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

const KEYS = [
  { key: "asaas_api_key", label: "Chave de API do Asaas", description: "d", is_secret: true, testable: false, input_type: "password", placeholder: "$aact_", configured: true, options: [], default: null, hint: "...b3f9", source: "local", updated_at: null },
  { key: "asaas_environment", label: "Ambiente do Asaas", description: "d", is_secret: false, testable: false, input_type: "text", placeholder: "", configured: false, options: [{ value: "sandbox", label: "Sandbox", description: "" }, { value: "production", label: "Produção", description: "" }], default: "sandbox", hint: null, source: null, updated_at: null },
];

function route(settings: unknown) {
  apiMock.get.mockImplementation((url: string) => {
    if (url === "/api/admin/settings") return settings instanceof Error ? Promise.reject(settings) : Promise.resolve(settings);
    if (url === "/api/admin/produto/arquivo") return Promise.resolve({ exists: true, size: 2097152, updated_at: "2026-10-01T10:00:00Z" });
    if (url === "/api/settings/api-keys") return Promise.resolve({ total: 3, items: KEYS });
    return Promise.reject(new Error(url));
  });
}
beforeEach(() => vi.clearAllMocks());

describe("Admin (Página de vendas)", () => {
  it("403 renders 'Sem acesso' and never the form", async () => {
    route(new ApiError(403, "forbidden"));
    renderWithProviders(<Admin />);
    expect(await screen.findByText("Sem acesso")).toBeInTheDocument();
    expect(screen.queryByText("Salvar página")).toBeNull();
    expect(screen.queryByLabelText("Preço")).toBeNull();
  });

  it("shows live total, saves with expected_version and the BRL-masked price in cents", async () => {
    route({ version: 3, data: DATA });
    apiMock.put.mockResolvedValue({ version: 4 });
    renderWithProviders(<Admin />);
    expect(await screen.findByText(/Total: R\$ 144,00/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar página" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Preço"), { target: { value: "5990" } });
    expect(screen.getByLabelText("Preço")).toHaveValue("59,90");
    fireEvent.click(screen.getByRole("button", { name: "Salvar página" }));
    await waitFor(() => expect(apiMock.put).toHaveBeenCalled());
    const [url, body] = apiMock.put.mock.calls[0];
    expect(url).toBe("/api/admin/settings");
    expect(body.expected_version).toBe(3);
    expect(body.data.price_cents).toBe(5990);
  });

  it("shows Integrações: masked hint + source, never a secret, env selector, webhook URL", async () => {
    route({ version: 1, data: DATA });
    renderWithProviders(<Admin />);
    expect(await screen.findByText("Chave de API do Asaas")).toBeInTheDocument();
    expect(screen.getByTestId("api-key-hint-asaas_api_key")).toHaveTextContent("...b3f9");
    expect(screen.getByTestId("api-key-configured-asaas_api_key")).toHaveTextContent("Definida aqui");
    expect(screen.getByLabelText("Chave de API do Asaas")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Chave de API do Asaas")).toHaveValue("");
    expect(screen.getByLabelText("Ambiente do Asaas").tagName).toBe("SELECT");
    expect(screen.getByTestId("webhook-url")).toHaveTextContent(`${window.location.origin}/api/webhooks/asaas`);
    expect(screen.getByRole("button", { name: "Remover Chave de API do Asaas" })).toBeInTheDocument();
  });

  it("saves a key through PUT /api/settings/api-keys/{key} with {value}", async () => {
    route({ version: 1, data: DATA });
    apiMock.put.mockResolvedValue({ ...KEYS[0] });
    renderWithProviders(<Admin />);
    const input = await screen.findByLabelText("Chave de API do Asaas");
    fireEvent.change(input, { target: { value: "$aact_novo" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(apiMock.put).toHaveBeenCalledWith("/api/settings/api-keys/asaas_api_key", { value: "$aact_novo" }));
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
    fireEvent.click(screen.getByRole("button", { name: "Salvar página" }));
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
