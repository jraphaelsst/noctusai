/**
 * Query + transport plumbing shared by every organ's hooks factory (commerce, finance, items,
 * parties, inventory): the two-signal loading contract, `keepPreviousData`, the plain-fetch
 * transport for a public (unauthenticated) base URL, and the `ApiError` branch helpers.
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): `signals()` returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data`
 * (indicator only). Never `isLoading`, never a bare `isFetching` gate.
 */
import type { UseQueryResult } from '@tanstack/react-query';
import { ApiError, type ApiClient } from '../api';

/** The subset of the seed `ApiClient` an organ's hooks need. */
export type OrganApi = Pick<ApiClient, 'get' | 'post' | 'put' | 'patch' | 'delete' | 'upload'>;

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    // Non-JSON body (proxy error page): keep the raw text so ApiError carries it.
    return { message: text.slice(0, 300) };
  }
}

/** Plain-fetch transport for a base URL (public storefront; no auth header). */
export function createFetchTransport(apiBase: string): OrganApi {
  const base = apiBase.replace(/\/+$/, '');
  async function call<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
    const init: RequestInit = { method, headers: { Accept: 'application/json' } };
    if (form) {
      init.body = form;
    } else if (body !== undefined) {
      (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
    const res = await fetch(`${base}${path}`, init);
    const data = await parseBody(res);
    if (!res.ok) {
      const d = data as { error?: { message?: string }; detail?: unknown; message?: string } | null;
      const message =
        d?.error?.message ??
        (typeof d?.detail === 'string' ? d.detail : undefined) ??
        (d?.detail && typeof d.detail === 'object' && 'message' in (d.detail as object)
          ? String((d.detail as { message: unknown }).message)
          : undefined) ??
        d?.message ??
        `Erro HTTP ${res.status}`;
      throw new ApiError(res.status, message, data);
    }
    return data as T;
  }
  return {
    get: <T = any>(path: string, params?: Record<string, any>) => {
      const qs = params
        ? '?' +
          new URLSearchParams(
            Object.entries(params)
              .filter(([, v]) => v !== undefined && v !== null && v !== '')
              .map(([k, v]) => [k, String(v)]),
          ).toString()
        : '';
      return call<T>('GET', path + (qs === '?' ? '' : qs));
    },
    post: <T = any>(path: string, body?: unknown) => call<T>('POST', path, body ?? {}),
    put: <T = any>(path: string, body?: unknown) => call<T>('PUT', path, body ?? {}),
    patch: <T = any>(path: string, body?: unknown) => call<T>('PATCH', path, body ?? {}),
    delete: <T = any>(path: string, body?: unknown) => call<T>('DELETE', path, body),
    upload: <T = any>(path: string, form: FormData) => call<T>('POST', path, undefined, form),
  };
}

/** `ApiError` helpers the components branch on. */
export function apiErrorCode(err: unknown): string | null {
  return err instanceof ApiError ? err.code : null;
}
export function apiErrorStatus(err: unknown): number | null {
  return err instanceof ApiError ? err.status : null;
}
export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

/** Two-signal loading, computed once. A disabled query (`idle`) is not a skeleton. */
export function signals<TData, TErr>(q: UseQueryResult<TData, TErr>) {
  return {
    data: q.data,
    error: q.error,
    isError: q.isError,
    isPending: q.isPending,
    refetch: q.refetch,
    showSkeleton: q.isPending && !q.data && q.fetchStatus !== 'idle',
    isRefreshing: q.isFetching && !!q.data,
  };
}

export const keep = <T,>(prev: T | undefined) => prev;
