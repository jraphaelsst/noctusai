import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiError } from "@noctusai/lib";
import { apiMock, PUBLIC_SETTINGS, renderWithProviders } from "@/test-utils";

vi.mock("@noctusai/seed/infra", () => ({ api: apiMock }));

import Landing from "../Landing";

const assign = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
});

const openDialog = () => fireEvent.click(screen.getAllByRole("button", { name: /Quero meu contrato/ })[0]);
const fill = (cpf: string) => {
  fireEvent.change(screen.getByLabelText(/Nome completo/), { target: { value: "Maria Silva" } });
  fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "maria@exemplo.com" } });
  fireEvent.change(screen.getByLabelText(/CPF/), { target: { value: cpf } });
};

describe("Landing", () => {
  it("renders dynamic price, recap, derived total, guarantee and author from settings", async () => {
    apiMock.get.mockResolvedValue(PUBLIC_SETTINGS);
    renderWithProviders(<Landing />);
    await waitFor(() => expect(screen.getByText("Contrato À Vista (Word + PDF)")).toBeInTheDocument());
    expect(apiMock.get).toHaveBeenCalledWith("/api/public/settings");
    expect(screen.getAllByText("R$ 47").length).toBeGreaterThan(0);
    expect(screen.getAllByText("R$ 144").length).toBeGreaterThan(0);
    expect(screen.getByText("Garantia de 7 dias")).toBeInTheDocument();
    expect(screen.getByText(/Gilson,/)).toBeInTheDocument();
    expect(screen.getByText(/Foto de Gilson/)).toBeInTheDocument(); // dashed placeholder (photo_url null)
  });

  it("skeletons only the dynamic spans while pending; the static page renders at once", () => {
    apiMock.get.mockReturnValue(new Promise(() => undefined));
    const { container } = renderWithProviders(<Landing />);
    expect(screen.getByText(/Um contrato mal feito pode custar/)).toBeInTheDocument();
    expect(container.querySelectorAll(".sk").length).toBeGreaterThan(0);
    expect(screen.queryByText("R$ 47")).toBeNull();
  });

  it("on error keeps the page, hides prices and disables the CTA", { timeout: 8000 }, async () => {
    apiMock.get.mockRejectedValue(new ApiError(500, "boom"));
    renderWithProviders(<Landing />);
    // the settings query retries once (1 s back-off) before surfacing the error
    await waitFor(() => expect(screen.getAllByText("Indisponível no momento").length).toBeGreaterThan(0), { timeout: 4000 });
    expect(screen.getByText(/Um contrato mal feito pode custar/)).toBeInTheDocument();
    expect(screen.queryByText(/R\$ 47/)).toBeNull();
    expect(screen.getAllByText("Indisponível no momento")[0].closest("button")).toBeDisabled();
  });

  it("has no login link anywhere", async () => {
    apiMock.get.mockResolvedValue(PUBLIC_SETTINGS);
    const { container } = renderWithProviders(<Landing />);
    await waitFor(() => screen.getByText("Contrato À Vista (Word + PDF)"));
    expect(container.querySelector('a[href*="login"]')).toBeNull();
    expect(screen.queryByText(/^Entrar$/)).toBeNull();
  });

  it("checkout: blocks an invalid CPF client-side, then posts digits and redirects", async () => {
    apiMock.get.mockResolvedValue(PUBLIC_SETTINGS);
    apiMock.post.mockResolvedValue({ checkout_url: "https://pay.example/inv", pedido_token: "tok" });
    renderWithProviders(<Landing />);
    await waitFor(() => screen.getByText("Contrato À Vista (Word + PDF)"));
    openDialog();

    fill("11111111111");
    fireEvent.click(screen.getByRole("button", { name: "Ir para o pagamento" }));
    expect(await screen.findByText(/CPF inválido/)).toBeInTheDocument();
    expect(apiMock.post).not.toHaveBeenCalled();

    fill("52998224725");
    expect(screen.getByLabelText(/CPF/)).toHaveValue("529.982.247-25");
    fireEvent.click(screen.getByRole("button", { name: "Ir para o pagamento" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://pay.example/inv"));
    expect(apiMock.post).toHaveBeenCalledWith("/api/public/checkout", {
      nome: "Maria Silva", email: "maria@exemplo.com", cpf: "52998224725",
    });
  });

  it.each([
    [409, /Vendas pausadas/],
    [503, /Pagamento indisponível/],
  ])("checkout %i shows its message", async (status, re) => {
    apiMock.get.mockResolvedValue(PUBLIC_SETTINGS);
    apiMock.post.mockRejectedValue(new ApiError(status, "x"));
    renderWithProviders(<Landing />);
    await waitFor(() => screen.getByText("Contrato À Vista (Word + PDF)"));
    openDialog();
    fill("52998224725");
    fireEvent.click(screen.getByRole("button", { name: "Ir para o pagamento" }));
    expect(await screen.findByText(re)).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("checkout 422 maps server field errors onto the fields", async () => {
    apiMock.get.mockResolvedValue(PUBLIC_SETTINGS);
    apiMock.post.mockRejectedValue(new ApiError(422, "x", { detail: [{ loc: ["body", "email"], msg: "e-mail recusado" }] }));
    renderWithProviders(<Landing />);
    await waitFor(() => screen.getByText("Contrato À Vista (Word + PDF)"));
    openDialog();
    fill("52998224725");
    fireEvent.click(screen.getByRole("button", { name: "Ir para o pagamento" }));
    expect(await screen.findByText("e-mail recusado")).toBeInTheDocument();
  });
});

describe("Landing checkout — flat error shape (contract A6)", () => {
  it("422 {code, field, detail} lands on the named field", async () => {
    apiMock.get.mockResolvedValue(PUBLIC_SETTINGS);
    apiMock.post.mockRejectedValue(new ApiError(422, "x", { detail: "CPF inválido", code: "invalid", field: "cpf" }));
    renderWithProviders(<Landing />);
    await waitFor(() => screen.getByText("Contrato À Vista (Word + PDF)"));
    openDialog();
    fill("52998224725");
    fireEvent.click(screen.getByRole("button", { name: "Ir para o pagamento" }));
    expect(await screen.findByText("CPF inválido")).toBeInTheDocument();
  });
});
