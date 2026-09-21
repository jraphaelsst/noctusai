/**
 * Network-boundary fake for Agent Studio tests: stubs `globalThis.fetch`, so
 * the REAL seed `createApiClient` (URL building, query params, JSON bodies,
 * error envelopes, 204 handling) runs unchanged between the hook and the wire.
 *
 * Each route answers `METHOD /path` (pathname match, query ignored for
 * matching but recorded). An unmatched request is recorded in `unmatched`
 * and answered with a 599 so a test can never pass on a request it did not
 * expect.
 */
import { vi } from "vitest";

export const TEST_BASE_URL = "http://studio.test";

export interface RecordedCall {
  method: string;
  path: string;
  search: URLSearchParams;
  body: unknown;
}

export interface FakeRoute {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export function installFetch(routes: FakeRoute[]) {
  const calls: RecordedCall[] = [];
  const unmatched: string[] = [];

  const impl = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    const method = (init.method ?? "GET").toUpperCase();
    const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: url.pathname, search: url.searchParams, body });
    const route = routes.find((r) => r.method === method && r.path === url.pathname);
    if (!route) {
      unmatched.push(`${method} ${url.pathname}${url.search}`);
      return new Response(JSON.stringify({ detail: "rota não prevista no teste", code: "unmatched" }), { status: 599 });
    }
    const status = route.status ?? 200;
    if (status === 204) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(route.body ?? {}), {
      status,
      headers: { "content-type": "application/json", ...(route.headers ?? {}) },
    });
  };

  const spy = vi.fn(impl);
  vi.stubGlobal("fetch", spy);
  return { calls, unmatched, spy };
}
