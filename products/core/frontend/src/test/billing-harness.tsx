/**
 * Test harness for billing pages: a recording fake HTTP client behind the
 * real `createBillingApi`, injected with `BillingApiProvider` — no module
 * mocking of our own code.
 */
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { BillingApiProvider, createBillingApi, type HttpClient } from '../lib/billing';

export type Route = (body?: unknown) => unknown | Promise<unknown>;

export interface FakeHttp extends HttpClient {
  calls: Array<{ method: string; path: string; body?: unknown }>;
  routes: Record<string, Route>;
}

export function fakeHttp(routes: Record<string, Route>): FakeHttp {
  const calls: FakeHttp['calls'] = [];
  const handle = (method: string) => async (path: string, body?: unknown) => {
    calls.push({ method, path, body });
    const key = `${method} ${path.split('?')[0]}`;
    const route = routes[key];
    if (!route) throw new Error(`no fake route for ${key}`);
    return route(body);
  };
  return {
    calls,
    routes,
    get: handle('GET') as HttpClient['get'],
    post: handle('POST') as HttpClient['post'],
    put: handle('PUT') as HttpClient['put'],
    patch: handle('PATCH') as HttpClient['patch'],
  };
}

export function renderWithBilling(http: FakeHttp, ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <BillingApiProvider value={createBillingApi(http)}>
        <MemoryRouter>{ui}</MemoryRouter>
      </BillingApiProvider>
    </QueryClientProvider>
  );
}

export function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

export const SETTINGS = {
  mode: 'test',
  automations_enabled: false,
  encryption_configured: true,
  storage_price_usd_per_gb_month: '0.021',
  gateways: {
    stripe: {
      enabled: true,
      modes: {
        test: { secret_key: { configured: true, source: 'db' }, webhook_secret: { configured: false, source: null } },
        live: { secret_key: { configured: true, source: 'env' }, webhook_secret: { configured: true, source: 'env' } },
      },
    },
    asaas: {
      enabled: false,
      modes: {
        test: { api_key: { configured: false, source: null }, webhook_token: { configured: false, source: null } },
        live: { api_key: { configured: false, source: null }, webhook_token: { configured: false, source: null } },
      },
    },
  },
  webhook_urls: {
    stripe: 'https://core.example.com/api/billing/webhook',
    asaas: 'https://core.example.com/api/billing/webhooks/asaas',
  },
};
