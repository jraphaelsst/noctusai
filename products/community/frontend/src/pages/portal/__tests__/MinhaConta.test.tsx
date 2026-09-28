/**
 * Portal minha conta — CONTRACT.md §Member portal: grace banner when
 * `estado === "carencia"` (carencia_ate + invoice link), upgrade cards →
 * `/assinar?plano=<id>`, cancel with confirmation explaining `pago_ate`.
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

  it("offers only higher tiers as upgrades, linking to the pre-filled checkout", async () => {
    mockGet.mockResolvedValue(CONTA);
    renderPortal(<MinhaConta />);
    const link = await screen.findByRole("link", { name: "Quero o Premium" });
    expect(link).toHaveAttribute("href", "/assinar?plano=p-premium");
    expect(screen.queryByRole("link", { name: "Quero o Gratuito" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Quero o Ouvinte" })).not.toBeInTheDocument();
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
