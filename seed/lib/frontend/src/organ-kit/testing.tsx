/** Shared test helpers for the organs (vitest-only; NOT exported from the organ-kit barrel). */
import { vi } from 'vitest';
import { ApiError } from '../api';
import type { OrganApi } from './query';

type Handler = unknown | ((path: string, arg?: unknown) => unknown);

export type RoutedHandler = Handler;

/**
 * Routed fake `ApiClient`: `routes['GET /api/finance/accounts']` is a value (resolved) or a function
 * `(path, argOrParams) => value` (may throw / return a rejected promise). An unrouted call REJECTS loudly
 * (a test must declare every endpoint it touches). Every call is recorded on the `vi.fn` mocks.
 * Pass the organ's own api type as `TApi` (default: the shared `OrganApi`).
 */
export function makeRoutedApi<TApi = OrganApi>(routes: Record<string, Handler> = {}) {
  const table = { ...routes };
  const run = (method: string) =>
    vi.fn(async (path: string, arg?: unknown) => {
      const clean = path.split('?')[0];
      const handler = table[`${method} ${clean}`] ?? table[`${method} ${path}`];
      if (handler === undefined) throw new ApiError(404, `unrouted ${method} ${path}`);
      return typeof handler === 'function' ? (handler as (p: string, a?: unknown) => unknown)(path, arg) : handler;
    });
  const api = {
    get: run('GET'),
    post: run('POST'),
    put: run('PUT'),
    patch: run('PATCH'),
    delete: run('DELETE'),
    upload: run('UPLOAD'),
    download: vi.fn(async (_path: string) => new Blob(['x'])),
  };
  return Object.assign(api as unknown as TApi & typeof api, {
    routes: table,
    route(key: string, handler: Handler) {
      table[key] = handler;
    },
  });
}

