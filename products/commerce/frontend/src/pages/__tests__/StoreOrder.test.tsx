/** Storefront — public order view states + the back-office host's "no store here" behaviour. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

const { apiMock, auth } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  auth: { user: null as unknown },
}));
vi.mock("@noctusai/seed/infra", () => ({ api: apiMock, useAuthStore: () => auth }));

import StoreOrder from "../storefront/StoreOrder";
import StoreHome from "../storefront/StoreHome";
import { renderRoutes, stubFetch, STOREFRONT } from "@/test-utils";

const ORDER = {
  token: "tok123",
  status: "paid",
  items: [{ title: "Curso de Foto", qty: 2, unit_price_cents: 9900, total_cents: 19800, product_type: "digital" }],
  subtotal_cents: 19800,
  discount_cents: 0,
  total_cents: 19800,
  currency: "BRL",
  payment_method: "credit_card",
  checkout_url: null,
  pix_qr: null,
  expires_at: null,
  paid_at: "2026-10-12T10:00:00Z",
};

const ROUTES = { "/pedido/:token": <StoreOrder />, "/": <StoreHome /> };

beforeEach(() => {
  vi.clearAllMocks();
  auth.user = null;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Storefront › order view", () => {
  it("paid: confirmation + items + total", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok123": { body: { data: ORDER } },
    });
    renderRoutes("/pedido/tok123", ROUTES);
    expect(await screen.findByText(/Pagamento confirmado/)).toBeInTheDocument();
    expect(screen.getByText(/2× Curso de Foto/)).toBeInTheDocument();
    expect(screen.getAllByText(/198,00/).length).toBeGreaterThan(0);
  });

  it("pending with hosted checkout: waiting copy + checkout link", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok123": {
        body: { data: { ...ORDER, status: "pending_payment", paid_at: null, checkout_url: "https://sandbox.asaas.com/c/x" } },
      },
    });
    renderRoutes("/pedido/tok123", ROUTES);
    expect(await screen.findByText(/Aguardando a confirmação do pagamento/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /pagamento|checkout|pagar/i })).toHaveAttribute("href", "https://sandbox.asaas.com/c/x");
  });

  it("expired: the regenerate-payment action is offered (closed in P4)", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok123": { body: { data: { ...ORDER, status: "expired", paid_at: null } } },
    });
    renderRoutes("/pedido/tok123", ROUTES);
    expect(await screen.findByText(/prazo de pagamento deste pedido expirou/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /novo pagamento|nova cobrança|gerar/i })).toBeEnabled();
  });

  it("unknown token: not-found state", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok123": { status: 404, body: { error: { code: "not_found", message: "Pedido não encontrado." } } },
    });
    renderRoutes("/pedido/tok123", ROUTES);
    expect(await screen.findByText("Pedido não encontrado.")).toBeInTheDocument();
  });

  it("transport error: error state with retry that recovers", async () => {
    let fail = true;
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok123": () => (fail ? { status: 500, body: { error: { message: "falhou" } } } : { body: { data: ORDER } }),
    });
    renderRoutes("/pedido/tok123", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText(/Pagamento confirmado/)).toBeInTheDocument();
  });
});

describe("Storefront › no store on this address (back-office host)", () => {
  it("anonymous visitor: organ no-store state + staff login link", async () => {
    stubFetch({ "GET /api/storefront": { status: 404, body: { error: { code: "not_found", message: "Loja não encontrada." } } } });
    renderRoutes("/", ROUTES);
    expect(await screen.findByText("Nenhuma loja neste endereço")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Área do lojista" })).toHaveAttribute("href", "/login");
  });

  it("signed-in staff: sent on to /admin", async () => {
    auth.user = { id: "u1" };
    stubFetch({ "GET /api/storefront": { status: 404, body: { error: { code: "not_found", message: "Loja não encontrada." } } } });
    renderRoutes("/", ROUTES);
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/admin"));
  });
});
