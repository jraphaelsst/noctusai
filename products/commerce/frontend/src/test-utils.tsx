/**
 * Page-test helpers: a fresh QueryClient (no retries) + a MemoryRouter at a
 * given URL with the page routes under test, and a `fetch` stub for the
 * public storefront transport (same-origin `fetch`, not the seed ApiClient).
 */
import * as React from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";

export function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

/** Renders the current pathname + search so a test can assert navigation. */
function LocationProbe() {
  const loc = useLocation();
  return <output data-testid="location">{`${loc.pathname}${loc.search}`}</output>;
}

export function renderRoutes(url: string, routes: Record<string, React.ReactElement>) {
  const client = makeClient();
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          {Object.entries(routes).map(([path, el]) => (
            <Route key={path} path={path} element={el} />
          ))}
          <Route path="*" element={null} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...utils, client };
}

export type FetchRoute = (init: RequestInit | undefined, url: URL) => { status?: number; body?: unknown } | undefined;

/** Stubs global `fetch`: `routes["METHOD /path"]` answers; anything else is a 599 so an unexpected call is loud. */
export function stubFetch(routes: Record<string, FetchRoute | { status?: number; body?: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const entry = routes[`${method} ${url.pathname}`];
    const res = typeof entry === "function" ? entry(init, url) : entry;
    if (!res) return new Response(JSON.stringify({ error: { code: "unexpected", message: `${method} ${url.pathname}` } }), { status: 599 });
    const status = res.status ?? 200;
    return new Response(res.body === undefined ? "" : JSON.stringify(res.body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const STOREFRONT = {
  trade_name: "Loja Teste",
  legal_name: "Loja Teste LTDA",
  cnpj: "11222333000181",
  address: { street: "Rua A", number: "1", city: "São Paulo", state: "SP", zip: "01000000" },
  contact: { email: "contato@loja.test", phone: "11999990000" },
  brand_tokens: {},
  locale: "pt-BR",
  currency: "BRL",
  legal: { terms_version: "t1", privacy_version: "p1", withdrawal_text: "Arrependimento em 7 dias." },
};

export const VALID_CPF = "529.982.247-25";
