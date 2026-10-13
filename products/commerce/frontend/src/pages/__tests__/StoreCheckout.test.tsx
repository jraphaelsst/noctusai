/** Storefront — cart → checkout submit → public order view, against the public `fetch` transport. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";

const { apiMock, auth } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  auth: { user: null as unknown },
}));
vi.mock("@noctusai/seed/infra", () => ({ api: apiMock, useAuthStore: () => auth }));

import { cartStorageKey } from "@noctusai/lib";
import StoreCart from "../storefront/StoreCart";
import StoreCheckout from "../storefront/StoreCheckout";
import StoreOrder from "../storefront/StoreOrder";
import { renderRoutes, stubFetch, STOREFRONT, VALID_CPF } from "@/test-utils";

const QUOTE = {
  lines: [
    {
      offer_id: "o1",
      product_id: "p1",
      title: "Curso de Foto",
      product_type: "digital",
      fulfillment_type: "digital_delivery",
      unit_price_cents: 9900,
      qty: 1,
      total_cents: 9900,
    },
  ],
  subtotal_cents: 9900,
  discount_cents: 0,
  total_cents: 9900,
  currency: "BRL",
  requires_immediate_delivery_waiver: true,
};

const PENDING_ORDER = {
  token: "tok123",
  status: "pending_payment",
  items: [{ title: "Curso de Foto", qty: 1, unit_price_cents: 9900, total_cents: 9900, product_type: "digital" }],
  subtotal_cents: 9900,
  discount_cents: 0,
  total_cents: 9900,
  currency: "BRL",
  payment_method: "pix",
  checkout_url: null,
  pix_qr: { payload: "00020126PIXCOPIAECOLA", encoded_image: null },
  expires_at: null,
  paid_at: null,
};

const ROUTES = {
  "/carrinho": <StoreCart />,
  "/checkout": <StoreCheckout />,
  "/pedido/:token": <StoreOrder />,
};

function seedCart() {
  window.localStorage.setItem(
    cartStorageKey(),
    JSON.stringify([
      { offer_id: "o1", product_slug: "curso-de-foto", title: "Curso de Foto", offer_name: "Acesso", unit_price_cents: 9900, currency: "BRL", qty: 1 },
    ]),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  auth.user = null;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Storefront › checkout", () => {
  it("cart quotes server-side and goes to checkout carrying the coupon", async () => {
    seedCart();
    const fetchMock = stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "POST /api/storefront/checkout/quote": { body: { data: QUOTE } },
    });
    renderRoutes("/carrinho?cupom=PROMO10", ROUTES);
    expect(await screen.findByText(/Curso de Foto/)).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/checkout/quote") && i?.method === "POST")).toBe(true),
    );
    const quoteBody = JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/checkout/quote"))![1]!.body));
    expect(quoteBody).toEqual({ items: [{ offer_id: "o1", qty: 1 }], coupon: "PROMO10" });
    fireEvent.click(await screen.findByRole("button", { name: /Finalizar|Continuar|Checkout/i }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/checkout?cupom=PROMO10"));
  });

  it("checkout with an empty cart shows the empty state, never the form", async () => {
    stubFetch({ "GET /api/storefront": { body: { data: STOREFRONT } } });
    renderRoutes("/checkout", ROUTES);
    expect(await screen.findByText(/Seu carrinho está vazio/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pagar/ })).toBeNull();
  });

  it("submits consents + waiver, clears the cart and opens the public order view", async () => {
    seedCart();
    const fetchMock = stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "POST /api/storefront/checkout/quote": { body: { data: QUOTE } },
      "POST /api/storefront/checkout": { status: 201, body: { data: { order_token: "tok123", status: "pending_payment" } } },
      "GET /api/storefront/orders/tok123": { body: { data: PENDING_ORDER } },
    });
    renderRoutes("/checkout", ROUTES);

    fireEvent.change(await screen.findByLabelText(/Nome completo/), { target: { value: "Maria Souza" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "Maria@Example.com" } });
    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: VALID_CPF } });
    fireEvent.change(screen.getByLabelText(/Telefone/), { target: { value: "11987654321" } });
    fireEvent.click(screen.getByLabelText(/Termos de uso/));
    fireEvent.click(screen.getByLabelText(/Política de privacidade/));
    fireEvent.click(screen.getByLabelText(/entrega imediata do conteúdo digital/));
    fireEvent.click(screen.getByRole("button", { name: /Pagar/ }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/pedido/tok123"));
    const call = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/api/storefront/checkout") && i?.method === "POST")!;
    const body = JSON.parse(String(call[1]!.body));
    expect(body.buyer).toEqual({ name: "Maria Souza", email: "maria@example.com", doc: "52998224725", phone: "11987654321" });
    expect(body.consents).toEqual({ terms_version: "t1", privacy_version: "p1", marketing: false, immediate_delivery_waiver: true });
    expect(body.items).toEqual([{ offer_id: "o1", qty: 1 }]);
    expect(JSON.parse(window.localStorage.getItem(cartStorageKey()) ?? "[]")).toEqual([]);
    expect(await screen.findByText(/Aguardando a confirmação do pagamento/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Pix/i)).toHaveValue("00020126PIXCOPIAECOLA");
  });

  it("a 503 pagamento_indisponivel keeps the buyer on checkout with the error shown", async () => {
    seedCart();
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "POST /api/storefront/checkout/quote": { body: { data: QUOTE } },
      "POST /api/storefront/checkout": {
        status: 503,
        body: { error: { code: "pagamento_indisponivel", message: "Pagamento indisponível." } },
      },
    });
    renderRoutes("/checkout", ROUTES);
    fireEvent.change(await screen.findByLabelText(/Nome completo/), { target: { value: "Maria Souza" } });
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "maria@example.com" } });
    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: VALID_CPF } });
    fireEvent.change(screen.getByLabelText(/Telefone/), { target: { value: "11987654321" } });
    fireEvent.click(screen.getByLabelText(/Termos de uso/));
    fireEvent.click(screen.getByLabelText(/Política de privacidade/));
    fireEvent.click(screen.getByLabelText(/entrega imediata do conteúdo digital/));
    fireEvent.click(screen.getByRole("button", { name: /Pagar/ }));
    expect(await screen.findByText(/Pagamento indisponível/)).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/checkout");
    expect(JSON.parse(window.localStorage.getItem(cartStorageKey()) ?? "[]")).toHaveLength(1);
  });
});
