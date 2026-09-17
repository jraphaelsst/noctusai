/**
 * Tests for `createApiKeysHooks` — URL / method / payload per endpoint,
 * plus the showSkeleton/isRefreshing loading-signal computation.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';

import { createApiKeysHooks } from './createApiKeysHooks';
import type { ApiClient } from '../../api';
import type { ApiKeyStatus, ApiKeysStatus } from './createApiKeysHooks';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

let api: ApiClient;
let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client: queryClient }, children);
}

const KEY_STATUS: ApiKeyStatus = {
  key: 'openai_api_key',
  label: 'OpenAI API Key',
  description: 'desc',
  is_secret: true,
  testable: true,
  input_type: 'password',
  placeholder: 'sk-...',
  configured: true,
  options: [],
  default: null,
  hint: '...b3f9',
  source: 'local',
  updated_at: '2026-09-17T00:00:00Z',
};

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  api = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  } as unknown as ApiClient;
});

describe('useApiKeys', () => {
  it('GETs the default base path', async () => {
    const payload: ApiKeysStatus = { items: [KEY_STATUS], total: 1 };
    (api.get as any).mockResolvedValue(payload);
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useApiKeys(), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual(payload));
    expect(api.get).toHaveBeenCalledWith('/api/settings/api-keys');
  });

  it('GETs a custom basePath when supplied', async () => {
    (api.get as any).mockResolvedValue({ items: [], total: 0 });
    const hooks = createApiKeysHooks(api, { basePath: '/api/custom/keys' });
    const { result } = renderHook(() => hooks.useApiKeys(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(api.get).toHaveBeenCalledWith('/api/custom/keys');
  });

  it('showSkeleton is true only before the first data arrives; isRefreshing is true on a later refetch', async () => {
    (api.get as any).mockResolvedValueOnce({ items: [], total: 0 });
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useApiKeys(), { wrapper });

    expect(result.current.showSkeleton).toBe(true);
    expect(result.current.isRefreshing).toBe(false);

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.showSkeleton).toBe(false);

    // A second, DEFERRED get so the in-flight refetch window is observable
    // (a synchronously-resolved mock races past `isFetching: true` before
    // `waitFor` gets a chance to see it).
    let resolveSecond: (v: ApiKeysStatus) => void = () => {};
    (api.get as any).mockReturnValueOnce(
      new Promise<ApiKeysStatus>((resolve) => {
        resolveSecond = resolve;
      }),
    );

    act(() => {
      void result.current.refetch();
    });
    await waitFor(() => expect(result.current.isFetching).toBe(true));
    expect(result.current.isRefreshing).toBe(true);
    expect(result.current.showSkeleton).toBe(false);

    act(() => resolveSecond({ items: [], total: 0 }));
    await waitFor(() => expect(result.current.isFetching).toBe(false));
  });
});

describe('useSaveApiKey', () => {
  it('PUTs {basePath}/{key} with { value } and invalidates the list', async () => {
    (api.put as any).mockResolvedValue(KEY_STATUS);
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useSaveApiKey(), { wrapper });

    act(() => {
      result.current.mutate({ key: 'openai_api_key', value: 'sk-new' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.put).toHaveBeenCalledWith('/api/settings/api-keys/openai_api_key', {
      value: 'sk-new',
    });
  });

  it('URL-encodes a key with special characters', async () => {
    (api.put as any).mockResolvedValue(KEY_STATUS);
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useSaveApiKey(), { wrapper });

    act(() => {
      result.current.mutate({ key: 'a/b c', value: 'v' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.put).toHaveBeenCalledWith(
      '/api/settings/api-keys/a%2Fb%20c',
      { value: 'v' },
    );
  });
});

describe('useRemoveApiKey', () => {
  it('DELETEs {basePath}/{key}', async () => {
    (api.delete as any).mockResolvedValue({ ...KEY_STATUS, configured: false, source: null });
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useRemoveApiKey(), { wrapper });

    act(() => {
      result.current.mutate('openai_api_key');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.delete).toHaveBeenCalledWith('/api/settings/api-keys/openai_api_key');
  });
});

describe('useTestApiKey', () => {
  it('POSTs {basePath}/{key}/test with an empty body', async () => {
    (api.post as any).mockResolvedValue({ key: 'openai_api_key', success: true, message: 'ok' });
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useTestApiKey(), { wrapper });

    act(() => {
      result.current.mutate('openai_api_key');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.post).toHaveBeenCalledWith('/api/settings/api-keys/openai_api_key/test', {});
  });

  it('resolves success:false as a normal (non-thrown) result', async () => {
    (api.post as any).mockResolvedValue({ key: 'x', success: false, message: 'Chave inválida' });
    const hooks = createApiKeysHooks(api);
    const { result } = renderHook(() => hooks.useTestApiKey(), { wrapper });

    act(() => {
      result.current.mutate('x');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.success).toBe(false);
  });
});
