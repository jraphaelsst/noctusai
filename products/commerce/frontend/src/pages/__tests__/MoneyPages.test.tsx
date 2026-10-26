/**
 * Money UI (CONTRACT P4 §5/§6): staff order → refund (gated by org admin, idempotent, "em andamento"), store
 * settings → installments + fiscal, storefront → card installments at checkout and "gerar novo pagamento".
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import "@testing-library/jest-dom";

const { apiMock, auth, admin } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn() },
  auth: { user: null as unknown },
  admin: { value: false },
}));
vi.mock("@noctusai/seed/infra", () => ({ api: apiMock, useAuthStore: () => auth }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<typeof import("@noctusai/lib/design-system")>()),
  useIsOrgAdmin: () => admin.value,
}));

import { ApiError, cartStorageKey } from "@noctusai/lib";
import OrderView from "../admin/OrderView";
import Configuracoes from "../admin/Configuracoes";
import StoreOrder from "../storefront/StoreOrder";
import StoreCheckout from "../storefront/StoreCheckout";
import { renderRoutes, stubFetch, STOREFRONT, VALID_CPF } from "@/test-utils";

const CHARGE = { id: "c1", order_id: "o1", attempt: 1, gateway: "asaas", payment_method: "credit_card", installment_count: 3, amount_cents: 10000, status: "paid", created_at: "2026-10-14T10:00:00Z", closed_at: null };
const ORDER = {
  id: "o1", token: "tok", customer_id: null, status: "paid", subtotal_cents: 10000, discount_cents: 0, total_cents: 10000, currency: "BRL", coupon_id: null,
  payment_method: "credit_card", gateway: "asaas", gateway_charge_id: "g", checkout_url: null, pix_qr: null, expires_at: null, paid_at: "2026-10-14T10:05:00Z",
  platform_fee_cents: 0, created_at: "2026-10-14T10:00:00Z", items: [], events: [], charges: [CHARGE], refunds: [], reminders: [],
};
const REFUND = { id: "r1", order_id: "o1", charge_id: "c1", amount_cents: 10000, reason: "desistência", status: "requested", gateway_refund_id: null, requested_by: null, created_at: "2026-10-14T11:00:00Z", done_at: null };
const PROFILE = {
  org_id: "org", version: 4, legal_name: "Loja LTDA", trade_name: "Loja", cnpj: "11222333000181", tax_regime: "simples", tax_treatment: {}, locale: "pt-BR", currency: "BRL",
  brand_tokens: {}, address: {}, contact_email: "a@b.co", contact_phone: "1133334444",
};
const FISCAL = {
  cnpj: "11222333000181", tax_regime: "lucro_presumido", inscricao_municipal: null, inscricao_estadual: null, municipio_ibge: null, invoice_company_ref: null,
  certificate_valid_until: null, certificate_cnpj: null, auto_issue_invoices: false, nfse_mode: "municipal", nfse_cutover: {}, nfse_nacional_forced: false,
  certificate_status: "ausente", can_cutover: false, can_rollback: false, version: 1,
};

function routeGets(table: Record<string, unknown>) {
  apiMock.get.mockImplementation((url: string) => {
    const hit = table[url];
    if (hit instanceof Error) return Promise.reject(hit);
    return hit === undefined ? Promise.reject(new ApiError(404, `unrouted ${url}`)) : Promise.resolve(hit);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  admin.value = false;
  auth.user = null;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Admin › pedido › dinheiro", () => {
  const ROUTES = { "/admin/pedidos/:id": <OrderView /> };
  const gets = (order: unknown) => ({ "/api/commerce/profile": { data: null }, "/api/commerce/orders/o1": { data: order }, "/api/commerce/orders/o1/invoices": { data: [] } });

  it("shows charges with parcelas; staff see no refund / invoice actions", async () => {
    routeGets(gets(ORDER));
    renderRoutes("/admin/pedidos/o1", ROUTES);
    const panel = await screen.findByTestId("order-money");
    expect(within(panel).getByText("3x")).toBeInTheDocument();
    expect(within(panel).getByText("Cartão de crédito")).toBeInTheDocument();
    await within(panel).findByText("Nenhuma nota fiscal emitida.");
    expect(screen.queryByRole("button", { name: "Reembolsar…" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Emitir" })).toBeNull();
  });

  it("an admin refunds: Idempotency-Key header, no amount for a full refund, and the 'em andamento' state when requested", async () => {
    admin.value = true;
    routeGets(gets(ORDER));
    apiMock.post.mockResolvedValue({ data: REFUND });
    renderRoutes("/admin/pedidos/o1", ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Reembolsar…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Motivo/), { target: { value: "desistência" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reembolsar" }));
    expect(await within(dialog).findByTestId("refund-in-progress")).toHaveTextContent("em andamento");
    const [path, body, opts] = apiMock.post.mock.calls[0];
    expect(path).toBe("/api/commerce/orders/o1/refunds");
    expect(body).toEqual({ reason: "desistência" });
    expect(opts.headers["Idempotency-Key"]).toBeTruthy();
  });

  it("an order with a requested refund shows it as em andamento in the history", async () => {
    admin.value = true;
    routeGets(gets({ ...ORDER, refunds: [REFUND] }));
    renderRoutes("/admin/pedidos/o1", ROUTES);
    const panel = await screen.findByTestId("order-money");
    expect(within(within(panel).getByTestId("refund-history")).getByText("Em andamento")).toBeInTheDocument();
  });

  it("the invoices list error state offers a retry", async () => {
    routeGets({ ...gets(ORDER), "/api/commerce/orders/o1/invoices": new ApiError(500, "boom") });
    renderRoutes("/admin/pedidos/o1", ROUTES);
    const panel = await screen.findByTestId("order-money");
    expect(await within(panel).findByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });
});

describe("Admin › loja › parcelamento e fiscal", () => {
  const ROUTES = { "/admin/configuracoes/*": <Configuracoes /> };
  const gets = () => ({ "/api/commerce/profile": { data: PROFILE }, "/api/commerce/fiscal": { data: FISCAL }, "/api/commerce/hosts": new ApiError(403, "no") });

  it("the installments form defaults to 12x / 3x sem juros / platform rate and saves the whole profile (admin)", async () => {
    admin.value = true;
    routeGets(gets());
    apiMock.put.mockResolvedValue({ data: { ...PROFILE, version: 5 } });
    renderRoutes("/admin/configuracoes/loja", ROUTES);
    const max = await screen.findByLabelText("Máximo de parcelas");
    expect(max).toHaveValue("12");
    expect(screen.getByLabelText("Parcelas sem juros (até)")).toHaveValue("3");
    fireEvent.click(screen.getByRole("button", { name: "Salvar parcelamento" }));
    await waitFor(() => expect(apiMock.put).toHaveBeenCalled());
    expect(apiMock.put.mock.calls[0][0]).toBe("/api/commerce/profile");
    expect(apiMock.put.mock.calls[0][1]).toMatchObject({ legal_name: "Loja LTDA", installments_max: 12, installments_interest_free: 3, installment_interest_monthly_bps: null, expected_version: 4 });
  });

  it("staff see both money sections read-only", async () => {
    routeGets(gets());
    renderRoutes("/admin/configuracoes/loja", ROUTES);
    expect(await screen.findByLabelText("Máximo de parcelas")).toBeDisabled();
    expect(await screen.findByText("Nenhum certificado enviado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar parcelamento" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enviar certificado" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Salvar dados fiscais" })).toBeNull();
  });

  it("an admin sees the certificate upload and the fiscal save", async () => {
    admin.value = true;
    routeGets(gets());
    renderRoutes("/admin/configuracoes/loja", ROUTES);
    expect(await screen.findByRole("button", { name: "Enviar certificado" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar dados fiscais" })).toBeInTheDocument();
  });

  it("a failing fiscal read shows the error state with retry (the profile part still renders)", async () => {
    routeGets({ ...gets(), "/api/commerce/fiscal": new ApiError(500, "boom") });
    renderRoutes("/admin/configuracoes/loja", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
    expect(await screen.findByLabelText("Máximo de parcelas")).toBeInTheDocument();
  });
});

describe("Storefront › parcelamento e novo pagamento", () => {
  const QUOTE = {
    lines: [{ offer_id: "o1", product_id: "p1", title: "Curso de Foto", product_type: "digital", fulfillment_type: "digital_delivery", unit_price_cents: 10000, qty: 1, total_cents: 10000 }],
    subtotal_cents: 10000, discount_cents: 0, total_cents: 10000, currency: "BRL", requires_immediate_delivery_waiver: false,
    installment_options: [
      { count: 1, installment_cents: 10000, total_cents: 10000, interest_free: true },
      { count: 3, installment_cents: 3333, total_cents: 10000, interest_free: true },
      { count: 6, installment_cents: 1800, total_cents: 10800, interest_free: false },
    ],
  };

  it("checkout: the card shows the picker (parcela + total with interest) and sends the chosen count", async () => {
    window.localStorage.setItem(cartStorageKey(), JSON.stringify([{ offer_id: "o1", product_slug: "c", title: "Curso de Foto", offer_name: "Acesso", unit_price_cents: 10000, currency: "BRL", qty: 1 }]));
    const fetchMock = stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "POST /api/storefront/checkout/quote": { body: { data: QUOTE } },
      "POST /api/storefront/checkout": { status: 201, body: { data: { order_token: "tok", status: "pending_payment" } } },
      "GET /api/storefront/orders/tok": { body: { data: { token: "tok", status: "pending_payment", items: [], subtotal_cents: 0, discount_cents: 0, total_cents: 0, currency: "BRL", payment_method: "credit_card", checkout_url: null, pix_qr: null, expires_at: null, paid_at: null } } },
    });
    renderRoutes("/checkout", { "/checkout": <StoreCheckout />, "/pedido/:token": <StoreOrder /> });
    fireEvent.change(await screen.findByLabelText(/Nome completo/), { target: { value: "Maria Souza" } });
    expect(screen.queryByTestId("installment-picker")).toBeNull(); // pix by default
    fireEvent.click(screen.getByLabelText("Cartão de crédito"));
    fireEvent.click(await screen.findByLabelText(/6x de R\$\s18,00 \(total R\$\s108,00\)/));
    expect(screen.getByRole("button", { name: /Pagar R\$\s108,00/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/E-mail/), { target: { value: "maria@example.com" } });
    fireEvent.change(screen.getByLabelText(/CPF ou CNPJ/), { target: { value: VALID_CPF } });
    fireEvent.change(screen.getByLabelText(/Telefone/), { target: { value: "11987654321" } });
    fireEvent.click(screen.getByLabelText(/Termos de uso/));
    fireEvent.click(screen.getByLabelText(/Política de privacidade/));
    fireEvent.click(screen.getByRole("button", { name: /Pagar/ }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/pedido/tok"));
    const call = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/api/storefront/checkout") && i?.method === "POST")!;
    expect(JSON.parse(String(call[1]!.body))).toMatchObject({ payment_method: "credit_card", installments: 6 });
  });

  it("an expired order regenerates its payment by token and the page picks up the new charge", async () => {
    const order = { token: "tok", status: "expired", items: [], subtotal_cents: 10000, discount_cents: 0, total_cents: 10000, currency: "BRL", payment_method: "pix", checkout_url: null, pix_qr: null, expires_at: null, paid_at: null };
    let regenerated = false;
    const fetchMock = stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok": () => ({ body: { data: regenerated ? { ...order, status: "pending_payment", pix_qr: { payload: "NOVOPIX" } } : order } }),
      "POST /api/storefront/orders/tok/payment": () => {
        regenerated = true;
        return { body: { data: { status: "pending_payment" } } };
      },
    });
    renderRoutes("/pedido/tok", { "/pedido/:token": <StoreOrder /> });
    fireEvent.click(await screen.findByRole("button", { name: "Gerar novo pagamento" }));
    expect(await screen.findByLabelText(/Pix/i)).toHaveValue("NOVOPIX");
    const call = fetchMock.mock.calls.find(([u, i]) => String(u).endsWith("/orders/tok/payment") && i?.method === "POST")!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ payment_method: "pix" });
  });

  it("a refused regenerate (429) is shown to the buyer", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/orders/tok": { body: { data: { token: "tok", status: "expired", items: [], subtotal_cents: 1, discount_cents: 0, total_cents: 1, currency: "BRL", payment_method: "pix", checkout_url: null, pix_qr: null, expires_at: null, paid_at: null } } },
      "POST /api/storefront/orders/tok/payment": { status: 429, body: { error: { code: "muitas_tentativas", message: "Aguarde um minuto antes de gerar um novo pagamento." } } },
    });
    renderRoutes("/pedido/tok", { "/pedido/:token": <StoreOrder /> });
    fireEvent.click(await screen.findByRole("button", { name: "Gerar novo pagamento" }));
    expect(await screen.findByText(/Aguarde um minuto/)).toBeInTheDocument();
  });
});
