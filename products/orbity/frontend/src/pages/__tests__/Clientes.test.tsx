/**
 * Clientes -- "Excluir cliente": admin-only, asks the seed useConfirm dialog (never window.confirm), refetches the list
 * on success, and shows the server's 409 reason inline instead of a generic toast.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom";
import { ConfirmProvider } from "@noctusai/lib/components";

const { mockGet, mockDelete, toast, admin } = vi.hoisted(() => ({
  mockGet: vi.fn(), mockDelete: vi.fn(), toast: { success: vi.fn(), error: vi.fn() }, admin: { value: true },
}));
vi.mock("@/lib/api", () => ({ api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: mockDelete } }));
vi.mock("@noctusai/seed/infra", () => ({ api: {}, supabase: {}, useAuthStore: () => ({ user: null }), default: { api: {} } }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<typeof import("@noctusai/lib/design-system")>()),
  useIsOrgAdmin: () => admin.value,
}));

import Clientes from "../Clientes";

const ROW = {
  id: "c1", org_id: "o1", name: "Acme", legal_name: "Acme LTDA", document: null, email: null, phone: null,
  company: null, monthly_value: null, due_date: null, default_billing_type: null, billing_automation_enabled: false,
  active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ConfirmProvider><Clientes /></ConfirmProvider>
    </QueryClientProvider>,
  );
}

// The row action and the dialog's confirm button share a label: the dialog's is the one rendered last.
const confirmButton = async () => {
  await screen.findByRole("button", { name: /cancelar/i });
  return screen.getAllByRole("button", { name: "Excluir cliente" }).at(-1)!;
};

beforeEach(() => {
  vi.clearAllMocks();
  admin.value = true;
  mockGet.mockResolvedValue({ items: [ROW], total: 1, page: 1, page_size: 50 });
});

describe("Clientes -- excluir cliente", () => {
  it("is hidden from non-admins", async () => {
    admin.value = false;
    renderPage();
    await screen.findByText("Acme LTDA");
    expect(screen.queryByTitle("Excluir cliente")).toBeNull();
  });

  it("confirms, deletes and refetches the list", async () => {
    mockDelete.mockResolvedValue({ ok: true, id: "c1" });
    renderPage();
    await screen.findByText("Acme LTDA");
    const loads = mockGet.mock.calls.length;
    fireEvent.click(screen.getByTitle("Excluir cliente"));
    fireEvent.click(await confirmButton());
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/clients/c1"));
    await waitFor(() => expect(mockGet.mock.calls.length).toBeGreaterThan(loads));
    expect(toast.success).toHaveBeenCalledWith("Cliente excluído");
  });

  it("does nothing when the confirmation is dismissed", async () => {
    renderPage();
    await screen.findByText("Acme LTDA");
    fireEvent.click(screen.getByTitle("Excluir cliente"));
    fireEvent.click(await screen.findByRole("button", { name: /cancelar/i }));
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("shows the 409 reason inline", async () => {
    const reason = "Este cliente tem contrato ativo ou cobranças em aberto. Encerre o contrato antes de excluir.";
    mockDelete.mockRejectedValue(Object.assign(new Error("[409] x"), { status: 409, body: { detail: reason, code: "cliente_com_pendencias" } }));
    renderPage();
    await screen.findByText("Acme LTDA");
    fireEvent.click(screen.getByTitle("Excluir cliente"));
    fireEvent.click(await confirmButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(reason);
    expect(toast.success).not.toHaveBeenCalled();
  });
});
