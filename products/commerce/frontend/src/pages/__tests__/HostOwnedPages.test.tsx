/**
 * Pages whose data hooks live in this product (endpoints the organ hooks do not
 * wrap yet): `/minhas-compras?token=`, `/privacidade/verificar`, `/admin/configuracoes/enderecos`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import "@testing-library/jest-dom";

const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api: apiMock, useAuthStore: () => ({ user: null }) }));

import { ApiError } from "@noctusai/lib";
import MyOrders from "../storefront/MyOrders";
import PrivacyVerify from "../storefront/PrivacyVerify";
import Configuracoes from "../admin/Configuracoes";
import { renderRoutes, stubFetch, STOREFRONT } from "@/test-utils";

const ORDER = {
  token: "tokA",
  status: "paid",
  items: [{ title: "Curso de Foto", qty: 1, unit_price_cents: 9900, total_cents: 9900 }],
  subtotal_cents: 9900,
  discount_cents: 0,
  total_cents: 9900,
  currency: "BRL",
  payment_method: "pix",
  checkout_url: null,
  pix_qr: null,
  expires_at: null,
  paid_at: "2026-10-12T10:00:00Z",
  created_at: "2026-10-12T09:00:00Z",
};

const ROUTES = {
  "/minhas-compras": <MyOrders />,
  "/privacidade/verificar": <PrivacyVerify />,
  "/admin/configuracoes/*": <Configuracoes />,
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Minhas compras", () => {
  it("without a token: the magic-link request form", async () => {
    stubFetch({ "GET /api/storefront": { body: { data: STOREFRONT } } });
    renderRoutes("/minhas-compras", ROUTES);
    expect(await screen.findByLabelText(/E-mail/)).toBeInTheDocument();
  });

  it("with a token: lists the buyer's orders linking to each public view", async () => {
    const fetchMock = stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/my-orders": { body: { data: [ORDER] } },
    });
    renderRoutes("/minhas-compras?token=abcdefghijkl", ROUTES);
    expect(await screen.findByText(/1× Curso de Foto/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver pedido" })).toHaveAttribute("href", "/pedido/tokA");
    const url = fetchMock.mock.calls.map(([u]) => String(u)).find((u) => u.includes("/my-orders"))!;
    expect(url).toContain("token=abcdefghijkl");
  });

  it("with a token and no orders: empty state", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/my-orders": { body: { data: [] } },
    });
    renderRoutes("/minhas-compras?token=abcdefghijkl", ROUTES);
    expect(await screen.findByText("Nenhuma compra encontrada para este e-mail.")).toBeInTheDocument();
  });

  it("expired link: translated link_invalido + a way to ask for a new one", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "GET /api/storefront/my-orders": { status: 400, body: { error: { code: "link_invalido", message: "Link inválido." } } },
    });
    renderRoutes("/minhas-compras?token=abcdefghijkl", ROUTES);
    expect(await screen.findByText("Este link é inválido ou expirou. Peça um novo.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pedir um novo link" })).toHaveAttribute("href", "/minhas-compras");
  });
});

describe("Privacidade › verificar", () => {
  it("confirms the request and names its kind", async () => {
    const fetchMock = stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "POST /api/storefront/privacy-requests/verify": { body: { data: { status: "verified", kind: "deletion" } } },
    });
    renderRoutes("/privacidade/verificar?token=abcdefghijkl", ROUTES);
    expect(await screen.findByTestId("privacy-verified")).toHaveTextContent("exclusão dos dados");
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/privacy-requests/verify"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ token: "abcdefghijkl" });
  });

  it("missing token: says the link is incomplete and calls nothing", async () => {
    const fetchMock = stubFetch({ "GET /api/storefront": { body: { data: STOREFRONT } } });
    renderRoutes("/privacidade/verificar", ROUTES);
    expect(await screen.findByText(/Link incompleto/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/verify"))).toBe(false);
  });

  it("invalid link: translated link_invalido", async () => {
    stubFetch({
      "GET /api/storefront": { body: { data: STOREFRONT } },
      "POST /api/storefront/privacy-requests/verify": { status: 400, body: { error: { code: "link_invalido", message: "x" } } },
    });
    renderRoutes("/privacidade/verificar?token=abcdefghijkl", ROUTES);
    expect(await screen.findByText("Este link é inválido ou expirou. Peça um novo.")).toBeInTheDocument();
  });
});

describe("Admin › Endereços da vitrine", () => {
  function routeGets(hosts: unknown) {
    apiMock.get.mockImplementation((url: string) => {
      if (url === "/api/commerce/profile") return Promise.resolve({ data: null });
      if (url === "/api/commerce/hosts") return hosts instanceof Error ? Promise.reject(hosts) : Promise.resolve(hosts);
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  }

  it("non platform-admin (403): explanation, no form", async () => {
    routeGets(new ApiError(403, "Apenas a administração da plataforma pode fazer isso."));
    renderRoutes("/admin/configuracoes/enderecos", ROUTES);
    expect(await screen.findByText(/Somente a administração da plataforma/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Adicionar endereço" })).toBeNull();
  });

  it("lists hosts, adds one (POST) and maps host_ja_existe", async () => {
    routeGets({ data: [{ hostname: "loja.exemplo.com.br", org_id: "o", is_primary: true }] });
    apiMock.post
      .mockRejectedValueOnce(new ApiError(409, "x", { error: { code: "host_ja_existe", message: "x" } }))
      .mockResolvedValueOnce({ data: { hostname: "nova.exemplo.com", org_id: "o", is_primary: false } });
    renderRoutes("/admin/configuracoes/enderecos", ROUTES);
    expect(await screen.findByText("loja.exemplo.com.br")).toBeInTheDocument();
    expect(within(screen.getByTestId("hosts-list")).getByText("Principal")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Domínio/), { target: { value: "Nova.Exemplo.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar endereço" }));
    expect(await screen.findByText("Este domínio já está em uso.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Adicionar endereço" }));
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(2));
    expect(apiMock.post).toHaveBeenLastCalledWith("/api/commerce/hosts", { hostname: "nova.exemplo.com", is_primary: false });
  });

  it("empty: says buyers cannot reach the store yet", async () => {
    routeGets({ data: [] });
    renderRoutes("/admin/configuracoes/enderecos", ROUTES);
    expect(await screen.findByText(/Nenhum endereço cadastrado/)).toBeInTheDocument();
  });

  it("removes a host after confirmation (DELETE)", async () => {
    routeGets({ data: [{ hostname: "loja.exemplo.com.br", org_id: "o", is_primary: false }] });
    apiMock.delete.mockResolvedValue(undefined);
    renderRoutes("/admin/configuracoes/enderecos", ROUTES);
    fireEvent.click(await screen.findByRole("button", { name: "Remover" }));
    expect(screen.getByText(/Remover loja.exemplo.com.br\?/)).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: "Remover" });
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith("/api/commerce/hosts/loja.exemplo.com.br"));
  });
});
