/**
 * Test harness for the Website admin pages (Settings + Leads): a recording
 * fake HTTP client behind the real `createWebsiteApi`, injected with
 * `WebsiteApiProvider` — no module mocking of our own code. Mirrors
 * `./billing-harness.tsx`.
 */
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { WebsiteApiProvider, createWebsiteApi, type HttpClient } from '../lib/website';

export type Route = (body?: unknown, params?: Record<string, any>) => unknown | Promise<unknown>;

export interface FakeHttp extends HttpClient {
  calls: Array<{ method: string; path: string; body?: unknown; params?: Record<string, any> }>;
}

export function fakeHttp(routes: Record<string, Route>): FakeHttp {
  const calls: FakeHttp['calls'] = [];
  const handle = (method: string) => async (path: string, arg?: unknown) => {
    const params = method === 'GET' ? (arg as Record<string, any> | undefined) : undefined;
    const body = method === 'GET' ? undefined : arg;
    calls.push({ method, path, body, params });
    const key = `${method} ${path.split('?')[0]}`;
    const route = routes[key];
    if (!route) throw new Error(`no fake route for ${key}`);
    return route(body, params);
  };
  return {
    calls,
    get: handle('GET') as HttpClient['get'],
    post: handle('POST') as HttpClient['post'],
    put: handle('PUT') as HttpClient['put'],
    patch: handle('PATCH') as HttpClient['patch'],
    async download(path: string) {
      calls.push({ method: 'DOWNLOAD', path });
      const key = `DOWNLOAD ${path.split('?')[0]}`;
      const route = routes[key];
      if (!route) throw new Error(`no fake route for ${key}`);
      return (await route()) as Blob;
    },
  };
}

export function renderWithWebsite(http: FakeHttp, ui: ReactNode, initialEntries: string[] = ['/']) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <WebsiteApiProvider value={createWebsiteApi(http)}>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </WebsiteApiProvider>
    </QueryClientProvider>
  );
}

export function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}
