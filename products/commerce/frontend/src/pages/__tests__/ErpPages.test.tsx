/**
 * ERP back-office pages on the commerce host: `/admin/compras`, `/admin/orcamentos`, `/admin/contratos`, the customer's public
 * quote link `/orcamento/:token`, and the product editor's item link. Real organs over mocked transports: loading / empty /
 * error / success, admin gating (UX hint — the server enforces), the public page failing closed, and the route + nav + page-status wiring.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const { apiMock, admin } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(), download: vi.fn() },
  admin: { value: false },
}));
vi.mock("@noctusai/seed/infra", () => ({ api: apiMock, useAuthStore: () => ({ user: null }) }));
vi.mock("@noctusai/lib/design-system", async (orig) => ({
  ...(await orig<typeof import("@noctusai/lib/design-system")>()),
  useIsOrgAdmin: () => admin.value,
}));

import { ApiError } from "@noctusai/lib";
import Compras from "../admin/Compras";
import Orcamentos from "../admin/Orcamentos";
import Contratos from "../admin/Contratos";
import ProductEdit from "../admin/ProductEdit";
import QuoteAccept from "../quote/QuoteAccept";
import { renderRoutes, stubFetch } from "@/test-utils";

const page = (rows: unknown[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length, total_pages: 1 } });

/** GETs answer from `table[path]`; any other path 404s like an unmounted router would. */
function routeGets(table: Record<string, unknown>) {
  apiMock.get.mockImplementation((url: string) => {
    const hit = table[url];
    if (hit instanceof Error) return Promise.reject(hit);
    return hit === undefined ? Promise.reject(new ApiError(404, `unrouted ${url}`)) : Promise.resolve(hit);
  });
}

const PROFILE = { "/api/commerce/profile": { data: null } };
const PURCHASE = {
  id: "po1", org_id: "o", number: 7, status: "approved", party_id: null, supplier_name: "Malharia Sul", warehouse_id: null,
  expected_date: null, installments_count: 1, first_due_days: 30, interval_days: 30, freight_cents: 0, discount_cents: 0,
  other_cents: 0, goods_cents: 25000, total_cents: 25000, notes: null, approved_by: null, approved_at: null, sent_at: null,
  cancelled_at: null, cancel_reason: null, created_at: "2026-10-14T10:00:00Z", updated_at: "2026-10-14T10:00:00Z", lines: [], receipts: [],
};
const QUOTE = {
  id: "q1", org_id: "o", number: "ORC-00001", root_id: "q1", version: 1, is_current: true, party_id: "pa1", title: "Uniformes",
  status: "draft", currency: "BRL", valid_until: null, notes: null, terms: null, convert_to: null, subtotal_cents: 50000,
  discount_cents: 0, total_cents: 50000, sent_at: null, last_sent_to: null, viewed_at: null, accepted_at: null, rejected_at: null,
  expired_at: null, rejection_reason: null, conversion_status: "none", conversion_kind: null, conversion_ref: null,
  conversion_error: null, signature_ref: null, signature_status: null, created_by: null, created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-14T10:00:00Z", party: { id: "pa1", legal_name: "Ana Souza", trade_name: null, email: "ana@example.com" },
};
const CONTRACT = {
  id: "c1", org_id: "o", number: "CT-1", title: "Manutenção mensal", status: "draft", billing_model: "recurring", amount_cents: 90000,
  party_id: null, party_name: "Ana Souza", party_doc: null, start_date: "2026-11-01", end_date: null, notice_days: 30,
};
const ITEM = { id: "i1", org_id: "o", sku: "CAM-001", name: "Camiseta", item_type: "goods", unit: "UN", is_active: true, price_cents: 5000 };

