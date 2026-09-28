/**
 * Portal minha conta — CONTRACT.md §Member portal: grace banner when
 * `estado === "carencia"` (carencia_ate + invoice link), upgrade cards →
 * the in-portal plan change dialog (`POST /api/portal/assinatura`, also
 * opened by `/portal?trocar=<id>`), cancel with confirmation explaining
 * `pago_ate`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("@/lib/api", () => ({
  api: { get: mockGet, post: mockPost, put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import MinhaConta from "@/pages/portal/MinhaConta";
import { renderPortal } from "./_harness";

const CONTA = {
  membro: { id: "m1", nome: "Ana Souza", email: "ana@x.com", telefone: null, status: "atrasado", entrou_em: "2026-01-10" },
  plano: { id: "p-ouvinte", nome: "Ouvinte", preco_centavos: 700, ciclo: "mensal", nivel_grupoterapia: "ouvir" },
  assinatura: {
    id: "a1",
    estado: "carencia",
    metodo: "pix",
    proxima_cobranca: "2026-10-01",
    pago_ate: "2026-10-01",
    carencia_ate: "2026-10-06",
    cancelada_em: null,
    gateway: "asaas",
  },
  pagamentos: [
    { id: "pg1", valor_centavos: 700, estado: "pago", metodo: "pix", vencimento: "2026-09-01", pago_em: "2026-09-01", url_fatura: "https://asaas/f/old" },
    { id: "pg2", valor_centavos: 700, estado: "pendente", metodo: "pix", vencimento: "2026-10-01", pago_em: null, url_fatura: "https://asaas/f/aberta" },
  ],
  planos_disponiveis: [
    { id: "p-gratis", nome: "Gratuito", descricao: null, preco_centavos: 0, ciclo: "mensal", nivel_grupoterapia: "nenhum" },
    { id: "p-ouvinte", nome: "Ouvinte", descricao: null, preco_centavos: 700, ciclo: "mensal", nivel_grupoterapia: "ouvir" },
    { id: "p-premium", nome: "Premium", descricao: null, preco_centavos: 2700, ciclo: "mensal", nivel_grupoterapia: "falar" },
  ],
};

beforeEach(() => vi.clearAllMocks());

describe("MinhaConta", () => {
  it("shows the grace banner with carencia_ate and the open invoice link", async () => {
    mockGet.mockResolvedValue(CONTA);
    renderPortal(<MinhaConta />);
    const banner = await screen.findByTestId("banner-carencia");
    expect(banner).toHaveTextContent("06/10/2026");
    expect(screen.getByRole("link", { name: /Abrir a fatura/ })).toHaveAttribute("href", "https://asaas/f/aberta");
    expect(mockGet).toHaveBeenCalledWith("/api/portal/minha-conta");
  });

  it("no grace banner when the subscription is active; shows next charge", async () => {
    mockGet.mockResolvedValue({ ...CONTA, assinatura: { ...CONTA.assinatura, estado: "ativa", carencia_ate: null } });
    renderPortal(<MinhaConta />);
    expect(await screen.findByTestId("proxima-cobranca")).toHaveTextContent("01/10/2026");
    expect(screen.queryByTestId("banner-carencia")).not.toBeInTheDocument();
  });

  it("offers only higher tiers as upgrades, each opening the plan change dialog", async () => {
    mockGet.mockResolvedValue(CONTA);
    renderPortal(<MinhaConta />);
    expect(await screen.findByRole("button", { name: "Quero o Premium" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Quero o Gratuito" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Quero o Ouvinte" })).not.toBeInTheDocument();
    // never the anonymous checkout
    expect(document.querySelector('a[href^="/assinar"]')).toBeNull();
  });

  it("upgrade by Pix: sends only plan/method/CPF and shows the QR inline", async () => {
    mockGet.mockResolvedValue(CONTA);
    mockPost.mockResolvedValue({
      checkout_url: "https://asaas/f/nova",
      assinatura_id: "a2",
      membro_id: "m1",
      pix_qr: { payload: "00020126pix-copia-e-cola", imagem_base64: "iVBOR", expira_em: null },
      status: null,
    });
    renderPortal(<MinhaConta />);
    fireEvent.click(await screen.findByRole("button", { name: "Quero o Premium" }));
    expect(screen.getByRole("dialog", { name: "Mudar para o Premium" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Gerar cobrança" }));
    expect(await screen.findByText("Informe o CPF (11 dígitos) ou o CNPJ (14 dígitos).")).toBeInTheDocument();
    expect(mockPost).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: "123.456.789-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Gerar cobrança" }));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/portal/assinatura", {
        plano_id: "p-premium",
        metodo: "pix",
        cpf_cnpj: "12345678901",
      }),
    );
    expect(await screen.findByTestId("pix-qr-card")).toHaveTextContent("00020126pix-copia-e-cola");
    expect(screen.getByTestId("troca-fatura")).toHaveAttribute("href", "https://asaas/f/nova");
  });

  it("upgrade by boleto: shows the boleto link", async () => {
    mockGet.mockResolvedValue(CONTA);
    mockPost.mockResolvedValue({
      checkout_url: "https://asaas/b/boleto",
      assinatura_id: "a2",
      membro_id: "m1",
      pix_qr: null,
      status: null,
    });
    renderPortal(<MinhaConta />);
    fireEvent.click(await screen.findByRole("button", { name: "Quero o Premium" }));
    fireEvent.click(screen.getByLabelText("Boleto"));
    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: "12.345.678/0001-90" } });
    fireEvent.click(screen.getByRole("button", { name: "Gerar cobrança" }));
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/portal/assinatura", {
        plano_id: "p-premium",
        metodo: "boleto",
        cpf_cnpj: "12345678000190",
      }),
    );
    expect(await screen.findByRole("link", { name: /Abrir o boleto/ })).toHaveAttribute("href", "https://asaas/b/boleto");
  });

  it("shows the 409 text verbatim", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockResolvedValue(CONTA);
    mockPost.mockRejectedValue(new ApiError(409, "Você já tem este plano."));
    renderPortal(<MinhaConta />);
    fireEvent.click(await screen.findByRole("button", { name: "Quero o Premium" }));
    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: "12345678901" } });
    fireEvent.click(screen.getByRole("button", { name: "Gerar cobrança" }));
    expect(await screen.findByText("Você já tem este plano.")).toBeInTheDocument();
  });

  it("/portal?trocar=<id> (the signup's paid-tier path) opens the dialog for that tier", async () => {
    mockGet.mockResolvedValue(CONTA);
    renderPortal(<MinhaConta />, "/portal?trocar=p-premium");
    expect(await screen.findByRole("dialog", { name: "Mudar para o Premium" })).toBeInTheDocument();
  });

  it("?trocar= with a tier that is not an upgrade opens nothing", async () => {
    mockGet.mockResolvedValue(CONTA);
    renderPortal(<MinhaConta />, "/portal?trocar=p-ouvinte");
    await screen.findByRole("button", { name: "Quero o Premium" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cancels only after confirmation and explains access until pago_ate", async () => {
    mockGet.mockResolvedValue({ ...CONTA, assinatura: { ...CONTA.assinatura, estado: "ativa" } });
    mockPost.mockResolvedValue({ ...CONTA.assinatura, estado: "cancelada", pago_ate: "2026-10-01" });
    renderPortal(<MinhaConta />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar assinatura" }));
    expect(mockPost).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Manter assinatura" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar cancelamento" }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/portal/assinatura/cancelar", { motivo: null }));
    expect(await screen.findByTestId("cancelamento-feito")).toHaveTextContent("01/10/2026");
  });

  it("shows the 502 gateway text verbatim", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockResolvedValue({ ...CONTA, assinatura: { ...CONTA.assinatura, estado: "ativa" } });
    mockPost.mockRejectedValue(new ApiError(502, "Não foi possível cancelar no gateway. Tente novamente."));
    renderPortal(<MinhaConta />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar assinatura" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar cancelamento" }));
    expect(await screen.findByText("Não foi possível cancelar no gateway. Tente novamente.")).toBeInTheDocument();
  });

  it("error state + care line in the footer", async () => {
    const { ApiError } = await import("@noctusai/lib");
    mockGet.mockRejectedValue(new ApiError(500, "Erro interno."));
    renderPortal(<MinhaConta />);
    expect(await screen.findByText("Erro interno.")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("CVV 188");
  });
});
