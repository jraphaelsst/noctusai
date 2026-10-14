/**
 * Back-office modules mounted from the seed organs (P4 + ERP W1-W2): `/admin/financeiro/*`, `/admin/itens`,
 * `/admin/parceiros`, `/admin/estoque` — routing (URL ⇄ section), admin gating, loading / empty / error / success.
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
import Financeiro from "../admin/Financeiro";
import Itens from "../admin/Itens";
import Parceiros from "../admin/Parceiros";
import Estoque from "../admin/Estoque";
import { renderRoutes } from "@/test-utils";

const page = (rows: unknown[]) => ({ data: rows, pagination: { page: 1, page_size: 20, total: rows.length, total_pages: 1 } });
const ITEM = { id: "i1", org_id: "o", sku: "CAM-001", name: "Camiseta", description: null, item_type: "product", unit: "UN", category_id: null, is_active: true, cost_cents: 1000, price_cents: 3000 };

/** GETs answer from `table[path]`; any other path 404s like an unmounted router would. */
function routeGets(table: Record<string, unknown>) {
  apiMock.get.mockImplementation((url: string) => {
    const hit = table[url];
    if (hit instanceof Error) return Promise.reject(hit);
    return hit === undefined ? Promise.reject(new ApiError(404, `unrouted ${url}`)) : Promise.resolve(hit);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  admin.value = false;
  routeGets({ "/api/commerce/profile": { data: null } });
});
afterEach(cleanup);

describe("Admin › Financeiro", () => {
  const ROUTES = { "/admin/financeiro/*": <Financeiro /> };

  it("mounts the FinanceShell at the base URL (overview) with its nine sections", async () => {
    renderRoutes("/admin/financeiro", ROUTES);
    expect(await screen.findByRole("heading", { name: "Financeiro", level: 1 })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Financeiro" });
    expect(nav.querySelectorAll("button")).toHaveLength(9);
    expect(screen.getByRole("button", { name: "Visão geral" })).toHaveAttribute("aria-current", "page");
  });

  it("deep link /receber opens that section; clicking a section pushes its URL", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/finance/entries": page([]) });
    renderRoutes("/admin/financeiro/receber", ROUTES);
    expect(await screen.findByText("Nenhum lançamento encontrado com esses filtros.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contas a receber" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Contas a pagar" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/admin/financeiro/pagar"));
    fireEvent.click(screen.getByRole("button", { name: "Visão geral" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/admin\/financeiro$/));
  });

  it("an unknown segment redirects to the canonical URL of the overview", async () => {
    renderRoutes("/admin/financeiro/nao-existe", ROUTES);
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/admin\/financeiro$/));
  });

  it("write actions are for org admins only", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/finance/entries": page([]) });
    renderRoutes("/admin/financeiro/receber", ROUTES);
    await screen.findByText("Nenhum lançamento encontrado com esses filtros.");
    expect(screen.queryByRole("button", { name: "Novo lançamento" })).toBeNull();
    cleanup();
    admin.value = true;
    renderRoutes("/admin/financeiro/receber", ROUTES);
    expect(await screen.findByRole("button", { name: "Novo lançamento" })).toBeInTheDocument();
  });

  it("shows the list error state with retry when the API fails", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/finance/entries": new ApiError(500, "boom") });
    renderRoutes("/admin/financeiro/pagar", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });
});