beforeEach(() => {
  vi.clearAllMocks();
  admin.value = false;
  routeGets({ ...PROFILE, "/api/items": page([ITEM]), "/api/parties": page([]) });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Admin › Compras", () => {
  const ROUTES = { "/admin/compras": <Compras /> };

  it("lists real rows from GET /api/purchasing/orders (success)", async () => {
    routeGets({ ...PROFILE, "/api/purchasing/orders": page([PURCHASE]) });
    renderRoutes("/admin/compras", ROUTES);
    expect(await screen.findByText("Malharia Sul")).toBeInTheDocument();
    expect(screen.getByText("#7")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Compras", level: 1 })).toBeInTheDocument();
  });

  it("shows the empty state and the error state with retry", async () => {
    routeGets({ ...PROFILE, "/api/purchasing/orders": page([]) });
    renderRoutes("/admin/compras", ROUTES);
    expect(await screen.findByText("Nenhum pedido de compra.")).toBeInTheDocument();
    cleanup();
    routeGets({ ...PROFILE, "/api/purchasing/orders": new ApiError(500, "boom") });
    renderRoutes("/admin/compras", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it("staff get a read-only list: no new-order button, no approvers tab; org admins get both", async () => {
    routeGets({ ...PROFILE, "/api/purchasing/orders": page([PURCHASE]), "/api/team": { data: [] } });
    renderRoutes("/admin/compras", ROUTES);
    await screen.findByText("Malharia Sul");
    expect(screen.queryByRole("button", { name: "Novo pedido" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Aprovadores" })).toBeNull();
    cleanup();
    admin.value = true;
    renderRoutes("/admin/compras", ROUTES);
    expect(await screen.findByRole("button", { name: "Novo pedido" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Aprovadores" })).toBeInTheDocument();
  });

  it("opens an order: its detail is fetched and an admin can receive an approved order", async () => {
    admin.value = true;
    routeGets({
      ...PROFILE,
      "/api/purchasing/orders": page([PURCHASE]),
      "/api/purchasing/orders/po1": { data: PURCHASE },
      "/api/purchasing/settings": { data: { approval_threshold_cents: null, persisted: false } },
      "/api/purchasing/receipts": page([]),
      "/api/parties": page([]),
      "/api/items": page([]),
      "/api/inventory/warehouses": { data: [] },
    });
    renderRoutes("/admin/compras", ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Abrir" }));
    expect(await screen.findByRole("button", { name: "Receber mercadoria" })).toBeInTheDocument();
    expect(apiMock.get).toHaveBeenCalledWith("/api/purchasing/orders/po1");
  });
});

describe("Admin › Orcamentos", () => {
  const ROUTES = { "/admin/orcamentos": <Orcamentos /> };

  it("lists real rows from GET /api/quotes and feeds the editor the org's customers and items", async () => {
    routeGets({
      ...PROFILE,
      "/api/quotes": page([QUOTE]),
      "/api/items": page([ITEM]),
      "/api/parties": page([{ id: "pa1", legal_name: "Ana Souza", trade_name: null, email: "ana@example.com" }]),
    });
    renderRoutes("/admin/orcamentos", ROUTES);
    expect(await screen.findByText("ORC-00001")).toBeInTheDocument();
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith("/api/parties", { role: "customer", active: "true", page_size: 100 }));
    expect(apiMock.get).toHaveBeenCalledWith("/api/items", { active: "true", page_size: 100 });
  });

  it("empty and error states; the create button is for org admins only", async () => {
    routeGets({ ...PROFILE, "/api/quotes": page([]) });
    renderRoutes("/admin/orcamentos", ROUTES);
    expect(await screen.findByText("Nenhum orçamento ainda.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Novo orçamento" })).toBeNull();
    cleanup();
    admin.value = true;
    renderRoutes("/admin/orcamentos", ROUTES);
    expect(await screen.findByRole("button", { name: "Novo orçamento" })).toBeInTheDocument();
    cleanup();
    routeGets({ ...PROFILE, "/api/quotes": new ApiError(500, "boom") });
    renderRoutes("/admin/orcamentos", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

describe("Admin › Contratos", () => {
  const ROUTES = { "/admin/contratos": <Contratos /> };

  it("lists real rows from GET /api/contracts, with empty and error states", async () => {
    routeGets({ ...PROFILE, "/api/contracts": page([CONTRACT]) });
    renderRoutes("/admin/contratos", ROUTES);
    expect(await screen.findByText("Manutenção mensal")).toBeInTheDocument();
    cleanup();
    routeGets({ ...PROFILE, "/api/contracts": page([]) });
    renderRoutes("/admin/contratos", ROUTES);
    expect(await screen.findByText("Nenhum contrato ainda.")).toBeInTheDocument();
    cleanup();
    routeGets({ ...PROFILE, "/api/contracts": new ApiError(500, "boom") });
    renderRoutes("/admin/contratos", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it("the create button is for org admins only", async () => {
    routeGets({ ...PROFILE, "/api/contracts": page([]) });
    renderRoutes("/admin/contratos", ROUTES);
    await screen.findByText("Nenhum contrato ainda.");
    expect(screen.queryByRole("button", { name: "Novo contrato" })).toBeNull();
    cleanup();
    admin.value = true;
    renderRoutes("/admin/contratos", ROUTES);
    expect(await screen.findByRole("button", { name: "Novo contrato" })).toBeInTheDocument();
  });
});

describe("Public › /orcamento/:token (no login)", () => {
  const ROUTES = { "/orcamento/:token": <QuoteAccept /> };
  const VIEW = {
    number: "ORC-00001", version: 1, title: "Uniformes", status: "sent", currency: "BRL", valid_until: null, notes: null, terms: null,
    subtotal_cents: 50000, discount_cents: 0, total_cents: 50000, party_name: "Ana Souza", issuer_name: "Loja Teste",
    lines: [{ position: 0, description: "Camiseta", unit: "UN", qty: 10, unit_price_cents: 5000, discount_cents: 0, total_cents: 50000 }],
    can_decide: true, decision: null, consent_template: "Eu, {name}, aceito este orçamento.",
  };

  it("renders the quote through the PUBLIC transport (fetch), never the authed api client", async () => {
    const fetchMock = stubFetch({ "GET /api/public/quotes/tok": { body: { data: VIEW } } });
    renderRoutes("/orcamento/tok", ROUTES);
    expect(await screen.findByText("Camiseta")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /ORC-00001/ })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
    expect(apiMock.get).not.toHaveBeenCalled();
  });

  it("a bad or expired token is one closed screen", async () => {
    stubFetch({ "GET /api/public/quotes/tok": { status: 404, body: { error: { code: "link_invalido", message: "Link inválido ou expirado." } } } });
    renderRoutes("/orcamento/tok", ROUTES);
    expect(await screen.findByText(/Link inválido ou expirado/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aceitar orçamento" })).toBeNull();
  });

  it("accepting posts the typed name and the agreement, then shows the recorded decision", async () => {
    let decided = false;
    const fetchMock = stubFetch({
      "GET /api/public/quotes/tok": () => ({
        body: { data: decided ? { ...VIEW, status: "accepted", can_decide: false, decision: { decision: "accepted", decided_at: "2026-10-14T12:00:00Z" } } : VIEW },
      }),
      "POST /api/public/quotes/tok/accept": () => {
        decided = true;
        return { body: { data: { ...VIEW, status: "accepted", can_decide: false, decision: { decision: "accepted", decided_at: "2026-10-14T12:00:00Z" } } } };
      },
    });
    renderRoutes("/orcamento/tok", ROUTES);
    fireEvent.change(await screen.findByLabelText(/Seu nome completo/), { target: { value: "Ana Souza" } });
    fireEvent.click(screen.getByLabelText(/Li e aceito os termos/));
    fireEvent.click(screen.getByRole("button", { name: "Aceitar orçamento" }));
    expect(await screen.findByText(/Orçamento aceito em/)).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({ name: "Ana Souza", agree: true });
  });
});

describe("Admin › Produto › item de estoque", () => {
  const PRODUCT = {
    id: "p1", slug: "camiseta", title: "Camiseta", description: "", product_type: "physical", fulfillment_type: "shipping",
    status: "draft", category_id: null, attributes: {}, tax_treatment_override: null, item_id: null, offers: [], media: [],
  };
  const ROUTES = { "/admin/produtos/:id": <ProductEdit /> };
  const gets = (items: unknown) => ({
    ...PROFILE,
    "/api/commerce/categories": { data: [] },
    "/api/commerce/products/p1": { data: PRODUCT },
    "/api/commerce/products/p1/offers": { data: [] },
    "/api/items": items,
  });

  it("offers the items catalog and PATCHes the chosen item_id", async () => {
    routeGets(gets(page([ITEM])));
    apiMock.patch.mockResolvedValue({ data: { ...PRODUCT, item_id: "i1" } });
    renderRoutes("/admin/produtos/p1", ROUTES);
    const select = await screen.findByLabelText("Item de estoque");
    await screen.findByRole("option", { name: "CAM-001 · Camiseta" });
    fireEvent.change(select, { target: { value: "i1" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(apiMock.patch).toHaveBeenCalled());
    expect(apiMock.patch.mock.calls[0][0]).toBe("/api/commerce/products/p1");
    expect(apiMock.patch.mock.calls[0][1]).toMatchObject({ item_id: "i1" });
  });

  it("sends no item_id (and shows no picker) while the catalog is unavailable — a save can never unlink by accident", async () => {
    routeGets(gets(new ApiError(500, "boom")));
    apiMock.patch.mockResolvedValue({ data: PRODUCT });
    renderRoutes("/admin/produtos/p1", ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Salvar" }));
    await waitFor(() => expect(apiMock.patch).toHaveBeenCalled());
    expect(screen.queryByLabelText("Item de estoque")).toBeNull();
    expect(apiMock.patch.mock.calls[0][1]).not.toHaveProperty("item_id");
  });
});

describe("Wiring › routes, nav and page status", () => {
  const SRC = join(__dirname, "..", "..");
  const app = readFileSync(join(SRC, "App.tsx"), "utf8");
  const migrations = join(SRC, "..", "..", "backend", "migrations");

  it("the three pages are routes AND nav entries keyed by their status_pagina name", () => {
    for (const [route, path] of [["compras", "/admin/compras"], ["orcamentos", "/admin/orcamentos"], ["contratos", "/admin/contratos"]]) {
      expect(app).toContain(`{ path: "${path}", component:`);
      expect(app).toContain(`href: "${path}"`);
      expect(app).toContain(`route: "${route}"`);
    }
  });

  it("the customer's quote link is a PUBLIC route (outside the authed shell), never an admin one", () => {
    const publicBlock = app.slice(app.indexOf("publicRoutes: ["));
    expect(publicBlock).toContain('{ path: "/orcamento/:token", component: QuoteAccept }');
    const authedBlock = app.slice(app.indexOf("  routes: ["), app.indexOf("publicRoutes: ["));
    expect(authedBlock).not.toContain("/orcamento/:token");
  });

  it("every nav route key of the new pages has a production status_pagina row in a migration", () => {
    const sql = readdirSync(migrations).map((f) => readFileSync(join(migrations, f), "utf8")).join("\n");
    for (const page of ["compras", "orcamentos", "contratos"]) expect(sql).toContain(`('${page}', 'producao')`);
  });
});
