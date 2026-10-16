/** ClientForm -- Razão Social required, nome fantasia optional, CNPJ lookup prefill that never overwrites silently. */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom";

const { mockGet, mockPost, mockPatch } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn(), mockPatch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: mockPost, patch: mockPatch } }));
vi.mock("@noctusai/seed/infra", () => ({ api: {}, useAuthStore: () => ({ user: null }), default: { api: {} } }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ClientForm, EMPTY_CLIENT, valuesOf } from "../ClientForm";

function renderForm(initial = EMPTY_CLIENT, onSaved = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ClientForm open initial={initial} onClose={vi.fn()} onSaved={onSaved} />
    </QueryClientProvider>,
  );
  return onSaved;
}

beforeEach(() => vi.clearAllMocks());

describe("ClientForm", () => {
  it("cannot save without the Razão Social", () => {
    renderForm();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
    expect(screen.getByText(/Informe a Razão Social/)).toBeInTheDocument();
  });

  it("saves with only the Razão Social -- the nome fantasia is optional and omitted", async () => {
    mockPost.mockResolvedValue({});
    const onSaved = renderForm();
    fireEvent.change(screen.getByPlaceholderText("Empresa Exemplo Comércio Ltda"), { target: { value: "Acme Comércio LTDA" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mockPost).toHaveBeenCalledWith("/api/clients", { legal_name: "Acme Comércio LTDA", billing_automation_enabled: false });
  });

  it("'Buscar CNPJ' is only offered for a 14-digit document", () => {
    renderForm();
    const input = screen.getByPlaceholderText("00.000.000/0000-00");
    expect(screen.getByRole("button", { name: "Buscar CNPJ" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "11.222.333/0001-81" } });
    expect(screen.getByRole("button", { name: "Buscar CNPJ" })).toBeEnabled();
  });

  it("prefills an EMPTY Razão Social from the registry", async () => {
    mockGet.mockResolvedValue({ cnpj: "11222333000181", legal_name: "ACME COMERCIO LTDA", situacao_cadastral: "ativa" });
    renderForm();
    fireEvent.change(screen.getByPlaceholderText("00.000.000/0000-00"), { target: { value: "11.222.333/0001-81" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CNPJ" }));
    await waitFor(() => expect(screen.getByPlaceholderText("Empresa Exemplo Comércio Ltda")).toHaveValue("ACME COMERCIO LTDA"));
    expect(mockGet).toHaveBeenCalledWith("/api/clients/cnpj/11222333000181");
  });

  it("never overwrites a typed Razão Social silently -- it offers the registry's name", async () => {
    mockGet.mockResolvedValue({ cnpj: "11222333000181", legal_name: "ACME COMERCIO LTDA", situacao_cadastral: "ativa" });
    renderForm({ ...EMPTY_CLIENT, legal_name: "Acme (digitado)", document: "11.222.333/0001-81" });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CNPJ" }));
    await screen.findByText("ACME COMERCIO LTDA");
    expect(screen.getByPlaceholderText("Empresa Exemplo Comércio Ltda")).toHaveValue("Acme (digitado)");
    fireEvent.click(screen.getByRole("button", { name: "Usar como Razão Social" }));
    expect(screen.getByPlaceholderText("Empresa Exemplo Comércio Ltda")).toHaveValue("ACME COMERCIO LTDA");
  });

  it("a failed lookup is reported and the form stays usable (type it manually)", async () => {
    mockGet.mockRejectedValue(new Error("Não foi possível consultar o CNPJ agora. Preencha a Razão Social manualmente."));
    renderForm({ ...EMPTY_CLIENT, document: "11222333000181" });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CNPJ" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("manualmente");
    expect(screen.getByPlaceholderText("Empresa Exemplo Comércio Ltda")).toBeEnabled();
  });

  it("editing patches the client; a nome fantasia equal to the legal name is shown empty", async () => {
    mockPatch.mockResolvedValue({});
    const values = valuesOf({ id: "c1", legal_name: "Acme LTDA", name: "Acme LTDA", document: null, email: null, phone: null, monthly_value: null, due_date: null, default_billing_type: null, billing_automation_enabled: false });
    expect(values.name).toBe("");
    const onSaved = renderForm(values);
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(mockPatch).toHaveBeenCalledWith("/api/clients/c1", { legal_name: "Acme LTDA", billing_automation_enabled: false });
  });
});