describe("Admin › Itens", () => {
  const ROUTES = { "/admin/itens": <Itens /> };

  it("lists real rows from GET /api/items (success) and the empty state", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/items": page([ITEM]) });
    renderRoutes("/admin/itens", ROUTES);
    expect(await screen.findByText("Camiseta")).toBeInTheDocument();
    expect(screen.getByText("CAM-001")).toBeInTheDocument();
    cleanup();
    routeGets({ "/api/commerce/profile": { data: null }, "/api/items": page([]) });
    renderRoutes("/admin/itens", ROUTES);
    expect(await screen.findByText("Nenhum item cadastrado.")).toBeInTheDocument();
  });

  it("shows the error state when the list fails", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/items": new ApiError(500, "boom") });
    renderRoutes("/admin/itens", ROUTES);
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it("staff get a read-only list: no create, no import tab, rows do not open the editor", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/items": page([ITEM]) });
    renderRoutes("/admin/itens", ROUTES);
    fireEvent.click(await screen.findByText("Camiseta"));
    expect(screen.queryByRole("button", { name: "Novo item" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Importar / exportar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Voltar para itens" })).toBeNull();
  });

  it("an admin creates (editor opens) and has the import tab", async () => {
    admin.value = true;
    routeGets({ "/api/commerce/profile": { data: null }, "/api/items": page([ITEM]), "/api/items/categories": { data: [] } });
    renderRoutes("/admin/itens", ROUTES);
    expect(await screen.findByRole("tab", { name: "Importar / exportar" })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Novo item" }));
    expect(await screen.findByRole("button", { name: "Voltar para itens" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Voltar para itens" }));
    expect(await screen.findByText("Camiseta")).toBeInTheDocument();
  });
});

describe("Admin › Parceiros / Estoque", () => {
  it("Parceiros: success rows and the error state when /api/parties fails", async () => {
    const party = { id: "p1", org_id: "o", kind: "company", legal_name: "Fornecedor Alfa", trade_name: null, doc: null, roles: ["supplier"], is_active: true, email: null, phones: [], address: {}, state_registration: null, municipal_registration: null, notes: null, created_at: "2026-10-14T10:00:00Z", updated_at: "2026-10-14T10:00:00Z" };
    routeGets({ "/api/commerce/profile": { data: null }, "/api/parties": page([party]) });
    renderRoutes("/admin/parceiros", { "/admin/parceiros": <Parceiros /> });
    expect(await screen.findByText("Fornecedor Alfa")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Novo cadastro" })).toBeNull();
    cleanup();
    admin.value = true;
    routeGets({ "/api/commerce/profile": { data: null }, "/api/parties": new ApiError(500, "boom") });
    renderRoutes("/admin/parceiros", { "/admin/parceiros": <Parceiros /> });
    expect(await screen.findByText(/Não foi possível carregar/)).toBeInTheDocument();
  });

  it("Estoque: tabs render and a failing /api/inventory surfaces the error state", async () => {
    routeGets({ "/api/commerce/profile": { data: null }, "/api/items": page([]) });
    renderRoutes("/admin/estoque", { "/admin/estoque": <Estoque /> });
    expect(await screen.findByRole("tab", { name: "Saldos" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Depósitos" })).toBeInTheDocument();
    expect(await screen.findAllByText(/Não foi possível carregar/)).not.toHaveLength(0);
  });
});

describe("nav ↔ status_pagina parity (an item without a row is silently hidden)", () => {
  const frontendRoot = join(__dirname, "..", "..", "..");
  const migrations = join(frontendRoot, "..", "backend", "migrations");

  it("every nav `route` key of App.tsx has a status_pagina row in a migration", () => {
    const app = readFileSync(join(frontendRoot, "src", "App.tsx"), "utf8");
    const routes = [...app.matchAll(/route:\s*"([a-z-]+)"/g)].map((m) => m[1]);
    expect(routes).toEqual(expect.arrayContaining(["financeiro", "itens", "parceiros", "estoque"]));
    const sql = readdirSync(migrations).filter((f) => f.endsWith(".sql")).map((f) => readFileSync(join(migrations, f), "utf8")).join("\n");
    const missing = routes.filter((r) => !new RegExp(`\\(\\s*'${r}'\\s*,\\s*'(producao|desenvolvimento|desativado)'`).test(sql));
    expect(missing).toEqual([]);
  });

  it("the four ERP pages are producao (their routers are mounted), idempotently", () => {
    const sql = readFileSync(join(migrations, "019_finance_items_pages_status_pagina.sql"), "utf8");
    for (const page of ["financeiro", "itens", "parceiros", "estoque"]) expect(sql).toMatch(new RegExp(`\\('${page}', 'producao'\\)`));
    expect(sql).toMatch(/ON CONFLICT \(nome_pagina\) DO NOTHING/);
    expect(sql).not.toContain("NOC-REMEDIATE[commerce-parties-inventory-mount]");
  });
});

describe("Estoque › item labels", () => {
  it("fetches names for the VISIBLE item ids only and shows them instead of short ids", async () => {
    const bal = { org_id: "o", item_id: "aaaaaaaa-1111", warehouse_id: "w1", on_hand: 5, reserved: 0, available: 5, avg_cost_cents: 100, value_cents: 500, min_qty: null, low_stock: false, updated_at: "2026-10-14T10:00:00Z" };
    routeGets({
      "/api/commerce/profile": { data: null },
      "/api/inventory/warehouses": { data: [{ id: "w1", name: "Central", code: "C", is_active: true }] },
      "/api/inventory/balances": page([bal]),
      "/api/items/aaaaaaaa-1111": { data: { ...ITEM, id: "aaaaaaaa-1111", sku: "CAM-9", name: "Camiseta Azul" } },
    });
    renderRoutes("/admin/estoque", { "/admin/estoque": <Estoque /> });
    expect(await screen.findByText(/CAM-9 · Camiseta Azul/)).toBeInTheDocument();
    expect(apiMock.get.mock.calls.filter(([u]) => String(u).startsWith("/api/items/")).map(([u]) => u)).toEqual(["/api/items/aaaaaaaa-1111"]);
    expect(apiMock.get.mock.calls.some(([u]) => u === "/api/items")).toBe(false); // no whole-catalog fetch
  });
});
