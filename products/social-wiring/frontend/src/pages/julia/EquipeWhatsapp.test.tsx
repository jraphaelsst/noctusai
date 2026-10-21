/** Julia › Equipe do WhatsApp — every state (skeleton / empty / error / list), add / edit / deactivate / remove through design-system
 *  dialogs (never browser dialogs), typed server refusals inline, and the org-admin gate. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import JuliaEquipeWhatsapp from "./EquipeWhatsapp";

const M = (over: Record<string, unknown> = {}) => ({
  id: "m1", user_id: null, nome: "Bia Souza", papel: "corretor", telefone: "5511977770009", ativo: true, ...over,
});
const PAPEIS = ["admin", "operador", "corretor", "atendente", "outro"];

function setup({ items = [M()] as unknown[] | Error }: { items?: unknown[] | Error } = {}) {
  api.get.mockImplementation((u: string) => {
    if (u.endsWith("/usuarios")) return Promise.resolve({ data: [{ id: "u1", nome: "Adriana", org_role: "admin" }] });
    return items instanceof Error ? Promise.reject(items) : Promise.resolve({ data: { items, papeis: PAPEIS, operadores: ["admin", "operador"] } });
  });
  api.post.mockResolvedValue({ data: {} });
  api.patch.mockResolvedValue({ data: {} });
  api.delete.mockResolvedValue(undefined);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><JuliaEquipeWhatsapp /></QueryClientProvider>);
}
beforeEach(() => { vi.clearAllMocks(); h.admin = true; });
afterEach(cleanup);

describe("lista", () => {
  it("shows a skeleton then name, role label, formatted phone and what the role means", async () => {
    setup();
    expect(screen.getByTestId("equipe-skeleton")).toBeTruthy();
    const item = await screen.findByTestId("equipe-item");
    expect(item.textContent).toContain("Bia Souza");
    expect(screen.getByTestId("equipe-papel").textContent).toBe("Corretor");
    expect(item.textContent).toContain("+55 11 97777-0009");
    expect(item.textContent).toContain("nunca é tratado como lead");
  });

  it("says that an empty list means everyone is a lead", async () => {
    setup({ items: [] });
    expect((await screen.findByTestId("equipe-vazia")).textContent).toContain("tratados como leads");
  });

  it("shows the error with a retry, never an empty list", async () => {
    setup({ items: new Error("boom") });
    expect(await screen.findByTestId("equipe-erro")).toBeTruthy();
    expect(screen.queryByTestId("equipe-vazia")).toBeNull();
  });

  it("marks an inactive member", async () => {
    setup({ items: [M({ ativo: false })] });
    expect(await screen.findByTestId("equipe-inativo")).toBeTruthy();
  });

  it("a non-admin sees the notice and triggers no request", async () => {
    h.admin = false;
    setup();
    expect(screen.getByTestId("equipe-sem-permissao")).toBeTruthy();
    expect(screen.queryByTestId("equipe-adicionar")).toBeNull();
    await new Promise((r) => setTimeout(r, 20));
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe("adicionar / editar", () => {
  it("posts the new member with a normalised body and closes on success", async () => {
    setup({ items: [] });
    fireEvent.click(await screen.findByTestId("equipe-adicionar"));
    fireEvent.change(screen.getByTestId("membro-nome"), { target: { value: "  Carlos " } });
    fireEvent.change(screen.getByTestId("membro-papel"), { target: { value: "operador" } });
    expect(screen.getByTestId("membro-papel-explicacao").textContent).toContain("One Chat");
    fireEvent.change(screen.getByTestId("membro-telefone"), { target: { value: "+55 11 98888-0000" } });
    fireEvent.click(screen.getByTestId("membro-salvar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/equipe-whatsapp", {
      nome: "Carlos", papel: "operador", telefone: "+55 11 98888-0000", user_id: null,
    }));
    await waitFor(() => expect(screen.queryByTestId("membro-dialog")).toBeNull());
    expect(toast.success).toHaveBeenCalled();
  });

  it("cannot save without a name and a way to identify (a number or a user)", async () => {
    setup({ items: [] });
    fireEvent.click(await screen.findByTestId("equipe-adicionar"));
    const salvar = screen.getByTestId("membro-salvar") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("membro-nome"), { target: { value: "Ana" } });
    expect(salvar.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("membro-usuario"), { target: { value: "u1" } });
    expect(salvar.disabled).toBe(false);
  });

  it("keeps the modal open and shows the typed server refusal inline", async () => {
    setup({ items: [] });
    api.post.mockRejectedValue({ message: "409", body: { error: { message: "Este WhatsApp já está na equipe." } } });
    fireEvent.click(await screen.findByTestId("equipe-adicionar"));
    fireEvent.change(screen.getByTestId("membro-nome"), { target: { value: "Ana" } });
    fireEvent.change(screen.getByTestId("membro-telefone"), { target: { value: "5511977770009" } });
    fireEvent.click(screen.getByTestId("membro-salvar"));
    expect((await screen.findByTestId("membro-erro")).textContent).toContain("já está na equipe");
    expect(screen.getByTestId("membro-dialog")).toBeTruthy();
  });

  it("edits through PATCH with the member id", async () => {
    setup();
    fireEvent.click(await screen.findByTestId("equipe-editar"));
    fireEvent.change(screen.getByTestId("membro-papel"), { target: { value: "atendente" } });
    fireEvent.click(screen.getByTestId("membro-salvar"));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    expect(api.patch.mock.calls[0][0]).toBe("/api/julia/equipe-whatsapp/m1");
    expect(api.patch.mock.calls[0][1]).toMatchObject({ papel: "atendente", nome: "Bia Souza" });
  });
});

describe("desativar / remover", () => {
  it("deactivates with one click and says the next message is a lead", async () => {
    setup();
    fireEvent.click(await screen.findByTestId("equipe-alternar"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/equipe-whatsapp/m1", { ativo: false }));
    await waitFor(() => expect(toast.success.mock.calls[0][0]).toContain("tratado como lead"));
  });

  it("asks in a design-system dialog before removing, and deletes only after the confirmation", async () => {
    const confirmar = vi.spyOn(window, "confirm");
    setup();
    fireEvent.click(await screen.findByTestId("equipe-remover"));
    expect(screen.getByTestId("equipe-remover-dialog").textContent).toContain("Bia Souza");
    expect(api.delete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("equipe-remover-confirmar"));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/julia/equipe-whatsapp/m1"));
    expect(confirmar).not.toHaveBeenCalled();
  });

  it("shows the refusal (the last operator of a Julia line) inside the dialog", async () => {
    setup();
    api.delete.mockRejectedValue({ message: "409", body: { error: { message: "A Julia precisa de ao menos um operador." } } });
    fireEvent.click(await screen.findByTestId("equipe-remover"));
    fireEvent.click(screen.getByTestId("equipe-remover-confirmar"));
    expect((await screen.findByTestId("equipe-remover-erro")).textContent).toContain("ao menos um operador");
  });
});
